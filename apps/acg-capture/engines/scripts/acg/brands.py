"""抓取品牌源：只维护品牌，品牌从企微「品牌」tab（q979lj）取。

为什么改成读表：渠道是执行细节，品牌才是「要盯谁」的业务事实。表里由运营维护
品牌、发行方、梯队、官方发售渠道，抓取侧不再自己维护一份品牌名单，避免两边漂移。

只取 `地区=中国大陆` 的行（日版品牌走另一个口径）。表读不到时退回 channels.json
里的品牌，保证离线/断网也能算出一份清单。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from .common import WORKFLOW, pull_sheet, txt

SHEET_BRAND = "q979lj"
CACHE = WORKFLOW / "runtime" / "brands.cache.json"
TTL_SECONDS = 6 * 3600
CN = "中国大陆"


def _row(record: dict) -> dict:
    values = record.get("values") or {}
    return {
        "name": txt(values.get("品牌")),
        "publisher": txt(values.get("发行方")),
        "region": txt(values.get("地区")),
        "tier": txt(values.get("关注梯队")),
        "coop": txt(values.get("合作进展")),
        "channels": txt(values.get("官方发售渠道（官网/社媒url）")),
        "status": txt(values.get("2026销售状态")),
    }


def _from_channels_file(region: str) -> list[dict]:
    """兜底：渠道表里的品牌去重。"""
    path = WORKFLOW / "references" / "channels.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    names = []
    for row in data.get("brands", []):
        brand = str(row.get("brand") or "").strip()
        if brand and brand not in names:
            names.append(brand)
    if region == CN:
        # 渠道表里带「日版」后缀的是日本线，别混进大陆清单
        names = [name for name in names if "日版" not in name and "（" not in name]
    return [{"name": name, "publisher": "", "region": region, "tier": "", "coop": "", "channels": "", "status": ""} for name in names]


def load(region: str = CN, refresh: bool = False) -> list[dict]:
    """返回品牌行（去重、保序）。读表失败用缓存，再失败用渠道表兜底。"""
    cached = None
    if CACHE.exists():
        try:
            cached = json.loads(CACHE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached = None
    fresh_enough = bool(cached) and (time.time() - float(cached.get("fetched_at") or 0)) < TTL_SECONDS
    if cached and fresh_enough and not refresh:
        rows = [row for row in cached.get("rows") or [] if row.get("region") == region]
        if rows:
            return rows

    try:
        records = pull_sheet(SHEET_BRAND)
    except Exception:  # noqa: BLE001 - 表不可用只降级，不阻断整轮
        records = []
    rows = [_row(record) for record in records]
    rows = [row for row in rows if row.get("name")]
    if rows:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(
            json.dumps({"fetched_at": time.time(), "rows": rows}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    else:
        rows = list((cached or {}).get("rows") or [])
    picked = [row for row in rows if row.get("region") == region]
    if picked:
        seen = set()
        uniq = []
        for row in picked:
            if row["name"] in seen:
                continue
            seen.add(row["name"])
            uniq.append(row)
        return uniq
    return _from_channels_file(region)


def names(region: str = CN, refresh: bool = False) -> list[str]:
    return [row["name"] for row in load(region, refresh=refresh)]


def resolve(name: str, region: str = CN) -> dict:
    """按名字找品牌行；找不到返回空行（不抛）。"""
    for row in load(region):
        if row["name"] == name:
            return row
    return {"name": name, "publisher": "", "region": region, "tier": "", "coop": "", "channels": "", "status": ""}
