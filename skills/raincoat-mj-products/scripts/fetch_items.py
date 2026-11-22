#!/usr/bin/env python3
"""Fetch one (platform, category, snapshot date) product ranking into JSONL.

Endpoint: /api/platform/{plat}/cats/{cid}/brands/all/hot_items

Measured behaviour (2026-11-19, market1):
- paging is ``page`` (1-based) + ``page_size``; ``iDisplayStart`` is ignored
- the list is capped at 100 rows per category/month — page beyond that returns []
- sorting is ``order_by=<column>&desc=true``; different columns expose different
  top-100 slices, so we merge a couple of them
- prices and amounts are in **cents**; ``sold`` is units
- there is no listing date anywhere in the row
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mmiapi import (  # noqa: E402
    SchemaChanged,
    Session,
    extract_rows,
    latest_month,
    resolve_path,
    run_cli,
)

MAX_ROWS_PER_SLICE = 100
DEFAULT_SLICES = ("sale", "sold")

ALIASES = {
    "item_id": ("item_id", "id", "itemId", "nid"),
    "title": ("title", "item", "item_name"),
    "shop": ("shop_name", "ishop", "shop"),
    "brand": ("brand_name", "brand"),
    "price": ("price", "price_raw"),
    "min_price": ("min_price",),
    "sale": ("sale", "sales", "gmv"),
    "sold": ("sold", "sales_volume", "volume"),
    "yoy": ("yoy",),
    "sold_yoy": ("sold_yoy",),
}


def month_of(value: str) -> str:
    value = value.strip()
    if len(value) == 7 and value[4] == "-":
        return value
    return value[:7]


def snapshot_path(data_dir: Path, plat: str, cid: str, label: str) -> Path:
    return data_dir / "snapshots" / plat / str(cid) / f"{label}.jsonl"


def seed_path(data_dir: Path, plat: str, cid: str, month: str) -> Path:
    return data_dir / "seeds" / plat / str(cid) / f"{month}.jsonl"


def _number(value) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "--", "null", "None", "N/A"}:
        return None
    try:
        return float(text.rstrip("%"))
    except ValueError:
        return None


def _money(value, unit: str = "cents") -> float | None:
    """Platform returns 分; keep a switch because the unit is an inference."""
    number = _number(value)
    if number is None:
        return None
    return round(number / 100.0, 2) if unit == "cents" else round(number, 2)


def pick(row: dict, keys: tuple[str, ...]):
    for key in keys:
        if key in row and row[key] not in (None, ""):
            return row[key]
    return None


def cat_path_text(value) -> str:
    """``cat_path`` comes back as a list of {category_name} dicts."""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        names = []
        for node in value:
            if isinstance(node, dict):
                name = node.get("category_name") or node.get("name")
                if name:
                    names.append(str(name))
        return "/".join(names)
    return ""


def normalize(row: dict, *, plat: str, cid: str, month: str, label: str, rank: int | None,
              slice_name: str, price_unit: str = "cents") -> dict | None:
    item_id = pick(row, ALIASES["item_id"])
    if item_id in (None, ""):
        return None
    title = pick(row, ALIASES["title"])
    if not title:
        raise SchemaChanged(
            "商品行里找不到标题字段；实际字段：" + ", ".join(sorted(row)[:20])
        )
    price_cents = pick(row, ALIASES["price"])
    return {
        "snapshot_date": label,
        "month": month,
        "plat": plat,
        "cid": str(cid),
        "item_id": str(item_id),
        "title": str(title),
        "shop": pick(row, ALIASES["shop"]),
        "brand": pick(row, ALIASES["brand"]),
        "price": _money(price_cents, price_unit),
        "min_price": _money(pick(row, ALIASES["min_price"]), price_unit),
        "price_raw": _number(price_cents),
        "sale": _money(pick(row, ALIASES["sale"]), price_unit),
        "sale_raw": _number(pick(row, ALIASES["sale"])),
        "price_unit": price_unit,
        "sold": _number(pick(row, ALIASES["sold"])),
        "yoy": _number(pick(row, ALIASES["yoy"])),
        "sold_yoy": _number(pick(row, ALIASES["sold_yoy"])),
        "cat_path": cat_path_text(row.get("cat_path")),
        "rank": rank,
        "rank_slice": slice_name,
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }


def build_params(month: str, page: int, page_size: int, order_by: str = "sale") -> dict:
    return {
        "start": month,
        "end": month,
        "page": page,
        "page_size": page_size,
        "order_by": order_by,
        "desc": "true",
        "lang": "zh",
    }


def fetch_slice(
    session: Session,
    *,
    plat: str,
    cid: str,
    month: str,
    label: str,
    order_by: str,
    max_items: int = MAX_ROWS_PER_SLICE,
    page_size: int = MAX_ROWS_PER_SLICE,
    price_unit: str = "cents",
) -> list[dict]:
    path = f"/api/platform/{plat}/cats/{cid}/brands/all/hot_items"
    rows: list[dict] = []
    page = 1
    while len(rows) < max_items:
        payload = session.get_json(path, build_params(month, page, page_size, order_by))
        chunk, _total = extract_rows(payload)
        if not chunk:
            break
        for index, raw in enumerate(chunk):
            entry = normalize(
                raw, plat=plat, cid=cid, month=month, label=label,
                rank=len(rows) + index + 1, slice_name=order_by, price_unit=price_unit,
            )
            if entry is not None:
                rows.append(entry)
            if len(rows) >= max_items:
                break
        if len(chunk) < page_size:
            break
        page += 1
    return rows


def fetch_rows(
    session: Session,
    *,
    plat: str,
    cid: str,
    month: str,
    label: str,
    max_items: int = MAX_ROWS_PER_SLICE,
    page_size: int = MAX_ROWS_PER_SLICE,
    slices: tuple[str, ...] = DEFAULT_SLICES,
    price_unit: str = "cents",
) -> tuple[list[dict], dict]:
    """Merge several top-100 slices; first slice wins for rank and metrics."""
    merged: dict[str, dict] = {}
    per_slice: dict[str, int] = {}
    for order_by in slices:
        part = fetch_slice(
            session, plat=plat, cid=cid, month=month, label=label,
            order_by=order_by, max_items=max_items, page_size=page_size, price_unit=price_unit,
        )
        per_slice[order_by] = len(part)
        for row in part:
            existing = merged.get(row["item_id"])
            if existing is None:
                merged[row["item_id"]] = row
            else:
                extra = [s for s in existing.get("also_ranked_in", "").split("|") if s]
                if order_by not in extra:
                    extra.append(order_by)
                    existing["also_ranked_in"] = "|".join(extra)

    rows = list(merged.values())
    meta = {
        "plat": plat,
        "cid": str(cid),
        "month": month,
        "label": label,
        "rows": len(rows),
        "per_slice": per_slice,
        "capped": any(count >= max_items for count in per_slice.values()),
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
    }
    return rows, meta


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def fetch_and_store(
    session: Session,
    *,
    data_dir: Path,
    plat: str,
    cid: str,
    label: str,
    month: str | None = None,
    max_items: int = MAX_ROWS_PER_SLICE,
    page_size: int = MAX_ROWS_PER_SLICE,
    kind: str = "snapshot",
    slices: tuple[str, ...] = DEFAULT_SLICES,
    price_unit: str = "cents",
) -> dict:
    month = month or month_of(label)
    rows, meta = fetch_rows(
        session, plat=plat, cid=cid, month=month, label=label,
        max_items=max_items, page_size=page_size, slices=slices, price_unit=price_unit,
    )
    target = (
        snapshot_path(data_dir, plat, cid, label)
        if kind == "snapshot"
        else seed_path(data_dir, plat, cid, month)
    )
    write_jsonl(target, rows)
    meta["path"] = str(target)
    return meta


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取单个类目的商品榜快照")
    parser.add_argument("--plat", required=True)
    parser.add_argument("--cid", required=True)
    parser.add_argument("--date", default=date.today().isoformat(), help="快照日 YYYY-MM-DD")
    parser.add_argument("--month", help="数据月份 YYYY-MM，默认取 --date 的月份")
    parser.add_argument("--kind", choices=["snapshot", "seed"], default="snapshot")
    parser.add_argument("--max-items", type=int, default=MAX_ROWS_PER_SLICE,
                        help=f"每个切片上限，服务端最多 {MAX_ROWS_PER_SLICE}")
    parser.add_argument("--page-size", type=int, default=MAX_ROWS_PER_SLICE)
    parser.add_argument("--price-unit", choices=["cents", "yuan"], default="cents",
                        help="接口金额单位，默认按分处理（35000 -> 350 元）")
    parser.add_argument("--order-by", action="append",
                        help="排序切片，可重复；默认 sale 与 sold")
    parser.add_argument("--data-dir", default=str(default_data_dir()))
    parser.add_argument("--state", help="登录态路径，默认 ~/.config/raincoat/mktindex/auth.json")
    parser.add_argument("--min-interval-ms", type=int, default=4000)
    parser.add_argument("--dry-run", action="store_true", help="只打印将要请求的 URL")
    args = parser.parse_args()

    data_dir = resolve_path(args.data_dir)
    month = month_of(args.month or args.date)
    slices = tuple(args.order_by) if args.order_by else DEFAULT_SLICES

    if args.dry_run:
        print(f"GET /api/platform/{args.plat}/cats/{args.cid}/brands/all/hot_items")
        print(f"  start={month}&end={month}&order_by={','.join(slices)}&page_size={args.page_size}")
        print("  （实跑时会用 /api/latesttime 把月份纠正到该平台的最新可用月）")
        return 0

    with Session(args.state, min_interval_ms=args.min_interval_ms) as session:
        if not args.month:
            _start, end = latest_month(session, args.plat)
            if end and month > end:
                print(f"提醒：{args.plat} 数据只到 {end}，改用 {end}（原请求 {month}）", file=sys.stderr)
                month = end
        meta = fetch_and_store(
            session,
            data_dir=data_dir,
            plat=args.plat,
            cid=args.cid,
            label=args.date if args.kind == "snapshot" else month,
            month=month,
            max_items=args.max_items,
            page_size=args.page_size,
            kind=args.kind,
            slices=slices,
            price_unit=args.price_unit,
        )
    print(json.dumps(meta, ensure_ascii=False, indent=2))
    if not meta["rows"]:
        print(
            f"警告：{meta['month']} 没有取到任何商品（该类目当月可能无数据，或超出可见范围）",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
