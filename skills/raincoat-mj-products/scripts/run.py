#!/usr/bin/env python3
"""Orchestrate 魔镜 new-product collection: validate → plan → fetch → diff → report.

Tiers are driven by the number of (platform, category) pairs, see plan.py:
small runs fail loudly, large runs never try to fetch an entire tree.
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date as date_cls
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_report  # noqa: E402
import diff_new  # noqa: E402
import plan as planner  # noqa: E402
from categories import Resolver, tree_for_plat  # noqa: E402
from fetch_items import fetch_and_store, snapshot_path  # noqa: E402
from mmiapi import (  # noqa: E402
    AuthRequired,
    Forbidden,
    MmiError,
    NotFound,
    RateLimiter,
    Session,
    default_config_path,
    is_logged_in,
    resolve_path,
)
from platforms import probe  # noqa: E402


def load_config(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # noqa: WPS433
        except ImportError as exc:  # optional dependency
            raise ValueError(
                "读取 YAML 配置需要 pyyaml（pip install pyyaml）；也可以直接用 JSON 配置"
            ) from exc
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("配置文件必须是对象")
    return data


def resolve_entry(entry: dict, plat: str, data_dir: Path, cache: dict) -> dict:
    """Resolve one config category for one platform → {cid, alias, path}."""
    alias = entry.get("alias") or entry.get("path") or str(entry.get("cid") or "")
    if not alias:
        raise MmiError("类目条目缺少 alias/path/cid")

    explicit = (entry.get("paths") or {}).get(plat)
    if explicit:
        resolver = cache.setdefault(tree_for_plat(plat), Resolver(tree_for_plat(plat), data_dir))
        info = resolver.resolve(explicit)
        return {"plat": plat, "cid": info["cid"], "alias": alias, "path": info["path"]}

    cid = entry.get("cid")
    if cid and entry.get("plat") in (None, plat):
        try:
            tree = tree_for_plat(plat)
        except MmiError:
            return {"plat": plat, "cid": str(cid), "alias": alias,
                    "path": entry.get("path") or ""}
        resolver = cache.setdefault(tree, Resolver(tree, data_dir))
        if str(cid) not in resolver.nodes:
            raise MmiError(f"cid {cid} 不在 {tree} 类目树里（跨平台 cid 不通用）")
        info = resolver.describe(str(cid))
        return {"plat": plat, "cid": str(cid), "alias": alias,
                "path": entry.get("path") or info["path"]}

    if entry.get("path"):
        tree = tree_for_plat(plat)
        resolver = cache.setdefault(tree, Resolver(tree, data_dir))
        info = resolver.resolve(entry["path"])
        return {"plat": plat, "cid": info["cid"], "alias": alias, "path": info["path"]}

    raise MmiError("类目条目缺少 path/paths/cid")


def platform_status(entry: dict, month: str) -> tuple[bool, str]:
    if not entry or not entry.get("ok"):
        return False, (entry or {}).get("error") or "平台不可用"
    end = entry.get("end") or ""
    start = entry.get("start") or ""
    if end and end < month:
        return False, f"数据止于 {end}，{month} 还没出"
    if start and month < start:
        return False, f"数据从 {start} 开始"
    return True, ""


def _months_between(earlier: str, later: str) -> int:
    return (int(later[:4]) - int(earlier[:4])) * 12 + (int(later[5:7]) - int(earlier[5:7]))


def previous_months(month: str, count: int) -> list[str]:
    year, mon = int(month[:4]), int(month[5:7])
    months = []
    for _ in range(count):
        mon -= 1
        if mon == 0:
            year, mon = year - 1, 12
        months.append(f"{year:04d}-{mon:02d}")
    return sorted(months)


def write_state(path: Path, record: dict) -> None:
    state = {"runs": []}
    if path.is_file():
        try:
            state = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            pass
    state.setdefault("runs", []).append(record)
    state["runs"] = state["runs"][-50:]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="魔镜新品抓取编排")
    parser.add_argument("--config", help="配置文件，默认工作目录下的 config.json")
    parser.add_argument("--date", default=date_cls.today().isoformat(), help="快照日")
    parser.add_argument("--month", help="数据月份，默认取各平台最新可用月份的最小值")
    parser.add_argument("--window", type=int, help="新品窗口天数，默认取配置")
    parser.add_argument("--max-items", type=int, help="每类目抓取条数上限")
    parser.add_argument("--data-dir", help="覆盖配置里的 data_dir")
    parser.add_argument("--out-dir", help="覆盖配置里的 output_dir")
    parser.add_argument("--state", help="登录态路径")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划与预算")
    parser.add_argument("--force", action="store_true", help="已有快照也重抓")
    parser.add_argument("--skip-seeds", action="store_true", help="不补历史月度种子")
    parser.add_argument("--limit-categories", type=int, help="XL 档：只抓前 K 个类目")
    args = parser.parse_args()

    config_path = resolve_path(args.config, str(default_config_path()))
    if not config_path.is_file():
        print(
            f"找不到配置：{config_path}\n先跑一次引导：python scripts/onboard.py",
            file=sys.stderr,
        )
        return 2
    try:
        config = load_config(config_path)
    except (ValueError, OSError) as exc:
        print(f"配置文件读不了：{exc}", file=sys.stderr)
        return 2
    # 配置里的相对路径以配置文件所在目录为基准；命令行参数仍按当前目录解析。
    cfg_base = config_path.parent

    def from_config(value, default: str) -> Path:
        raw = Path(str(value or default)).expanduser()
        return raw.resolve() if raw.is_absolute() else (cfg_base / raw).resolve()

    data_dir = from_config(args.data_dir or config.get("data_dir"), "./data")
    out_dir = from_config(args.out_dir or config.get("output_dir"), "./output")
    window = int(args.window or (config.get("window") or {}).get("days") or 7)
    topn = int(args.max_items or (config.get("fetch") or {}).get("max_items_per_category") or 100)
    page_size = int((config.get("fetch") or {}).get("page_size") or 100)
    slices = tuple((config.get("fetch") or {}).get("order_by_slices") or ("sale", "sold"))
    price_unit = str((config.get("fetch") or {}).get("price_unit") or "cents")

    plats = config.get("platforms") or [{"plat": "all"}]
    categories = config.get("categories") or []
    if not categories:
        print("配置里没有 categories", file=sys.stderr)
        return 2

    # 0) cheap session pre-flight: /api/user answers 200 even for guests.
    state_path = str(resolve_path(args.state)) if args.state else (
        str(Path(str(config.get("auth_state"))).expanduser())
        if config.get("auth_state") else None
    )
    user: dict = {}
    try:
        with Session(state_path) as preflight:
            user = (preflight.get_json("/api/user") or {}).get("result") or {}
        logged_in = is_logged_in(user)
        reason = "登录态是未登录状态（usertype=logged_out），Cookie 无效或已过期"
    except AuthRequired as exc:
        logged_in = False
        reason = str(exc)
    if not logged_in:
        if not args.dry_run:
            print(f"{reason}\n先跑 `python scripts/login.py` 再重试。", file=sys.stderr)
            return 3
        print(f"（预览模式：{reason}；实跑前需要先登录）", file=sys.stderr)
    else:
        print(f"会话有效：{user.get('username') or user.get('nick') or ''}".rstrip("："))

    available = probe(data_dir)
    wanted = [item["plat"] for item in plats]

    # 1) month: latest month common to the configured platforms, unless given.
    month = args.month
    if not month:
        ends = [available.get(p, {}).get("end") for p in wanted if available.get(p, {}).get("ok")]
        ends = [e for e in ends if e]
        if not ends:
            print("配置的平台全都不可用，先跑 scripts/platforms.py probe", file=sys.stderr)
            return 2
        # 取最新的可用月份；停更平台不能把整体拉回历史
        month = max(ends)
        lag = _months_between(month, date_cls.today().strftime("%Y-%m"))
        if lag > 3:
            print(
                f"最新可用月份是 {month}（距今 {lag} 个月），疑似配置里只剩停更平台；"
                "确认要分析历史数据请显式传 --month",
                file=sys.stderr,
            )
            return 2

    usable, skipped_plats = {}, []
    for plat in wanted:
        ok, reason = platform_status(available.get(plat, {}), month)
        usable[plat] = ok
        if not ok:
            skipped_plats.append({"plat": plat, "reason": reason})

    usable_plats = [p for p in wanted if usable.get(p)]
    if not usable_plats:
        print(f"没有任何平台能提供 {month} 的数据：" + json.dumps(skipped_plats, ensure_ascii=False),
              file=sys.stderr)
        return 2

    # 2) resolve categories per platform
    cache: dict[str, Resolver] = {}
    pairs: list[dict] = []
    unmapped: list[dict] = []
    groups = {item["plat"]: (item.get("group") or item["plat"]) for item in plats}
    for plat in usable_plats:
        for entry in categories:
            try:
                pair = resolve_entry(entry, plat, data_dir, cache)
                pair["group"] = groups.get(plat, plat)
                pairs.append(pair)
            except MmiError as exc:
                unmapped.append({"plat": plat, "entry": entry.get("alias") or entry.get("path"),
                                 "reason": str(exc)})

    if not pairs:
        print("所有类目都没解析成功：\n" + json.dumps(unmapped, ensure_ascii=False, indent=2),
              file=sys.stderr)
        return 2

    pairs = [dict(t) for t in {tuple(sorted(p.items())) for p in pairs}]
    if args.limit_categories:
        pairs = pairs[: args.limit_categories]

    # 3) plan + budget
    try:
        exec_plan = planner.build(
            pairs, config, topn=topn, page_size=page_size,
            max_requests=int((config.get("budget") or {}).get("max_requests") or 3000),
        )
    except ValueError as exc:
        print(f"计划被拒绝：{exc}", file=sys.stderr)
        return 2

    print(planner.describe(exec_plan))
    if skipped_plats:
        print("跳过平台：" + "；".join(f"{s['plat']}（{s['reason']}）" for s in skipped_plats))
    if unmapped:
        print(f"未映射类目 {len(unmapped)} 条（详见 --dry-run 输出）")

    if args.dry_run:
        for pair in pairs:
            print(f"  {pair['plat']:<14}{pair['cid']:<12}{pair['alias']}")
        if unmapped:
            print(json.dumps(unmapped, ensure_ascii=False, indent=2))
        print(f"\n数据月份 {month}，快照日 {args.date}，窗口 {window} 天，每类目上限 {topn}")
        return 0

    # 4) fetch
    limiter = RateLimiter(int((config.get("fetch") or {}).get("min_interval_ms") or 1500))
    local = threading.local()

    def session() -> Session:
        client = getattr(local, "client", None)
        if client is None:
            client = Session(
                args.state or config.get("auth_state"),
                limiter=limiter,
                retries=int((config.get("fetch") or {}).get("max_retries") or 3),
            )
            local.client = client
        return client

    def task(pair: dict, kind: str, label: str, target_month: str) -> dict:
        if kind == "snapshot":
            existing = snapshot_path(data_dir, pair["plat"], pair["cid"], label)
            if existing.is_file() and not args.force:
                return {"pair": pair, "kind": kind, "status": "cached", "path": str(existing)}
        try:
            meta = fetch_and_store(
                session(), data_dir=data_dir, plat=pair["plat"], cid=str(pair["cid"]),
                label=label, month=target_month, max_items=topn, page_size=page_size,
                kind=kind, slices=slices, price_unit=price_unit,
            )
            return {"pair": pair, "kind": kind, "status": "ok", "meta": meta}
        except (AuthRequired, Forbidden, NotFound, MmiError) as exc:
            return {"pair": pair, "kind": kind, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}

    baseline = int((config.get("new_product") or {}).get("baseline_months") or 0)
    tasks: list[tuple[dict, str, str, str]] = []
    if baseline and not args.skip_seeds:
        for seed_month in previous_months(month, baseline):
            for pair in pairs:
                seed_file = data_dir / "seeds" / pair["plat"] / str(pair["cid"]) / f"{seed_month}.jsonl"
                if not seed_file.is_file() or args.force:
                    tasks.append((pair, "seed", seed_month, seed_month))
    for pair in pairs:
        tasks.append((pair, "snapshot", args.date, month))

    print(f"开始抓取：{len(tasks)} 个任务，并发 {exec_plan.concurrency}")
    results = []
    failures = []
    if exec_plan.concurrency > 1 and len(tasks) > 1:
        with ThreadPoolExecutor(max_workers=exec_plan.concurrency) as pool:
            futures = [pool.submit(task, *item) for item in tasks]
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                if result["status"] == "failed":
                    failures.append(result)
    else:
        for item in tasks:
            result = task(*item)
            results.append(result)
            if result["status"] == "failed":
                failures.append(result)
                if not exec_plan.continue_on_error:
                    print(f"S 档遇到失败即停止：{result['error']}", file=sys.stderr)
                    return 1

    ok = [r for r in results if r["status"] in {"ok", "cached"}]
    if failures:
        print(f"失败 {len(failures)} 个：" + "；".join(
            f"{f['pair']['plat']}/{f['pair']['alias']} {f.get('error', '')}" for f in failures[:5]
        ), file=sys.stderr)

    snapshot_ok = [r for r in ok if r["kind"] == "snapshot"]
    if not snapshot_ok:
        print("没有任何快照抓取成功，终止。", file=sys.stderr)
        return 1

    # 5) diff
    live_pairs = [r["pair"] for r in snapshot_ok]
    rows: list[dict] = []
    metas = []
    for pair in live_pairs:
        part, meta = diff_new.window_rows(
            data_dir, plat=pair["plat"], cid=str(pair["cid"]), alias=pair["alias"],
            cat_path=pair.get("path") or "", day=date_cls.fromisoformat(args.date), window=window,
            market=pair.get("group"),
        )
        rows.extend(part)
        metas.append(meta)
    deduped = diff_new.dedupe_global(rows)
    csv_path = data_dir / "out" / f"near{window}d_new_{args.date}.csv"
    diff_new.write_csv(csv_path, deduped)

    # 6) report
    summary = build_report.summarize(deduped, data_dir, args.date)
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"new_products_report_{args.date}.md"
    md_path.write_text(build_report.markdown(summary, deduped, args.date, window), encoding="utf-8")
    xlsx_path = out_dir / f"new_products_{args.date}.xlsx"
    made_xlsx = build_report.write_xlsx(xlsx_path, summary, deduped)

    record = {
        "date": args.date,
        "month": month,
        "window": window,
        "tier": exec_plan.tier,
        "pairs": len(pairs),
        "snapshots": len(snapshot_ok),
        "new_items": len(deduped),
        "failures": len(failures),
        "skipped_platforms": skipped_plats,
        "unmapped": len(unmapped),
        "csv": str(csv_path),
        "markdown": str(md_path),
        "xlsx": str(xlsx_path) if made_xlsx else None,
    }
    write_state(data_dir / "state.json", record)

    print(json.dumps(record, ensure_ascii=False, indent=2))
    if any(m["window_partial"] for m in metas):
        print("\n注意：日快照不足一个窗口，first_seen 可能偏晚（见报告页脚）。", file=sys.stderr)
    return 0 if not failures or exec_plan.continue_on_error else 1


if __name__ == "__main__":
    raise SystemExit(main())
