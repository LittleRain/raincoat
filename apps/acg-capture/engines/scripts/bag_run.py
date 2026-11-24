#!/usr/bin/env python3
"""ACG 官方福袋抓取引擎。

职责：
  1. 维护线索（仓库 JSON）与渠道（仓库 JSON），供插件读写；
  2. 按线索派发 workbuddy + DeepSeek 双源抓取，汇总、验收后写入企微「官方福袋」表；
  3. 只读巡检（snapshot）与表结构初始化（init-table）。

用法：
  python3 scripts/bag_run.py --snapshot
  python3 scripts/bag_run.py --init-table
  python3 scripts/bag_run.py --kind discover --write
  python3 scripts/bag_run.py --kind discover --leads lead-genshin --lanes deepseek
  python3 scripts/bag_run.py --leads-upsert-json '<json>'
  python3 scripts/bag_run.py --leads-delete lead-genshin
  python3 scripts/bag_run.py --channels-upsert-json '<json>'
  python3 scripts/bag_run.py --channels-probe mihoyo-mihuyoupin

事件协议与官方赏一致：stdout 每行 `@@ACG@@ {json}`；人看的进度走 stderr。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from acg import bag_channels, bag_leads, bag_table  # noqa: E402
from acg.common import BAG_LEDGER_CACHE, CACHE_DIR, DATA_DIR, LOCKS_DIR, today  # noqa: E402


def log(message: str) -> None:
    print(f"[bag] {message}", file=sys.stderr, flush=True)


def _emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=1))


def _channel_ids() -> set[str]:
    return {row.get("id") for row in bag_channels.load()["channels"]}


def snapshot() -> dict:
    leads = bag_leads.load()["leads"]
    channels = bag_channels.load()["channels"]
    health = bag_leads.stats(leads, channels)
    try:
        bags = bag_table.list_bags()
        ledger = {"rows": len(bags), "error": ""}
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            BAG_LEDGER_CACHE.write_text(
                json.dumps({"at": today(), "bags": bags}, ensure_ascii=False, indent=1), encoding="utf-8"
            )
        except OSError:
            # 缓存写不进去（只读环境/沙箱）不影响巡检，台账本身以企微表为准
            pass
    except Exception as error:  # noqa: BLE001 - 表读不到不能阻断线索巡检
        ledger = {"rows": 0, "error": str(error)[:200]}
    return {
        "at": today(),
        "leads": health,
        "channels": {
            "total": len(channels),
            "confirmed": sum(1 for row in channels if row.get("status") == "confirmed"),
            "pending": sum(1 for row in channels if row.get("status") == "pending"),
            "dead": sum(1 for row in channels if row.get("status") == "dead"),
            "usable": sum(1 for row in channels if bag_channels.usable(row)),
        },
        "ledger": ledger,
    }


def _reload_after_write() -> dict:
    leads = bag_leads.load()["leads"]
    channels = bag_channels.load()["channels"]
    return {"leads": leads, "channels": channels, "stats": bag_leads.stats(leads, channels)}


def decide(run_id: str, item_id: str, decision: str, note: str, source: str, write: bool) -> int:
    """人工裁决：采信（写表）或判废（只标记）。

    整段读改写都在 run_lock 里做：插件同时点多个「采信」时，多个进程会并发读改写同一个 run.json，
    没有锁就会互相覆盖（只有一个条目的状态留下），所以这里是跨进程串行化的入口。
    """
    from acg.common import RUNS_DIR, now_iso, run_lock, save_state

    run_dir = RUNS_DIR / run_id
    state_path = run_dir / "run.json"
    if not state_path.exists():
        _emit({"ok": False, "error": f"运行不存在：{run_id}"})
        return 1

    with run_lock(run_dir):
        state = json.loads(state_path.read_text(encoding="utf-8"))
        item = next((row for row in (state.get("items") or []) if row.get("id") == item_id), None)
        if not item:
            _emit({"ok": False, "error": f"没有条目 {item_id}"})
            return 1
        if item.get("status") != "pending_review":
            _emit({"ok": False, "error": f"条目状态是 {item.get('status')}，只有待确认才能裁决"})
            return 1
        written = 0
        if decision == "accept":
            if source:
                item["source"] = source
            item["status"] = "accepted"
            item["decidedBy"] = "human"
            item["decidedAt"] = now_iso()
            if write:
                bag_table.add_bags([{"values": bag_table.bag_values(item)}], bag_table.empty_records())
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


def main() -> int:
    parser = argparse.ArgumentParser(description="ACG 官方福袋抓取引擎")
    parser.add_argument("--kind", choices=["discover"], default="")
    parser.add_argument("--snapshot", action="store_true")
    parser.add_argument("--init-table", action="store_true")
    parser.add_argument("--leads", default="", help="只跑这些线索，逗号分隔")
    parser.add_argument("--lanes", default="workbuddy,deepseek")
    parser.add_argument("--modes", default="sweep,channel", help="workbuddy 任务：sweep 全量扫街 / channel 定向渠道")
    parser.add_argument("--since", default="")
    parser.add_argument("--until", default="")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--no-agent", action="store_true", help="只算清单，不派 Agent")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--trigger", default="manual")
    parser.add_argument("--decide", default="", help="待确认条目裁决：runId")
    parser.add_argument("--item", default="")
    parser.add_argument("--decision", choices=["accept", "reject"], default="")
    parser.add_argument("--note", default="")
    parser.add_argument("--source", default="")
    # 线索 / 渠道维护（插件调用，校验只在这一处）
    parser.add_argument("--leads-upsert-json", default="")
    parser.add_argument("--leads-delete", default="")
    parser.add_argument("--leads-status", default="")
    parser.add_argument("--status", choices=["active", "paused"], default="")
    parser.add_argument("--channels-upsert-json", default="")
    parser.add_argument("--channels-delete", default="")
    parser.add_argument("--channels-probe", default="")
    args = parser.parse_args()

    try:
        if args.leads_upsert_json:
            payload = json.loads(args.leads_upsert_json)
            row = bag_leads.upsert(payload, _channel_ids())
            _emit({"ok": True, "lead": row, **_reload_after_write()})
            return 0

        if args.leads_delete:
            removed = bag_leads.remove(args.leads_delete)
            _emit({"ok": removed, "error": "" if removed else "线索不存在", **_reload_after_write()})
            return 0 if removed else 1

        if args.leads_status:
            if not args.status:
                _emit({"ok": False, "error": "缺少 --status"})
                return 1
            data = bag_leads.load()
            row = next((item for item in data["leads"] if item.get("id") == args.leads_status), None)
            if not row:
                _emit({"ok": False, "error": "线索不存在"})
                return 1
            bag_leads.upsert({**row, "status": args.status}, _channel_ids())
            _emit({"ok": True, **_reload_after_write()})
            return 0

        if args.channels_upsert_json:
            payload = json.loads(args.channels_upsert_json)
            row = bag_channels.upsert(payload)
            _emit({"ok": True, "channel": row, **_reload_after_write()})
            return 0

        if args.channels_delete:
            used = [
                lead.get("id")
                for lead in bag_leads.load()["leads"]
                if args.channels_delete in (lead.get("channelIds") or [])
            ]
            if used:
                _emit({"ok": False, "error": f"渠道仍被线索引用：{', '.join(used[:5])}"})
                return 1
            removed = bag_channels.remove(args.channels_delete)
            _emit({"ok": removed, "error": "" if removed else "渠道不存在", **_reload_after_write()})
            return 0 if removed else 1

        if args.channels_probe:
            row = next(
                (item for item in bag_channels.load()["channels"] if item.get("id") == args.channels_probe),
                None,
            )
            if not row:
                _emit({"ok": False, "error": "渠道不存在"})
                return 1
            evidence = bag_channels.probe(row)
            if evidence.get("ok"):
                bag_channels.upsert({**row, "lastVerified": today()})
            _emit({"ok": True, "evidence": evidence})
            return 0

        if args.decide:
            if not args.item or not args.decision:
                _emit({"ok": False, "error": "缺少 --item 或 --decision"})
                return 1
            return decide(args.decide, args.item, args.decision, args.note, args.source, args.write)

        if args.init_table:
            result = bag_table.ensure_columns()
            _emit(result)
            return 0

        if args.snapshot:
            _emit(snapshot())
            return 0

        if args.kind == "discover":
            from acg import bag_discover

            DATA_DIR.mkdir(parents=True, exist_ok=True)
            LOCKS_DIR.mkdir(parents=True, exist_ok=True)
            run = bag_discover.run(
                leads_filter=args.leads,
                lanes=args.lanes,
                since=args.since,
                until=args.until,
                write=args.write,
                use_agent=not args.no_agent,
                run_id=args.run_id or None,
                trigger=args.trigger,
                modes=args.modes,
            )
            _emit({"runId": run.id, "status": run.state["status"], "counts": run.state["counts"]})
            return 0 if run.state["status"] == "done" else 1

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
