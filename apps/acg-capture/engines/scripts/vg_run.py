#!/usr/bin/env python3
"""ACG 游戏虚拟商品抓取引擎。

职责（2026-11-18 口径）：
  1. 不维护「要追踪的游戏库」：表里已经抓到的游戏就是清单，整游戏跳过；
  2. 每周一轮：只看窗口（默认 60 天）内新上线/新公布的手游端游，过热度门槛后
     抓一次代币/月卡/通行证写入企微「游戏虚拟商品」表，抓完即终态；
  3. 只读巡检（snapshot）、表结构初始化（init-table）、人工裁决（decide）、渠道库维护。

用法：
  python3 scripts/vg_run.py --snapshot
  python3 scripts/vg_run.py --init-table
  python3 scripts/vg_run.py --kind discover --write
  python3 scripts/vg_run.py --kind discover --window-days 30 --lanes deepseek
  python3 scripts/vg_run.py --decide <runId> --item <id> --decision accept --write

事件协议与其它两条线一致：stdout 每行 `@@ACG@@ {json}`；人看的进度走 stderr。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acg import vg_channels, vg_table  # noqa: E402
from acg.common import (  # noqa: E402
    CACHE_DIR,
    DATA_DIR,
    LOCKS_DIR,
    RUNS_DIR,
    VG_LEDGER_CACHE,
    now_iso,
    save_state,
    today,
)

TYPES = ["充值代币", "月卡", "通行证", "礼包", "其他"]
COVER_TYPES = ["充值代币", "月卡", "通行证"]


def log(message: str) -> None:
    print(f"[vg] {message}", file=sys.stderr, flush=True)


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1))


def load_games(path: str) -> list[dict] | None:
    """读显式游戏清单：JSON 数组（[{game,publisher,appStore}]）或 CSV（列 game / 游戏IP）。"""
    if not path:
        return None
    source = Path(path)
    if not source.exists():
        raise ValueError(f"游戏清单不存在：{path}")
    if source.suffix.lower() == ".csv":
        import csv

        with source.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        games = []
        for row in rows:
            name = (row.get("game") or row.get("游戏IP") or row.get("ip_name") or "").strip()
            if not name:
                continue
            games.append(
                {
                    "game": name,
                    "publisher": (row.get("publisher") or row.get("发行商") or "").strip(),
                    "appStore": (row.get("appStore") or "").strip(),
                    "rank": (row.get("排名") or "").strip(),
                }
            )
        return games
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("游戏清单 JSON 必须是数组")
    return [row for row in payload if isinstance(row, dict) and str(row.get("game") or "").strip()]


def snapshot() -> dict:
    """只读巡检：表里的商品就是全部状态，游戏汇总也从这里派生。"""
    channels = vg_channels.channels()
    games: list[dict] = []
    ledger = {
        "rows": 0,
        "byGame": {},
        "byType": {kind: 0 for kind in TYPES},
        "error": "",
    }
    try:
        items = vg_table.list_items()
        games = vg_table.games_from_items(items)
        for row in items:
            name = row.get("game") or "未命名"
            bucket = ledger["byGame"].setdefault(
                name, {"count": 0, "types": {}, "capturedAt": "", "channels": []}
            )
            bucket["count"] += 1
            kind = row.get("type") or "其他"
            bucket["types"][kind] = bucket["types"].get(kind, 0) + 1
            stamp = str(row.get("capturedAt") or "")[:10]
            if stamp and (not bucket["capturedAt"] or stamp < bucket["capturedAt"]):
                bucket["capturedAt"] = stamp
            channel = str(row.get("channel") or "").strip()
            if channel and channel not in bucket["channels"]:
                bucket["channels"].append(channel)
        ledger["rows"] = len(items)
        ledger["byType"] = {
            kind: sum(1 for row in items if (row.get("type") or "其他") == kind) for kind in TYPES
        }
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            VG_LEDGER_CACHE.write_text(
                json.dumps(
                    {"at": today(), "items": items, "byGame": ledger["byGame"], "games": games},
                    ensure_ascii=False,
                    indent=1,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
    except Exception as error:  # noqa: BLE001 - 表读不到时返回空巡检而不是崩掉
        ledger["error"] = str(error)[:200]

    coverage = [
        {
            "game": row["game"],
            "count": row["count"],
            "types": {kind: row["types"].get(kind, 0) for kind in COVER_TYPES},
            "missing": row["missing"],
            "capturedAt": row["capturedAt"],
            "channels": row["channels"],
        }
        for row in games
    ]

    return {
        "at": today(),
        "games": {
            "total": len(games),
            "withAllTypes": sum(1 for row in games if not row["missing"]),
            "missingTypes": sum(1 for row in games if row["missing"]),
        },
        "channels": {
            "total": len(channels),
            "confirmed": sum(1 for row in channels if row.get("status") == "confirmed"),
            "pending": sum(1 for row in channels if row.get("status") == "pending"),
            "dead": sum(1 for row in channels if row.get("status") == "dead"),
            "usable": sum(1 for row in channels if vg_channels.usable(row)),
        },
        "ledger": ledger,
        "coverage": coverage,
        "channelsAll": channels,
    }


def decide(run_id: str, item_id: str, decision: str, note: str, source: str, write: bool) -> int:
    """人工裁决入口：整段读改写都在跨进程锁里，避免同时点多个「采信」互相覆盖。"""
    from acg.common import RUNS_DIR, run_lock

    run_dir = RUNS_DIR / run_id
    with run_lock(run_dir):
        return _decide_locked(run_dir, item_id, decision, note, source, write)


def _decide_locked(run_dir, item_id: str, decision: str, note: str, source: str, write: bool) -> int:
    state_path = run_dir / "run.json"
    if not state_path.exists():
        _emit({"ok": False, "error": f"运行不存在：{run_id}"})
        return 1
    state = json.loads(state_path.read_text(encoding="utf-8"))
    item = next((row for row in (state.get("items") or []) if row.get("id") == item_id), None)
    if not item:
        _emit({"ok": False, "error": f"没有条目 {item_id}"})
        return 1
    if item.get("status") != "pending_review":
        _emit({"ok": False, "error": f"条目状态是 {item.get('status')}，只有待确认才能裁决"})
        return 1
    from acg.common import save_state

    written = 0
    if decision == "accept":
        if source:
            item["source"] = source
        item["status"] = "accepted"
        item["decidedBy"] = "human"
        item["decidedAt"] = now_iso()
        if write:
            vg_table.add_items([{"values": vg_table.item_values(item)}], vg_table.empty_records())
            item["written"] = True
            written = 1
        state["counts"]["pending"] = max(0, state["counts"].get("pending", 1) - 1)
        state["counts"]["accepted"] = state["counts"].get("accepted", 0) + 1
        state["counts"]["written"] = state["counts"].get("written", 0) + written
    else:
        item["status"] = "rejected"
        item["reasons"] = list(item.get("reasons") or []) + ["manual_reject"]
        item["decidedBy"] = "human"
        item["decidedAt"] = now_iso()
        state["counts"]["pending"] = max(0, state["counts"].get("pending", 1) - 1)
        state["counts"]["rejected"] = state["counts"].get("rejected", 0) + 1
    if note:
        item["note"] = note
    save_state(state_path, state)
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                {"at": now_iso(), "type": "decide", "item": item_id, "decision": decision, "written": written},
                ensure_ascii=False,
            )
            + "\n"
        )
    _emit({"ok": True, "item": item, "written": written})
    return 0


def _regroup_items(items: list[dict]) -> list[dict]:
    """把「980创世结晶」「300三角币」这类按档位拆开的候选合回一个商品。

    老运行里的候选是按档位存的（名字带面额），面板的待确认列表就会被同一商品的
    多个档位刷屏。这里重新按商品名归一 + 合并价格，一个商品只留一条。
    """
    from acg import vg_accept, vg_table

    groups: dict[str, list[dict]] = {}
    for item in items:
        record = dict(item)
        canon, denom = vg_table.canonical_product(str(record.get("name") or ""))
        if canon:
            record["name"] = canon
        if denom and not record.get("denom"):
            record["denom"] = denom
        groups.setdefault(vg_accept.product_key(record), []).append(record)

    merged: list[dict] = []
    for rows in groups.values():
        keep = dict(rows[0])
        prices: list[dict] = []
        for row in rows:
            entries = row.get("prices") or []
            if not entries and row.get("price"):
                entries = [{"price": row["price"], "denom": row.get("denom") or "", "channel": row.get("channel") or ""}]
            for entry in entries:
                if entry not in prices:
                    prices.append(entry)
        if prices:
            keep["prices"] = prices
            keep["price"] = keep.get("price") or prices[0].get("price")
        notes: list[str] = []
        for row in rows:
            for part in str(row.get("note") or "").split("；"):
                part = part.strip()
                if part and part not in notes:
                    notes.append(part)
        keep["note"] = "；".join(notes)
        longest = max(rows, key=lambda row: len(str(row.get("quote") or "")))
        keep["quote"] = longest.get("quote") or keep.get("quote")
        keep["source"] = longest.get("source") or keep.get("source")
        reason_rows = [row for row in rows if row.get("reasons")]
        keep["reasons"] = []
        merged.append(keep)
    return merged


def _canonical_run_id(value: str) -> str | None:
    """面板只列出 r-YYYYMMDD-HHMMSS-vg-discover 形式的运行；自定义 id 会被派生成标准 id。

    这样命令行手动跑的一轮也能在「抓取任务」里看到，而不是只在磁盘上。
    """
    import re
    from datetime import datetime

    text = str(value or "").strip()
    if not text:
        return None
    if re.match(r"^r-\d{8}-\d{6}-vg-discover$", text):
        return text
    return f"r-{datetime.now().strftime('%Y%m%d-%H%M%S')}-vg-discover"


def reverify(
    run_id: str,
    policy: str = "strict",
    write: bool = False,
    games: list[dict] | None = None,
    extras: list[str] | None = None,
) -> int:
    """按新口径重判一轮已抓到的候选，不重新联网抓取。

    用途：口径变了（例如不再按官方渠道卡）、或者批次等待超时后候选人已经跑出来了，
    用已经落盘的候选重跑验收，让能过的行进表，不用再花一次模型钱。
    """
    import sys

    from acg import dispatch, vg_accept, vg_channels, vg_discover, vg_table

    run_dir = RUNS_DIR / run_id
    if not run_dir.exists():
        _emit({"ok": False, "error": f"运行不存在：{run_id}"})
        return 1
    state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    channels = vg_channels.channels()
    page_cache: dict = {}

    def target_for(name: str) -> dict | None:
        if not games:
            return None
        return vg_discover._match_game({"game": name}, games)

    items = state.get("items") or []
    # 验收是网络密集型：先把所有来源页并发取一遍（同一个 URL 只取一次），再逐条判
    urls = {str(row.get("source") or "") for row in items if str(row.get("source") or "").startswith("http")}
    for path in extras or []:
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError:
            continue
        for candidate in dispatch.parse_candidates(text):
            url = str(candidate.get("source") or candidate.get("url") or "")
            if url.startswith("http"):
                urls.add(url)
    if urls:
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda url: vg_accept._page(page_cache, url), sorted(urls)))
        print(f"[vg] 预取 {len(urls)} 个来源页", file=sys.stderr, flush=True)

    records: list[dict] = []
    for item in _regroup_items(items):
        record = {**item, "reasons": [], "status": "pending_review"}
        target = target_for(str(item.get("game") or ""))
        if target:
            record["game"] = target["game"]
        game = {"game": record["game"], "publisher": item.get("publisher") or "", "channelIds": []}
        records.append(vg_accept.verify(record, game, channels, page_cache, policy=policy))

    # 超时批次/历史运行里已经跑出来的候选，一并重新验收
    for path in extras or []:
        text = Path(path).read_text(encoding="utf-8")
        candidates = dispatch.parse_candidates(text)
        normalized = []
        for candidate in candidates:
            target = target_for(str(candidate.get("game") or ""))
            if not target:
                continue
            normalized.append(vg_accept.normalize_candidate(candidate, target, str(candidate.get("lane") or "workbuddy")))
        verified = [
            vg_accept.verify(record, {"game": record["game"], "publisher": "", "channelIds": []}, channels, page_cache, policy=policy)
            for record in vg_accept.merge(normalized)
        ]
        records.extend(vg_accept.combine_products(verified))

    existing = vg_table.list_items()
    existing_keys = {vg_accept.product_key(row) for row in existing}
    counts = {"accepted": 0, "rejected": 0, "pending": 0, "duplicate": 0, "written": 0}
    accepted_rows = []
    seen: set[str] = set()
    for record in records:
        key = vg_accept.product_key(record)
        if key in seen:
            continue
        seen.add(key)
        if key in existing_keys:
            record["status"] = "duplicate"
            record["written"] = False
            counts["duplicate"] += 1
        elif record["status"] == "accepted":
            counts["accepted"] += 1
            if write:
                record["written"] = True
                accepted_rows.append({"values": vg_table.item_values(record)})
        elif record["status"] == "pending_review":
            counts["pending"] += 1
        else:
            counts["rejected"] += 1

    if accepted_rows:
        vg_table.add_items(accepted_rows, vg_table.empty_records())
        counts["written"] = len(accepted_rows)

    state["items"] = records
    # 面板按 counts 展示这一轮「采纳/写入」了多少，重判后必须跟着更新，否则显示 0
    state["counts"] = {
        "accepted": counts["accepted"],
        "rejected": counts["rejected"],
        "pending": counts["pending"],
        "duplicate": counts["duplicate"],
        "written": counts["written"],
        "dispatched": (state.get("counts") or {}).get("dispatched", 0),
        "done": 0,
        "unavailable": 0,
    }
    state["status"] = "done"
    state["stage"] = "done"
    if not state.get("endedAt"):
        state["endedAt"] = now_iso()
    state["reverify"] = {"at": now_iso(), "policy": policy, "counts": counts}
    save_state(run_dir / "run.json", state)
    with (run_dir / "events.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"at": now_iso(), "type": "reverify", "policy": policy, "counts": counts},
                                ensure_ascii=False) + "\n")
    _emit({"ok": True, "runId": run_id, "policy": policy, "counts": counts})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="ACG 游戏虚拟商品抓取引擎")
    parser.add_argument("--kind", choices=["discover"], default="")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--init-table", action="store_true")
    parser.add_argument("--window-days", type=int, default=0, help="只看最近 N 天出现的新游戏，默认取 vg-sources.json")
    parser.add_argument("--lanes", default="workbuddy,deepseek")
    parser.add_argument("--since", default="")
    parser.add_argument("--until", default="")
    parser.add_argument("--games-file", default="", help="显式游戏清单（JSON 数组或 CSV，字段 game/游戏IP），跳过发现层")
    parser.add_argument("--wb-batch", type=int, default=0, help="workbuddy 每批几个游戏，默认 8")
    parser.add_argument("--wb-timeout", type=int, default=0, help="workbuddy 单批等待上限（秒），默认 1200")
    parser.add_argument("--wb-parallel", type=int, default=0, help="workbuddy 同时跑几批，默认 3")
    parser.add_argument("--policy", choices=["strict", "open"], default="strict", help="验收口径：strict 只认官方渠道；open 不卡渠道")
    parser.add_argument("--reverify", default="", help="按新口径重判一次已抓到的候选（不重新抓取）")
    parser.add_argument("--extra", action="append", default=[], help="额外的候选文件（超时批次抢救出来的正文）")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--no-agent", action="store_true", help="只算清单，不派 Agent")
    parser.add_argument("--discover-only", action="store_true", help="只发现新游戏，不抓商品")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--trigger", default="manual")
    parser.add_argument("--decide", default="", help="待确认条目裁决：runId")
    parser.add_argument("--item", default="")
    parser.add_argument("--decision", choices=["accept", "reject"], default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--source", default="")
    # 渠道库维护（插件与人工调用）
    parser.add_argument("--channels-upsert-json", default="")
    parser.add_argument("--channels-delete", default="")
    parser.add_argument("--channels-probe", default="")
    args = parser.parse_args()

    try:
        if args.channels_upsert_json:
            payload = json.loads(args.channels_upsert_json)
            row = vg_channels.upsert(payload)
            _emit({"ok": True, "channel": row, "channels": vg_channels.channels()})
            return 0

        if args.channels_delete:
            data = vg_channels.load()
            before = len(data["channels"])
            data["channels"] = [row for row in data["channels"] if row.get("id") != args.channels_delete]
            if len(data["channels"]) == before:
                _emit({"ok": False, "error": "渠道不存在"})
                return 1
            vg_channels.save(data)
            _emit({"ok": True, "channels": vg_channels.channels()})
            return 0

        if args.channels_probe:
            row = next(
                (item for item in vg_channels.channels() if item.get("id") == args.channels_probe),
                None,
            )
            if not row:
                _emit({"ok": False, "error": "渠道不存在"})
                return 1
            evidence = vg_channels.probe(row)
            if evidence.get("ok"):
                vg_channels.upsert({**row, "lastVerified": today()})
            _emit({"ok": True, "evidence": evidence})
            return 0

        if args.decide:
            if not args.item or not args.decision:
                _emit({"ok": False, "error": "缺少 --item 或 --decision"})
                return 1
            return decide(args.decide, args.item, args.decision, args.note, args.source, args.write)

        if args.reverify:
            return reverify(
                args.reverify,
                policy=args.policy,
                write=args.write,
                games=load_games(args.games_file),
                extras=args.extra,
            )

        if args.init_table:
            _emit(vg_table.ensure_columns())
            return 0

        if args.snapshot:
            _emit(snapshot())
            return 0

        if args.kind == "discover":
            import re as _re
            from datetime import datetime as _dt

            from acg import vg_discover

            DATA_DIR.mkdir(parents=True, exist_ok=True)
            LOCKS_DIR.mkdir(parents=True, exist_ok=True)
            run = vg_discover.run(
                window_days=args.window_days,
                lanes=args.lanes,
                since=args.since,
                until=args.until,
                write=args.write,
                use_agent=not args.no_agent,
                run_id=_canonical_run_id(args.run_id),
                trigger=args.trigger,
                discover_only=args.discover_only,
                games=load_games(args.games_file),
                wb_batch=args.wb_batch,
                wb_timeout=args.wb_timeout,
                wb_parallel=args.wb_parallel,
                policy=args.policy,
            )
            _emit(
                {
                    "runId": run.id,
                    "status": run.state["status"],
                    "counts": run.state["counts"],
                    "discovery": run.state.get("discovery"),
                }
            )
            return 0 if run.state["status"] in ("done", "partial") else 1

        parser.print_help()
        return 2
    except ValueError as error:
        _emit({"ok": False, "error": str(error)})
        return 1
    except Exception as error:  # noqa: BLE001
        log(f"失败：{error}")
        _emit({"ok": False, "error": str(error)[:500]})
        return 1


if __name__ == "__main__":
    sys.exit(main())
