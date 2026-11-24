"""企微「官方福袋」表（同一份智能表格的子表 tvZwq0）读写。

表是唯一真源：线索/渠道在仓库 JSON，抓取结果写这里。
列由本模块维护（ensure_columns），改名、加列、删默认列都可重复执行。
"""

from __future__ import annotations

import json

from .common import (
    BAG_FIELDS_CACHE,
    CACHE_DIR,
    DOC_URL,
    SHEET_BAG,
    cell_text,
    pull_sheet,
    run_wecom,
    txt,
)

# 13 列（2026-11-17 用户确认：保留原方案 1–9、12–15）
COLUMNS: list[dict] = [
    {"title": "官方福袋ID", "type": "text"},
    {"title": "IP", "type": "text"},
    {"title": "IP类型", "type": "single_select", "options": ["游戏", "潮玩", "动漫", "其他"]},
    {"title": "发行方", "type": "text"},
    {"title": "官方商品名", "type": "text"},
    {"title": "载体", "type": "single_select", "options": ["福袋", "神秘盒子", "礼盒", "惊喜袋", "盲袋", "其他"]},
    {"title": "载体性质", "type": "single_select", "options": ["官方原称", "等价载体"]},
    {"title": "档位与价格", "type": "text"},
    {"title": "最低官方价", "type": "number"},
    {"title": "证据链接", "type": "text"},
    {"title": "原文引用", "type": "text"},
    {"title": "状态", "type": "single_select", "options": ["官方在售", "已结束", "存疑"]},
    {"title": "置信度", "type": "number"},
]

# 建表时遗留的默认列：能改名复用的改名，其余删掉
DEFAULT_RENAME = {"文本": "官方商品名", "单选": "状态", "数字": "最低官方价"}
DEFAULT_DROP = ["人员", "日期"]

TITLES = [column["title"] for column in COLUMNS]


def _fields_payload(column: dict) -> dict:
    payload: dict = {"field_type": column["type"]}
    if column["type"] == "single_select":
        payload["property_single_select"] = {
            "is_quick_add": True,
            "options": [{"text": option} for option in column.get("options", [])],
        }
    if column["type"] == "number":
        payload["property_number"] = {"decimal_places": 2, "use_separate": False}
    return payload


