"""企微表格：赏盘 / 子品的读取模型与写入。"""

from __future__ import annotations

import json
import re

from .common import (
    DOC_URL,
    SHEET_PAN,
    SHEET_SUB,
    cell_text,
    num,
    pull_sheet,
    run_wecom,
    txt,
)

LAST_KINDS = {"LAST", "最终赏", "last", "Last", "最终賞"}


def load_pans() -> list[dict]:
    records = pull_sheet(SHEET_PAN)
    pans = []
    for record in records:
        values = record.get("values") or {}
        rid = values.get("record_id") or record.get("record_id")
        pans.append(
            {
                "rid": rid,
                "name": txt(values.get("商品名称")),
                "alias": txt(values.get("商品别名")),
                "brand": txt(values.get("品牌")),
                "ip": txt(values.get("IP")),
                "price": txt(values.get("单抽价")),
                "release": txt(values.get("发售日期")),
                "released": txt(values.get("是否已发售")),
                "channel": txt(values.get("售卖渠道")),
                "updateTime": record.get("update_time") or "",
                "createTime": record.get("create_time") or "",
            }
        )
    return [pan for pan in pans if pan["name"]]


def load_subs() -> list[dict]:
    records = pull_sheet(SHEET_SUB)
    subs = []
    for record in records:
        values = record.get("values") or {}
        links = values.get("关联") or []
        pan_rid = ""
        if isinstance(links, list) and links and isinstance(links[0], dict):
            pan_rid = links[0].get("record_id") or ""
        subs.append(
            {
                "rid": values.get("record_id") or record.get("record_id"),
                "pan_rid": pan_rid,
                "pan_name": txt(values.get("赏盘名称")),
                "kind": txt(values.get("赏别")),
                "name": txt(values.get("子品名称")),
                "alias": txt(values.get("别名")),
                "qty": num(values.get("单套数量")),
                "type": txt(values.get("实物类型")),
                "updateTime": record.get("update_time") or "",
            }
        )
    return subs


def is_last(kind: str) -> bool:
    return (kind or "").strip() in LAST_KINDS


def update_pans(payloads: list[dict]) -> dict:
    """payloads: [{"record_id": "...", "values": {...}}]"""
    if not payloads:
        return {}
    return run_wecom(
        [
            "smartsheet",
            "records",
            "update",
            "--docid",
            DOC_URL,
            "--sheet-id",
            SHEET_PAN,
            "--type",
            "update",
            "--key-type",
            "CELL_VALUE_KEY_TYPE_FIELD_TITLE",
            "--records",
            json.dumps(payloads, ensure_ascii=False),
        ]
    )


def update_subs(payloads: list[dict]) -> dict:
    if not payloads:
        return {}
    return run_wecom(
        [
            "smartsheet",
            "records",
            "update",
            "--docid",
            DOC_URL,
            "--sheet-id",
            SHEET_SUB,
            "--type",
            "update",
            "--key-type",
            "CELL_VALUE_KEY_TYPE_FIELD_TITLE",
            "--records",
            json.dumps(payloads, ensure_ascii=False),
        ]
    )


def add_pans(rows: list[dict]) -> dict:
    """rows: [{"values": {...}}]，值已按单元格格式序列化。"""
    if not rows:
        return {}
    return run_wecom(
        [
            "smartsheet",
            "records",
            "update",
            "--docid",
            DOC_URL,
            "--sheet-id",
            SHEET_PAN,
            "--type",
            "add",
            "--key-type",
            "CELL_VALUE_KEY_TYPE_FIELD_TITLE",
            "--records",
            json.dumps(rows, ensure_ascii=False),
        ]
    )


def add_subs(rows: list[dict]) -> dict:
    """新建子品行（无子品的盘补齐结构时用）。rows: [{"values": {...}}]。"""
    if not rows:
        return {}
    return run_wecom(
        [
            "smartsheet",
            "records",
            "update",
            "--docid",
            DOC_URL,
            "--sheet-id",
            SHEET_SUB,
            "--type",
            "add",
            "--key-type",
            "CELL_VALUE_KEY_TYPE_FIELD_TITLE",
            "--records",
            json.dumps(rows, ensure_ascii=False),
        ]
    )


def sub_values_for_new(pan_rid: str, pan_name: str, prize: dict) -> dict:
    """子品行字段：关联指回赏盘，赏盘名称一并写上（人和公式都按名字找）。

    LAST 固定 1 个、按约定不写单套数量，所以 qty 为空时不落这一列。
    """
    values = {
        "关联": [{"record_id": pan_rid}],
        "赏盘名称": cell_text(pan_name),
        "赏别": cell_text(prize.get("kind") or ""),
        "子品名称": cell_text(prize.get("name") or ""),
    }
    alias = str(prize.get("alias") or "").strip()
    if alias:
        values["别名"] = cell_text(alias)
    count = prize.get("count")
    if isinstance(count, int) and count > 0 and not is_last(prize.get("kind") or ""):
        values["单套数量"] = count
    return values


def price_cell(value: int, currency: str, jp: bool) -> str:
    if currency.upper() == "JPY" or jp:
        return f"{value}円/抽（日版）"
    return f"{value}元/抽"


PRICE_TEXT_RE = re.compile(r"(\d{2,5})\s*(元|円)\s*/?\s*(?:抽|次|回)")


def price_from_text(raw) -> tuple[int, str]:
    """抓新品时 price 是原文里的字符串（如「58元/次」）；只认「数字+元/円+/抽|次|回」这一种写法。"""
    match = PRICE_TEXT_RE.search(str(raw or ""))
    if not match:
        return 0, ""
    return int(match.group(1)), ("JPY" if match.group(2) == "円" else "CNY")


def pan_values_for_new(candidate: dict) -> dict:
    """新盘入库字段：未给的写空/未公布，不编。"""
    price = candidate.get("price")
    if isinstance(price, dict):
        value = price.get("value")
        currency = price.get("currency") or ""
    else:
        value, currency = price_from_text(price)
    jp = "日版" in (candidate.get("name") or "") or "on-line" in (candidate.get("source") or "")
    values = {
        "商品名称": cell_text(candidate.get("name") or ""),
        "品牌": cell_text(candidate.get("brand") or ""),
        "IP": cell_text(candidate.get("ip") or ""),
        "发售日期": cell_text(candidate.get("release") or ""),
        "是否已发售": cell_text("已发售" if candidate.get("stage") == "已发售" else "未发售"),
        "售卖渠道": cell_text(candidate.get("channel") or ""),
        "商品别名": cell_text(candidate.get("alias") or ""),
    }
    if isinstance(value, (int, float)) and int(value) > 0:
        values["单抽价"] = cell_text(price_cell(int(value), currency, jp))
    else:
        values["单抽价"] = cell_text("未公布")
    return values
