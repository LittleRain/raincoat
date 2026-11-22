#!/usr/bin/env python3
"""Diff snapshots into "first seen in the last N days" new products.

The platform's product ranking has no listing date, and its metrics are monthly,
so "new" here means: the item id shows up for the first time in a snapshot taken
inside the window. Items seen only in a monthly seed are history, not news.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import date as date_cls, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mmiapi import default_data_dir, resolve_path  # noqa: E402

COLUMNS = [
    "plat",
    "market",
    "cat_alias",
    "cat_path",
    "cid",
    "item_id",
    "title",
    "brand",
    "shop",
    "price",
    "min_price",
    "sold",
    "sale",
    "rank",
    "first_seen_date",
    "first_seen_month",
    "days_since_seen",
    "in_latest",
    "window_partial",
    "also_in",
    "snapshot_date",
]


def _rows(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    out = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def daily_files(data_dir: Path, plat: str, cid: str) -> list[tuple[date_cls, Path]]:
    folder = data_dir / "snapshots" / plat / str(cid)
    found = []
    if folder.is_dir():
        for path in folder.glob("*.jsonl"):
            try:
                found.append((date_cls.fromisoformat(path.stem), path))
            except ValueError:
                continue
    return sorted(found)


def seed_files(data_dir: Path, plat: str, cid: str) -> list[tuple[str, Path]]:
    folder = data_dir / "seeds" / plat / str(cid)
    found = []
    if folder.is_dir():
        for path in folder.glob("*.jsonl"):
            stem = path.stem
            if len(stem) == 7 and stem[4] == "-":
                found.append((stem, path))
    return sorted(found)


def first_seen(data_dir: Path, plat: str, cid: str, upto: date_cls) -> dict[str, dict]:
    """item_id -> {first_date, first_month} using everything on disk <= upto."""
    index: dict[str, dict] = {}
    for month, path in seed_files(data_dir, plat, cid):
        for row in _rows(path):
            item_id = str(row.get("item_id") or "")
            if not item_id:
                continue
            entry = index.setdefault(item_id, {"first_date": None, "first_month": None})
            if entry["first_month"] is None or month < entry["first_month"]:
                entry["first_month"] = month

    for day, path in daily_files(data_dir, plat, cid):
        if day > upto:
            continue
        month = day.strftime("%Y-%m")
        for row in _rows(path):
            item_id = str(row.get("item_id") or "")
            if not item_id:
                continue
            entry = index.setdefault(item_id, {"first_date": None, "first_month": None})
            if entry["first_date"] is None or day.isoformat() < entry["first_date"]:
                entry["first_date"] = day.isoformat()
            if entry["first_month"] is None or month < entry["first_month"]:
                entry["first_month"] = month
    return index


def window_rows(
    data_dir: Path,
    *,
    plat: str,
    cid: str,
    alias: str,
    cat_path: str,
    day: date_cls,
    window: int = 7,
    market: str | None = None,
) -> tuple[list[dict], dict]:
    """Rows first seen inside [day-window+1, day], with their latest metrics."""
    files = [(d, p) for d, p in daily_files(data_dir, plat, cid) if d <= day]
    latest_day = files[-1][0] if files else None
    earliest_day = files[0][0] if files else None

    partial = True
    if earliest_day is not None:
        covered = (day - earliest_day).days + 1
        partial = covered < window

    index = first_seen(data_dir, plat, cid, day)
    start = day - timedelta(days=window - 1)

    # latest row per item across snapshots inside the window
    latest_row: dict[str, dict] = {}
    seen_in_latest: set[str] = set()
    for when, path in files:
        if when < start:
            continue
        rows = _rows(path)
        for row in rows:
            item_id = str(row.get("item_id") or "")
            if not item_id:
                continue
            latest_row[item_id] = row
            if latest_day is not None and when == latest_day:
                seen_in_latest.add(item_id)

    out: list[dict] = []
    for item_id, seen in index.items():
        first = seen.get("first_date")
        if not first:
            continue
        first_day = date_cls.fromisoformat(first)
        if first_day < start or first_day > day:
            continue
        # A monthly seed proves the item existed before this snapshot, so a first
        # daily appearance inside the window is not a launch signal.
        first_month = seen.get("first_month")
        if first_month and first_month < first[:7]:
            continue
        row = latest_row.get(item_id)
        if row is None:
            # entered the ranking earlier in the window, then dropped out
            for when, path in reversed(files):
                if when < first_day:
                    continue
                match = next(
                    (r for r in _rows(path) if str(r.get("item_id")) == item_id), None
                )
                if match is not None:
                    row = match
                    break
        if row is None:
            continue
        out.append(
            {
                "plat": plat,
                "cat_alias": alias,
                "cat_path": cat_path or row.get("cat_path") or "",
                "cid": str(cid),
                "item_id": item_id,
                "title": row.get("title"),
                "brand": row.get("brand"),
                "shop": row.get("shop"),
                "price": row.get("price"),
                "min_price": row.get("min_price"),
                "sold": row.get("sold"),
                "sale": row.get("sale"),
                "rank": row.get("rank"),
                "first_seen_date": first,
                "first_seen_month": seen.get("first_month") or first[:7],
                "days_since_seen": (day - first_day).days,
                "in_latest": item_id in seen_in_latest,
                "window_partial": partial,
                "also_in": "",
                "snapshot_date": row.get("snapshot_date"),
                "market": market or plat,
            }
        )

    out.sort(key=lambda r: (r["first_seen_date"], r["rank"] or 10**9))
    meta = {
        "plat": plat,
        "cid": str(cid),
        "alias": alias,
        "window": window,
        "window_partial": partial,
        "market": market or plat,
        "snapshot_dates": len(files),
        "latest_snapshot": latest_day.isoformat() if latest_day else None,
        "new_items": len(out),
    }
    return out, meta


def dedupe_global(rows: list[dict]) -> list[dict]:
    """Keep the first category per (market, item), record the rest.

    ``market`` groups platforms that share one item-id space (淘宝+天猫+tmall…), so
    the same product fetched under two of them is not counted twice.
    """
    kept: dict[tuple[str, str], dict] = {}
    for row in rows:
        key = (row.get("market") or row["plat"], row["item_id"])
        if key in kept:
            other = kept[key]
            names = [n for n in other["also_in"].split("|") if n]
            if row["cat_alias"] not in names:
                names.append(row["cat_alias"])
                other["also_in"] = "|".join(names)
            continue
        kept[key] = row
    return list(kept.values())


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # utf-8-sig: Excel on Windows opens plain UTF-8 CSV as mojibake
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def discover_pairs(data_dir: Path) -> list[dict]:
    """Fallback when no plan is given: whatever snapshots already exist."""
    pairs = []
    root = data_dir / "snapshots"
    if not root.is_dir():
        return pairs
    for plat_dir in sorted(root.iterdir()):
        if not plat_dir.is_dir():
            continue
        for cid_dir in sorted(plat_dir.iterdir()):
            if cid_dir.is_dir():
                pairs.append(
                    {"plat": plat_dir.name, "cid": cid_dir.name, "alias": cid_dir.name, "path": ""}
                )
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description="生成近 N 天新品表")
    parser.add_argument("--date", default=date_cls.today().isoformat())
    parser.add_argument("--window", type=int, default=7)
    parser.add_argument("--data-dir", default=str(default_data_dir()))
    parser.add_argument("--out", help="输出 CSV 路径，默认 <data-dir>/out/near{window}d_new_<date>.csv")
    parser.add_argument("--plan", help="plan.json（run.py 生成），不给则扫描已有快照")
    parser.add_argument("--no-dedupe", action="store_true", help="关闭跨类目 item 去重")
    args = parser.parse_args()

    data_dir = resolve_path(args.data_dir)
    day = date_cls.fromisoformat(args.date)

    if args.plan:
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        pairs = plan.get("pairs") or []
    else:
        pairs = discover_pairs(data_dir)

    rows: list[dict] = []
    metas = []
    for pair in pairs:
        part, meta = window_rows(
            data_dir,
            plat=pair["plat"],
            cid=str(pair["cid"]),
            alias=pair.get("alias") or str(pair["cid"]),
            cat_path=pair.get("path") or "",
            day=day,
            window=args.window,
        )
        rows.extend(part)
        metas.append(meta)

    if not args.no_dedupe:
        rows = dedupe_global(rows)

    out = resolve_path(
        args.out, str(data_dir / "out" / f"near{args.window}d_new_{args.date}.csv")
    )
    write_csv(out, rows)

    partial = any(meta["window_partial"] for meta in metas)
    print(
        json.dumps(
            {
                "date": args.date,
                "window": args.window,
                "pairs": len(pairs),
                "new_items": len(rows),
                "window_partial": partial,
                "out": str(out),
                "per_pair": metas,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if partial:
        print(
            "\n注意：部分类目的日快照不足一个窗口，first_seen 可能偏晚（window_partial=true）。",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