def list_fields(refresh: bool = False) -> list[dict]:
    if not refresh and BAG_FIELDS_CACHE.exists():
        try:
            cached = json.loads(BAG_FIELDS_CACHE.read_text(encoding="utf-8"))
            if cached.get("sheet") == SHEET_BAG and cached.get("fields"):
                return cached["fields"]
        except (OSError, json.JSONDecodeError):
            pass
    payload = run_wecom(
        ["smartsheet", "fields", "list", "--docid", DOC_URL, "--sheet-id", SHEET_BAG]
    )
    fields = payload.get("fields") or []
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    BAG_FIELDS_CACHE.write_text(
        json.dumps({"sheet": SHEET_BAG, "at": "now", "fields": fields}, ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    return fields


def _call_fields(kind: str, columns: list[dict], field_ids: list[str] | None = None) -> dict:
    payload = []
    for index, column in enumerate(columns):
        item = _fields_payload(column)
        if field_ids and index < len(field_ids):
            # update/delete 用 field_id 定位；改名必须走 new_field_title，
            # 传 field_title 会被当成「按名字找现有列」而跳过（2026-11-17 实测）。
            item["field_id"] = field_ids[index]
            if kind == "update":
                item["new_field_title"] = column["title"]
        else:
            item["field_title"] = column["title"]
        payload.append(item)
    return run_wecom(
        [
            "smartsheet",
            "fields",
            kind,
            "--docid",
            DOC_URL,
            "--sheet-id",
            SHEET_BAG,
            "--type",
            kind,
            "--fields",
            json.dumps(payload, ensure_ascii=False),
        ]
    )


def ensure_columns() -> dict:
    """把子表调成 13 列；可重复执行，返回每一步做了什么。"""
    fields = list_fields(refresh=True)
    by_title = {txt(field.get("field_title")): field for field in fields}
    actions: list[str] = []

    # 1) 默认列改名复用
    renames = []
    rename_ids = []
    for old, new in DEFAULT_RENAME.items():
        if old in by_title and new not in by_title:
            column = next(item for item in COLUMNS if item["title"] == new)
            renames.append(column)
            rename_ids.append(by_title[old]["field_id"])
            actions.append(f"rename {old} -> {new}")
    if renames:
        _call_fields("update", renames, rename_ids)

    # 2) 删掉不需要的默认列（人员 / 日期）
    for title in DEFAULT_DROP:
        field = by_title.get(title)
        if not field:
            continue
        run_wecom(
            [
                "smartsheet",
                "fields",
                "delete",
                "--docid",
                DOC_URL,
                "--sheet-id",
                SHEET_BAG,
                "--type",
                "delete",
                "--fields",
                json.dumps([{"field_id": field["field_id"]}], ensure_ascii=False),
            ]
        )
        actions.append(f"delete {title}")

    # 3) 补缺列
    fields = list_fields(refresh=True)
    present = {txt(field.get("field_title")) for field in fields}
    missing = [column for column in COLUMNS if column["title"] not in present]
    if missing:
        _call_fields("add", missing)
        actions.append("add " + ", ".join(column["title"] for column in missing))

    # 4) 回读校验
    fields = list_fields(refresh=True)
    present = {txt(field.get("field_title")) for field in fields}
    absent = [title for title in TITLES if title not in present]
    if absent:
        raise RuntimeError(f"列创建不完整，缺：{', '.join(absent)}")
    return {"ok": True, "actions": actions, "columns": TITLES, "count": len(fields)}


def _select_cell(title: str, value: str) -> list[dict]:
    try:
        fields = list_fields()
    except Exception:  # noqa: BLE001 - 离线/只读环境拿不到字段时退回文本值
        return [{"text": value}]
    field = next((item for item in fields if txt(item.get("field_title")) == title), None)
    options = (field or {}).get("property_single_select", {}).get("options", []) or []
    for option in options:
        if txt(option.get("text")) == value:
            return [{"id": option.get("id"), "text": value}]
    # 选项还没建好时退回文本，is_quick_add 会自动建选项
    return [{"text": value}]


def bag_values(bag: dict) -> dict:
    """台账条目 → 单元格值。"""
    tiers = bag.get("tiers") or []
    tier_text = "；".join(
        f"{tier.get('price')} 元/{tier.get('items') or '随机'}" for tier in tiers if tier.get("price")
    )
    prices = [tier.get("price") for tier in tiers if isinstance(tier.get("price"), (int, float))]
    raw_status = bag.get("status") or "official"
    status = {
        "official": "官方在售",
        "accepted": "官方在售",
        "retired": "已结束",
        "rejected": "已结束",
        "suspect": "存疑",
        "pending_review": "存疑",
    }.get(raw_status, "存疑")
    ip_type = {"game": "游戏", "toy": "潮玩", "anime": "动漫"}.get(bag.get("ipType") or "", "其他")
    carrier = bag.get("carrier") or "福袋"
    role = "官方原称" if bag.get("role") != "equivalent_carrier" else "等价载体"
    evidence = (bag.get("evidence") or [{}])[0]
    return {
        "官方福袋ID": cell_text(bag.get("id") or ""),
        "IP": cell_text(bag.get("ip") or ""),
        "IP类型": _select_cell("IP类型", ip_type),
        "发行方": cell_text(bag.get("publisher") or ""),
        "官方商品名": cell_text(bag.get("officialName") or ""),
        "载体": _select_cell("载体", carrier),
        "载体性质": _select_cell("载体性质", role),
        "档位与价格": cell_text(tier_text),
        "最低官方价": min(prices) if prices else None,
        "证据链接": cell_text(evidence.get("url") or bag.get("sourceUrl") or ""),
        "原文引用": cell_text(evidence.get("quote") or ""),
        "状态": _select_cell("状态", status),
        "置信度": float(bag.get("confidence") or 0),
    }


def list_bags() -> list[dict]:
    records = pull_sheet(SHEET_BAG)
    bags = []
    for record in records:
        values = record.get("values") or {}
        if not values:
            continue
        bags.append(
            {
                "recordId": values.get("record_id") or record.get("record_id"),
                "id": txt(values.get("官方福袋ID")),
                "ip": txt(values.get("IP")),
                "ipType": txt(values.get("IP类型")),
                "publisher": txt(values.get("发行方")),
                "officialName": txt(values.get("官方商品名")),
                "carrier": txt(values.get("载体")),
                "role": txt(values.get("载体性质")),
                "tiers": txt(values.get("档位与价格")),
                "minPrice": values.get("最低官方价"),
                "evidence": txt(values.get("证据链接")),
                "quote": txt(values.get("原文引用")),
                "status": txt(values.get("状态")),
                "confidence": values.get("置信度"),
            }
        )
    return bags


def empty_records() -> list[str]:
    """建表时留下的空行 record_id，写入时优先复用。"""
    records = pull_sheet(SHEET_BAG)
    return [
        record.get("record_id")
        for record in records
        if not any(v for v in (record.get("values") or {}).values())
    ]


def add_bags(rows: list[dict], reuse: list[str] | None = None) -> dict:
    """rows: [{"values": {...}}]；reuse 给空行 record_id，前 N 条走 update。"""
    if not rows:
        return {}
    result: dict = {}
    reuse = list(reuse or [])
    updates = []
    for index, row in enumerate(rows):
        if index < len(reuse):
            updates.append({"record_id": reuse[index], "values": row["values"]})
    if updates:
        result["updated"] = run_wecom(
            [
                "smartsheet",
                "records",
                "update",
                "--docid",
                DOC_URL,
                "--sheet-id",
                SHEET_BAG,
                "--type",
                "update",
                "--key-type",
                "CELL_VALUE_KEY_TYPE_FIELD_TITLE",
                "--records",
                json.dumps(updates, ensure_ascii=False),
            ]
        )
    adds = rows[len(updates):]
    if adds:
        result["added"] = run_wecom(
            [
                "smartsheet",
                "records",
                "update",
                "--docid",
                DOC_URL,
                "--sheet-id",
                SHEET_BAG,
                "--type",
                "add",
                "--key-type",
                "CELL_VALUE_KEY_TYPE_FIELD_TITLE",
                "--records",
                json.dumps(adds, ensure_ascii=False),
            ]
        )
    return result


def update_bags(payloads: list[dict]) -> dict:
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
            SHEET_BAG,
            "--type",
            "update",
            "--key-type",
            "CELL_VALUE_KEY_TYPE_FIELD_TITLE",
            "--records",
            json.dumps(payloads, ensure_ascii=False),
        ]
    )
