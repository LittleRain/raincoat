#!/usr/bin/env python3
"""Render the new-product table into a Markdown summary and an xlsx workbook.

Everything here is derived from the CSV produced by diff_new.py plus the snapshots
on disk (needed for "share of the category's monthly sales"). No network access.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date as date_cls
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mmiapi import default_data_dir, resolve_path  # noqa: E402

BANDS = [(0, 50, "<50"), (50, 100, "50–100"), (100, 200, "100–200"),
         (200, 500, "200–500"), (500, None, "≥500")]


def read_csv(path: Path) -> list[dict]:
    # utf-8-sig also reads plain UTF-8, and strips the BOM we write for Excel
    with path.open("r", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def _num(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def snapshot_sale(data_dir: Path, plat: str, cid: str, day: str) -> float:
    path = data_dir / "snapshots" / plat / str(cid) / f"{day}.jsonl"
    if not path.is_file():
        return 0.0
    total = 0.0
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            try:
                total += _num(json.loads(line).get("sale"))
            except ValueError:
                continue
    return total


def band_of(price: float | None) -> str:
    if price is None:
        return "未知"
    for low, high, label in BANDS:
        if price >= low and (high is None or price < high):
            return label
    return "未知"


def group_snapshot_sales(data_dir: Path, plats: set[str], cid: str, day: str) -> float:
    """Union of the category ranking across platforms, deduped by item id."""
    sales: dict[str, float] = {}
    for plat in sorted(plats):
        path = data_dir / "snapshots" / plat / str(cid) / f"{day}.jsonl"
        if not path.is_file():
            continue
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                item_id = str(row.get("item_id") or "")
                value = _num(row.get("sale"))
                if item_id and value > sales.get(item_id, 0.0):
                    sales[item_id] = value
    return sum(sales.values())


def summarize(rows: list[dict], data_dir: Path, day: str) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row.get("market") or row["plat"], row["cat_alias"])].append(row)

    summary = []
    for (market, alias), group in sorted(groups.items()):
        cid = group[0]["cid"]
        plats = sorted({r["plat"] for r in group})
        new_sale = sum(_num(r.get("sale")) for r in group)
        cat_sale = group_snapshot_sales(data_dir, set(plats), cid, day)
        brands: dict[str, float] = defaultdict(float)
        for row in group:
            brands[row.get("brand") or "未知"] += _num(row.get("sale"))
        brand_total = sum(brands.values()) or 1.0
        top_brands = sorted(brands.items(), key=lambda kv: kv[1], reverse=True)[:5]
        summary.append(
            {
                "plat": "/".join(plats),
                "market": market,
                "cat_alias": alias,
                "cid": cid,
                "cat_path": group[0].get("cat_path") or "",
                "new_count": len(group),
                "new_sale": round(new_sale, 2),
                "cat_sale": round(cat_sale, 2),
                "sale_share": round(new_sale / cat_sale, 4) if cat_sale else None,
                "top5_brand_share": round(sum(v for _, v in top_brands) / brand_total, 4),
                "top_brands": "、".join(f"{name}({value:.0f})" for name, value in top_brands),
                "breakout": sum(1 for r in group if (_num(r.get("rank")) or 10**9) <= 50),
                "window_partial": group[0].get("window_partial") == "True",
            }
        )
    return summary


def markdown(summary: list[dict], rows: list[dict], day: str, window: int) -> str:
    lines = [f"# 近 {window} 天新品（{day}）", ""]
    partial = any(item["window_partial"] for item in summary)
    if partial:
        lines += [
            "> ⚠️ 部分类目的日快照不足一个窗口，`first_seen` 可能偏晚；"
            "连续采集满窗口后口径才完整。",
            "",
        ]
    lines += [
        "## 类目概览",
        "",
        "| 平台 | 类目 | 新品数 | 新品销售额 | 类目总额 | 占比 | 品牌TOP5集中度 | 进前50 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in summary:
        share = "—" if item["sale_share"] is None else f"{item['sale_share'] * 100:.1f}%"
        lines.append(
            f"| {item['plat']} | {item['cat_alias']} | {item['new_count']} | "
            f"{item['new_sale']:,.0f} | {item['cat_sale']:,.0f} | {share} | "
            f"{item['top5_brand_share'] * 100:.1f}% | {item['breakout']} |"
        )

    top = sorted(rows, key=lambda r: _num(r.get("sale")), reverse=True)[:20]
    lines += ["", "## 新品 TOP20（按当月销售额）", "",
              "| # | 平台 | 类目 | 商品 | 品牌 | 价格 | 销量 | 销售额 | 名次 | 首次出现 |",
              "| ---: | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for idx, row in enumerate(top, 1):
        title = (row.get("title") or "").replace("|", "／")[:42]
        lines.append(
            f"| {idx} | {row['plat']} | {row['cat_alias']} | {title} | "
            f"{row.get('brand') or '—'} | {_num(row.get('price')):.0f} | "
            f"{_num(row.get('sold')):.0f} | {_num(row.get('sale')):,.0f} | "
            f"{row.get('rank') or '—'} | {row.get('first_seen_date')} |"
        )

    bands: dict[str, int] = defaultdict(int)
    for row in rows:
        bands[band_of(_num(row.get("price")) if row.get("price") else None)] += 1
    lines += ["", "## 价格带分布", "", "| 价格带 | 数量 |", "| --- | ---: |"]
    for _, _, label in BANDS + [(0, None, "未知")]:
        if bands.get(label):
            lines.append(f"| {label} | {bands[label]} |")

    lines += [
        "",
        "---",
        "",
        "口径说明：销量/销售额为**当月累计**，不是近 7 天；新品判定为「首次出现在快照里」，"
        "榜单截断会让真实新品的发现时间偏晚。",
    ]
    return "\n".join(lines) + "\n"


def write_xlsx(path: Path, summary: list[dict], rows: list[dict]) -> bool:
    try:
        from openpyxl import Workbook
    except ImportError:
        return False

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "类目概览"
    headers = ["平台", "类目", "cid", "类目路径", "新品数", "新品销售额", "类目总销售额",
               "占比", "品牌TOP5集中度", "进前50", "口径不完整"]
    sheet.append(headers)
    for item in summary:
        sheet.append([
            item["plat"], item["cat_alias"], item["cid"], item["cat_path"],
            item["new_count"], item["new_sale"], item["cat_sale"],
            item["sale_share"], item["top5_brand_share"], item["breakout"],
            item["window_partial"],
        ])

    detail = workbook.create_sheet("新品明细")
    columns = ["plat", "cat_alias", "cat_path", "cid", "item_id", "title", "brand", "shop",
               "price", "min_price", "sold", "sale", "rank", "first_seen_date",
               "first_seen_month", "days_since_seen", "in_latest", "window_partial",
               "also_in"]
    detail.append(columns)
    for row in rows:
        detail.append([row.get(col) for col in columns])

    for column in ("E", "F", "G", "H", "I"):
        for cell in sheet[column][1:]:
            cell.number_format = "0.00%"
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(path)
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="生成新品摘要（Markdown + xlsx）")
    parser.add_argument("--csv", required=True, help="diff_new.py 产出的 CSV")
    parser.add_argument("--data-dir", default=str(default_data_dir()))
    parser.add_argument("--date", default=date_cls.today().isoformat())
    parser.add_argument("--window", type=int, default=7)
    parser.add_argument("--out-dir", default="./output")
    args = parser.parse_args()

    csv_path = Path(args.csv).expanduser().resolve()
    if not csv_path.is_file():
        print(f"找不到 CSV：{csv_path}\n先跑 scripts/run.py 或 scripts/diff_new.py 生成它", file=sys.stderr)
        return 2
    data_dir = resolve_path(args.data_dir)
    out_dir = resolve_path(args.out_dir)

    rows = read_csv(csv_path)
    summary = summarize(rows, data_dir, args.date)

    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"new_products_report_{args.date}.md"
    md_path.write_text(markdown(summary, rows, args.date, args.window), encoding="utf-8")

    xlsx_path = out_dir / f"new_products_{args.date}.xlsx"
    made_xlsx = write_xlsx(xlsx_path, summary, rows)
    if not made_xlsx:
        print("未安装 openpyxl，跳过 xlsx（pip install openpyxl 后可生成）", file=sys.stderr)

    print(json.dumps({
        "rows": len(rows),
        "categories": len(summary),
        "markdown": str(md_path),
        "xlsx": str(xlsx_path) if made_xlsx else None,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
