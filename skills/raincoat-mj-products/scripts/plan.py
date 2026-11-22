#!/usr/bin/env python3
"""Turn 平台×类目 数量 into an execution plan: tier, budget, failure semantics.

Small runs should fail loudly; large runs must never try to fetch the whole tree.
This module is pure (no network, no disk) so the tiers are unit-testable.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

TIERS: list[tuple[str, int, int | None, dict]] = [
    # name, min_categories, max_categories, behaviour
    ("S", 1, 10, {"continue_on_error": False, "probe": False, "concurrency": 1}),
    ("M", 11, 50, {"continue_on_error": True, "probe": False, "concurrency": 1}),
    ("L", 51, 300, {"continue_on_error": True, "probe": True, "concurrency": 2}),
    ("XL", 301, None, {"continue_on_error": True, "probe": True, "concurrency": 2}),
]

TIER_NOTES = {
    "S": "串行全量抓取；任一失败即整体失败，不产出半份报告",
    "M": "串行 + 断点续跑；单类目失败跳过，计入 skipped",
    "L": "先探针（每类目 1 请求）判断规模，再抓候选类目明细；并发 2",
    "XL": "只做变化检测：探针全扫 → 按商品数排序 → 取前 max_categories 抓明细",
}


@dataclass
class Plan:
    tier: str
    categories: int
    pairs: list[dict] = field(default_factory=list)
    requests: int = 0
    probe_requests: int = 0
    bytes_estimate: int = 0
    seconds_estimate: int = 0
    continue_on_error: bool = True
    concurrency: int = 1
    notes: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def classify(categories: int) -> str:
    if categories < 1:
        raise ValueError("至少需要 1 个类目")
    for name, low, high, _ in TIERS:
        if categories >= low and (high is None or categories <= high):
            return name
    raise ValueError(f"无法分类的类目数：{categories}")


def tier_config(tier: str) -> dict:
    for name, _, _, behaviour in TIERS:
        if name == tier:
            return behaviour
    raise ValueError(f"未知档位：{tier}")


def estimate(
    pairs: int,
    *,
    topn: int,
    page_size: int,
    tier: str,
    per_request_ms: int = 1500,
    slices: int = 1,
) -> dict:
    """Request count / runtime / size for ``pairs`` (plat, cid) combinations."""
    if page_size < 1:
        raise ValueError("page_size 必须 >= 1")
    pages = max(1, math.ceil(topn / page_size))
    detail = pairs * pages * max(1, slices)
    probe = pairs if tier_config(tier).get("probe") else 0
    total = detail + probe
    concurrency = max(1, tier_config(tier).get("concurrency", 1))
    seconds = int(total * per_request_ms / 1000 / concurrency)
    return {
        "requests": total,
        "detail_requests": detail,
        "probe_requests": probe,
        "seconds": seconds,
        "bytes": int(topn * pairs * 420),
        "concurrency": concurrency,
    }


def build(
    resolved: list[dict],
    config: dict,
    *,
    topn: int,
    page_size: int,
    max_requests: int = 3000,
) -> Plan:
    """Build the plan and refuse categories the tier does not allow."""
    if not resolved:
        raise ValueError("没有解析成功的 (平台, 类目) 组合")

    tier = classify(len(resolved))
    behaviour = tier_config(tier)
    budget = config.get("budget") or {}
    max_categories = int(budget.get("max_categories") or 300)
    if tier == "XL":
        detail = behaviour["probe"]
        limit = int(config.get("fetch", {}).get("max_categories") or 0)
        if limit < 1:
            raise ValueError(
                f"类目数 {len(resolved)} 超过 {max_categories}，XL 档必须显式指定 "
                "fetch.max_categories（只抓前 K 个类目）"
            )
        if limit > max_categories:
            raise ValueError(f"fetch.max_categories 不能大于 budget.max_categories（{max_categories}）")
        del detail

    stats = estimate(
        len(resolved), topn=topn, page_size=page_size, tier=tier, per_request_ms=int(
            config.get("fetch", {}).get("per_request_ms") or 4000
        ),
        slices=len((config.get("fetch") or {}).get("order_by_slices") or ("sale", "sold")),
    )
    if stats["requests"] > max_requests:
        raise ValueError(
            f"预计 {stats['requests']} 个请求，超过 budget.max_requests={max_requests}；"
            "缩小类目/平台、降低 topN 或提高上限后重试"
        )

    return Plan(
        tier=tier,
        categories=len(resolved),
        pairs=resolved,
        requests=stats["requests"],
        probe_requests=stats["probe_requests"],
        bytes_estimate=stats["bytes"],
        seconds_estimate=stats["seconds"],
        continue_on_error=bool(behaviour["continue_on_error"]),
        concurrency=int(behaviour["concurrency"]),
        notes=TIER_NOTES[tier],
    )


def describe(plan: Plan) -> str:
    minutes = plan.seconds_estimate / 60
    return (
        f"档位 {plan.tier}（{plan.categories} 个 平台×类目）：{plan.notes}\n"
        f"预计 {plan.requests} 个请求（其中探针 {plan.probe_requests}）、"
        f"约 {minutes:.1f} 分钟、落盘约 {plan.bytes_estimate / 1e6:.1f} MB"
    )
