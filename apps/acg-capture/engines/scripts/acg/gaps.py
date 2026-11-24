"""缺口计算与本轮批次。

三类缺口，同一轮同一批派发（2026-11-18 口径修正）：

- price  赏盘「单抽价」为空或写着「未公布 / 待补」
- count  子品「单套数量」为空（LAST 不算，它固定 1 个、不填）
- sub    赏盘有、子品行 0 条：缺整套子品结构（赏别 + 赏名 + 别名，数量拿不到可留空）

sub 原先只统计不派单，结果 8 个无子品的盘永远补不上。现在它是必做项，排在本轮最前
（要从零建行，工作量最大），排序后才轮到 count / price。
"""

from __future__ import annotations

import difflib
from collections import defaultdict

from .common import norm
from .table import is_last

EMPTY_PRICE = {"", "未公布", "待补", "-", "暂无"}


def _price_missing(pan: dict) -> bool:
    return pan["price"].strip() in EMPTY_PRICE


def compute(pans: list[dict], subs: list[dict]) -> dict:
    sub_by_pan = defaultdict(list)
    for sub in subs:
        sub_by_pan[sub["pan_rid"]].append(sub)

    price_pans = [pan for pan in pans if _price_missing(pan)]

    # 报表口径：表格里「单套数量为空」的全部行（含 LAST），和用户筛选看到的数一致
    all_empty = defaultdict(list)
    for sub in subs:
        if sub["qty"] is None:
            all_empty[sub["pan_rid"]].append(sub)

    # 待补口径：LAST 固定 1 个、按约定不填，所以真正要补的是非 LAST 行
    count_rows = defaultdict(list)
    for sub in subs:
        if is_last(sub["kind"]):
            continue
        if sub["qty"] is None:
            count_rows[sub["pan_rid"]].append(sub)

    nosub = [pan for pan in pans if not sub_by_pan.get(pan["rid"])]
    nosub_ids = {pan["rid"] for pan in nosub}

    by_pan: dict[str, dict] = {}
    for pan in pans:
        gaps = []
        if pan["rid"] in nosub_ids:
            gaps.append("sub")
        if _price_missing(pan):
            gaps.append("price")
        rows = count_rows.get(pan["rid"], [])
        if rows:
            gaps.append("count")
        if not gaps:
            continue
        by_pan[pan["rid"]] = {
            "panRecordId": pan["rid"],
            "pan": pan["name"],
            "alias": pan["alias"],
            "brand": pan["brand"],
            "price": pan["price"],
            "release": pan["release"],
            "gaps": gaps,
            "rows": [
                {"recordId": row["rid"], "kind": row["kind"], "name": row["name"]}
                for row in rows[:40]
            ],
            "rowCount": len(rows),
        }

    return {
        "stats": {
            "pans": len(pans),
            "subs": len(subs),
            "pricePans": len(price_pans),
            "countRows": sum(len(rows) for rows in all_empty.values()),
            "countPans": len(all_empty),
            "lastRows": sum(1 for rows in all_empty.values() for row in rows if is_last(row["kind"])),
            "actionableRows": sum(len(rows) for rows in count_rows.values()),
            "actionablePans": len(count_rows),
            "subPans": len(nosub),
            "queuePans": len(by_pan),
            "noSubPans": len(nosub),
        },
        "byPan": by_pan,
        "pricePans": price_pans,
        "noSub": nosub,
        "dedup": dedup_candidates(pans, sub_by_pan),
    }


def dedup_candidates(pans: list[dict], sub_by_pan: dict) -> list[dict]:
    """同名 / 高度相似的占位行：只报告，不自动删。"""
    pairs = []
    for i, left in enumerate(pans):
        for right in pans[i + 1 :]:
            a, b = norm(left["name"]), norm(right["name"])
            if not a or not b:
                continue
            same = a == b
            similar = difflib.SequenceMatcher(None, a, b).ratio() >= 0.93
            if not (same or similar):
                continue
            left_empty = not sub_by_pan.get(left["rid"]) and _price_missing(left)
            right_empty = not sub_by_pan.get(right["rid"]) and _price_missing(right)
            if not (left_empty or right_empty):
                continue
            pairs.append(
                {
                    "left": {"id": left["rid"], "name": left["name"], "empty": left_empty},
                    "right": {"id": right["rid"], "name": right["name"], "empty": right_empty},
                    "ratio": round(difflib.SequenceMatcher(None, a, b).ratio(), 3),
                }
            )
    return pairs


def pick_batch(by_pan: dict, size: int = 999) -> list[dict]:
    items = list(by_pan.values())

    def rank(item):
        kinds = set(item["gaps"])
        # 无子品的盘最先（要从零建行），其次缺口类型多的、缺的行多的
        return (
            0 if "sub" in kinds else 1,
            -len(kinds),
            -item["rowCount"],
            item["release"],
        )

    return sorted(items, key=rank)[:size]
