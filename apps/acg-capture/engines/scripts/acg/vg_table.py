"""企微「游戏虚拟商品」子表（同一份智能表格的 ty2XMk）读写。

表是唯一真源：没有单独的游戏库，表里的游戏名就是清单；
列由本模块维护（ensure_columns），可重复执行。

9 列（2026-11-18 收敛）：
- 去掉「档位」列：一个商品名只留一行，各面额/渠道的价格全部写进「备注」；
- 「上次核验」已改名「入库日期」；
- 不要「官方价」数字列，价格文本在备注里。
"""

from __future__ import annotations

import json
import re

from .common import (
    CACHE_DIR,
    DOC_URL,
    SHEET_VG,
    VG_FIELDS_CACHE,
    cell_text,
    norm,
    pull_sheet,
    run_wecom,
    txt,
)

COLUMNS: list[dict] = [
    {"title": "游戏", "type": "text"},
    {"title": "商品类型", "type": "single_select", "options": ["充值代币", "月卡", "通行证", "礼包", "其他"]},
    {"title": "商品名", "type": "text"},
    {"title": "购买渠道", "type": "text"},
    {"title": "证据链接", "type": "text"},
    {"title": "原文引用", "type": "text"},
    {"title": "状态", "type": "single_select", "options": ["在售", "预约", "下架", "存疑"]},
    {"title": "入库日期", "type": "date_time"},
    {"title": "备注", "type": "text"},
]

COVER_TYPES = ["充值代币", "月卡", "通行证"]

DEFAULT_RENAME = {
    "文本": "游戏",
    "单选": "商品类型",
    "日期": "入库日期",
    "上次核验": "入库日期",
}
# 官方价（并入备注）、数字（默认列）、档位（并入备注后删除）
DEFAULT_DROP = ["人员", "官方价", "数字", "档位"]

TITLES = [column["title"] for column in COLUMNS]

TYPE_LABEL = {
    "token": "充值代币",
    "monthly": "月卡",
    "pass": "通行证",
    "bundle": "礼包",
    "other": "其他",
}
STATUS_LABEL = {
    "on_sale": "在售",
    "presale": "预约",
    "retired": "下架",
    "suspect": "存疑",
}

PRICE_RE = re.compile(r"(?:官方价\s*)?(\d+(?:\.\d+)?)\s*元（([^）]*)）")
RATIO_RE = re.compile(r"约\s*1\s*元=\s*[\d.]+\s*币")


NUM_PATTERN = r"(\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d{1,6}(?:\.\d{1,2})?)"
UNIT_PATTERN = r"(?:枚|个|颗)"
CANON_RE = re.compile(
    rf"^(?:充值)?\s*{NUM_PATTERN}\s*{UNIT_PATTERN}?\s*([\u4e00-\u9fa5A-Za-z][\u4e00-\u9fa5A-Za-z0-9]{{0,7}})$"
)
PRICE_IN_NAME_RE = re.compile(rf"^{NUM_PATTERN}\s*元\s*(.+)$")
QTY_SUFFIX_RE = re.compile(rf"^(.{{1,12}}?)\s*[x×]\s*{NUM_PATTERN}$")
GIFT_RE = re.compile(r"[（(]\s*(?:额外|再)?赠送[^）)]*[）)]\s*$")

# 这些词出现在「剩下的部分」里就说明它不是币种，而是礼包/卡券/权益
NON_CURRENCY_WORDS = (
    "礼包", "月卡", "周卡", "日卡", "季卡", "年卡", "通行证", "战令", "特权", "会员",
    "礼盒", "箱子", "宝箱", "招募", "装备", "材料", "皮肤", "时装", "角色", "英雄",
    "补给", "特惠", "福袋", "盲盒", "抽奖", "钥匙", "次数", "通行",
)
CURRENCY_HINTS = ("币", "券", "点", "晶", "石", "钻", "玉", "金", "宝")


def _digits(value: str) -> str:
    """面额统一成不带千分位的整数写法。"""
    text = str(value or "").replace(",", "").strip()
    if not text:
        return ""
    try:
        number = float(text)
    except ValueError:
        return text
    return str(int(number)) if number == int(number) else f"{number:g}"


def _is_currency(token: str, currency: str = "") -> bool:
    """判断「数字后面那串」是币种名还是商品品类。"""
    if not token:
        return False
    if currency and token == currency:
        return True
    if any(word in token for word in NON_CURRENCY_WORDS):
        return False
    return len(token) <= 6 and token.endswith(CURRENCY_HINTS)


def canonical_product(name: str, currency: str = "") -> tuple[str, str]:
    """「充值1980枚龙晶」「980创世结晶」「点券x60」→（币种, 面额）；礼包/月卡这类保持原名。

    口径：一个币种一行，不同档位只是面额不同，面额与价格都进备注。
    返回 (规范商品名, 面额)。面额为空表示不是按数量卖的代币档。
    """
    raw = str(name or "").strip()
    text = raw.replace(" ", "")
    if not text:
        return "", ""
    # 「6800NZ点（赠送288NZ点）」：赠送部分不属于面额
    text = GIFT_RE.sub("", text).strip()

    match = PRICE_IN_NAME_RE.match(text)
    if match and any(word in match.group(2) for word in ("礼包", "月卡", "周卡", "日卡", "通行证", "战令", "特权", "会员")):
        # 「30元月卡」「18元日礼包」→ 商品名，价格留在备注
        return match.group(2), ""

    match = QTY_SUFFIX_RE.match(text)
    if match and _is_currency(match.group(1), currency):
        return _canon_token(match.group(1), currency), _digits(match.group(2))

    match = CANON_RE.match(text)
    if not match:
        return raw, ""
    denom, token = _digits(match.group(1)), match.group(2)
    # 「980枚古老梦华」里的「枚」本身就是量的标记，古老梦华这种不带币种字的也认
    explicit_unit = bool(re.match(rf"^(?:充值)?\s*{NUM_PATTERN}\s*{UNIT_PATTERN}", text))
    if not _is_currency(token, currency) and not (
        explicit_unit and not any(word in token for word in NON_CURRENCY_WORDS)
    ):
        # 「98元礼包」「3星必得招募礼包」不是代币，保持原名
        return text, ""
    return _canon_token(token, currency), denom


def _canon_token(token: str, currency: str = "") -> str:
    if currency and currency in token:
        return currency
    return token


def _fields_payload(column: dict) -> dict:
    payload: dict = {"field_type": column["type"]}
    if column["type"] == "single_select":
        payload["property_single_select"] = {
            "is_quick_add": True,
            "options": [{"text": option} for option in column.get("options", [])],
        }
    if column["type"] == "number":
        payload["property_number"] = {"decimal_places": 2, "use_separate": False}
    if column["type"] == "date_time":
        payload["property_date_time"] = {"auto_fill": False, "format": 'yyyy"年"m"月"d"日"'}
    return payload


def list_fields(refresh: bool = False) -> list[dict]:
    if not refresh and VG_FIELDS_CACHE.exists():
        try:
            cached = json.loads(VG_FIELDS_CACHE.read_text(encoding="utf-8"))
            if cached.get("sheet") == SHEET_VG and cached.get("fields"):
                return cached["fields"]
        except (OSError, json.JSONDecodeError):
            pass
    payload = run_wecom(["smartsheet", "fields", "list", "--docid", DOC_URL, "--sheet-id", SHEET_VG])
    fields = payload.get("fields") or []
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        VG_FIELDS_CACHE.write_text(
            json.dumps({"sheet": SHEET_VG, "at": "now", "fields": fields}, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
    except OSError:
        pass
    return fields


def _call_fields(kind: str, columns: list[dict], field_ids: list[str] | None = None) -> dict:
    payload = []
    for index, column in enumerate(columns):
        item = _fields_payload(column)
        if field_ids and index < len(field_ids):
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
            SHEET_VG,
            "--type",
            kind,
            "--fields",
            json.dumps(payload, ensure_ascii=False),
        ]
    )


def ensure_columns() -> dict:
    """把子表调成 9 列；可重复执行（含档位合并进备注、删官方价/档位列）。"""
    fields = list_fields(refresh=True)
    by_title = {txt(field.get("field_title")): field for field in fields}
    actions: list[str] = []

    renames = []
    rename_ids = []
    renamed_to: set[str] = set()
    for old, new in DEFAULT_RENAME.items():
        if new in renamed_to or new in by_title:
            continue
        if old in by_title:
            column = next(item for item in COLUMNS if item["title"] == new)
            renames.append(column)
            rename_ids.append(by_title[old]["field_id"])
            renamed_to.add(new)
            actions.append(f"rename {old} -> {new}")
    if renames:
        _call_fields("update", renames, rename_ids)

    price_field = by_title.get("官方价")
    if price_field:
        actions.append(_migrate_price_to_note())

    # 档位：先合并成「一个商品一行」，再删列
    denom_field = by_title.get("档位")
    if denom_field:
        actions.append(_merge_products_drop_denom())

    # 商品名归一：「充值1980枚龙晶」「1980枚龙晶」都并成「龙晶」一行
    actions.append(_normalize_products())
    actions.append(_dedupe_notes())

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
                SHEET_VG,
                "--type",
                "delete",
                "--fields",
                json.dumps([{"field_id": field["field_id"]}], ensure_ascii=False),
            ]
        )
        actions.append(f"delete {title}")

    fields = list_fields(refresh=True)
    present = {txt(field.get("field_title")) for field in fields}
    missing = [column for column in COLUMNS if column["title"] not in present]
    if missing:
        _call_fields("add", missing)
        actions.append("add " + ", ".join(column["title"] for column in missing))

    fields = list_fields(refresh=True)
    present = {txt(field.get("field_title")) for field in fields}
    absent = [title for title in TITLES if title not in present]
    if absent:
        raise RuntimeError(f"列创建不完整，缺：{', '.join(absent)}")
    return {"ok": True, "actions": actions, "columns": TITLES, "count": len(fields)}


def _select_cell(title: str, value: str) -> list[dict]:
    try:
        fields = list_fields()
    except Exception:  # noqa: BLE001
        return [{"text": value}]
    field = next((item for item in fields if txt(item.get("field_title")) == title), None)
    options = (field or {}).get("property_single_select", {}).get("options", []) or []
    for option in options:
        if txt(option.get("text")) == value:
            return [{"id": option.get("id"), "text": value}]
    return [{"text": value}]


def channel_short(channel: str) -> str:
    text = str(channel or "").strip()
    if not text:
        return "未知渠道"
    if "App Store" in text or "appstore" in text.lower():
        return "App Store"
    return text.replace("（内购项目）", "").strip() or text


def price_text(item: dict) -> str:
    price = item.get("price")
    try:
        value = float(price)
    except (TypeError, ValueError):
        return ""
    if value <= 0:
        return ""
    label = channel_short(item.get("channel") or "")
    denom = str(item.get("denom") or "").strip()
    if denom:
        return f"{denom} 档 {value:g} 元（{label}）"
    return f"{value:g} 元（{label}）"


def product_prices(item: dict) -> list[str]:
    """一个商品的价格条目：优先用 prices[]，否则用单价。"""
    entries = []
    for row in item.get("prices") or []:
        text = price_text(row)
        if text and text not in entries:
            entries.append(text)
    if not entries:
        text = price_text(item)
        if text:
            entries.append(text)
    return entries


def note_with_price(item: dict, existing: str = "") -> str:
    """把价格条目拼进备注：原备注（去掉旧价格段）在前，价格在后。"""
    base = str(existing or "").strip()
    bits = [part for part in re.split(r"[；;]", base) if part.strip()]
    others = [part for part in bits if not part.strip().startswith(("官方价", "档位"))]
    merged = list(others)
    for text in product_prices(item):
        if text not in merged:
            merged.append(text)
    return "；".join(merged)


def _migrate_price_to_note() -> str:
    records = pull_sheet(SHEET_VG)
    payloads = []
    for record in records:
        values = record.get("values") or {}
        if not values:
            continue
        try:
            price = float(values.get("官方价"))
        except (TypeError, ValueError):
            continue
        if price <= 0:
            continue
        existing = txt(values.get("备注"))
        if any(abs(float(p) - price) < 1e-6 for p in PRICE_RE.findall(existing)):
            continue
        channel = txt(values.get("购买渠道"))
        merged = note_with_price({"price": price, "channel": channel}, existing)
        payloads.append({"record_id": record.get("record_id"), "values": {"备注": cell_text(merged)}})
    if payloads:
        update_items(payloads)
    return f"migrate 官方价 -> 备注（{len(payloads)} 行）"


def _group_key(game: str, name: str) -> str:
    return f"{norm(game)}|{norm(name)}"


def _merged_note(rows: list[dict]) -> str:
    """一个商品多行（不同面额）→ 合成一条备注，保留已有的「N 档 X 元」标签。"""
    entries: list[str] = []
    others: list[str] = []
    for row in rows:
        denom = str(row.get("denom") or "").strip()
        note = str(row.get("note") or "")
        has_price = False
        for part in re.split(r"[；;]", note):
            part = part.strip()
            if not part or part.startswith(("官方价", "档位")):
                continue
            if "元（" in part:
                has_price = True
                match = PRICE_RE.search(part)
                if not match:
                    continue
                price = float(match.group(1))
                label = match.group(2)
                if "档" in part:
                    text = part
                elif denom:
                    text = f"{denom} 档 {price:g} 元（{label}）"
                else:
                    text = f"{price:g} 元（{label}）"
                if text not in entries:
                    entries.append(text)
                continue
            if RATIO_RE.search(part):
                part = RATIO_RE.search(part).group(0)
                if any(RATIO_RE.search(item) for item in others):
                    continue
            if part not in others:
                others.append(part)
        if not has_price and denom:
            entries.append(f"{denom} 档（价格未记录）")
    return "；".join(others + entries)


def _merge_products_drop_denom() -> str:
    """把同游戏同商品名的多行合并成一行，价格全部写进备注；返回说明。"""
    records = pull_sheet(SHEET_VG)
    groups: dict[str, list[dict]] = {}
    for record in records:
        values = record.get("values") or {}
        game = txt(values.get("游戏"))
        name = txt(values.get("商品名"))
        if not game or not name:
            continue
        groups.setdefault(_group_key(game, name), []).append(
            {
                "recordId": record.get("record_id"),
                "denom": txt(values.get("档位")),
                "channel": txt(values.get("购买渠道")),
                "note": txt(values.get("备注")),
            }
        )

    updates = []
    deletes = []
    merged_rows = 0
    for rows in groups.values():
        keep = rows[0]
        merged = _merged_note(rows)
        if merged and merged != keep["note"]:
            updates.append({"record_id": keep["recordId"], "values": {"备注": cell_text(merged)}})
        for row in rows[1:]:
            if row.get("recordId"):
                deletes.append(row["recordId"])
                merged_rows += 1
    if updates:
        update_items(updates)
    if deletes:
        delete_items(deletes)
    return f"merge 同商品多档 -> 备注（{len(groups)} 个商品，合并删除 {merged_rows} 行）"


def _normalize_products() -> str:
    """把「充值N枚X」「N枚X」这类名字归一成 X，并把同游戏同 X 的多行合并。"""
    records = pull_sheet(SHEET_VG)
    groups: dict[str, list[dict]] = {}
    for record in records:
        values = record.get("values") or {}
        game = txt(values.get("游戏"))
        name = txt(values.get("商品名"))
        if not game or not name:
            continue
        canon, denom = canonical_product(name)
        key = _group_key(game, canon)
        groups.setdefault(key, []).append(
            {
                "recordId": record.get("record_id"),
                "game": game,
                "origName": name,
                "canon": canon,
                "denom": denom,
                "type": txt(values.get("商品类型")),
                "channel": txt(values.get("购买渠道")),
                "note": txt(values.get("备注")),
            }
        )

    updates = []
    deletes = []
    changed = 0
    for rows in groups.values():
        keep = rows[0]
        merged = _merged_note(rows)
        values: dict = {}
        if keep["origName"] != keep["canon"]:
            values["商品名"] = cell_text(keep["canon"])
        if keep["denom"] and keep["type"] != "充值代币":
            values["商品类型"] = _select_cell("商品类型", "充值代币")
        if merged and merged != keep["note"]:
            values["备注"] = cell_text(merged)
        if values:
            updates.append({"record_id": keep["recordId"], "values": values})
            changed += 1
        for row in rows[1:]:
            if row.get("recordId"):
                deletes.append(row["recordId"])
    if updates:
        update_items(updates)
    if deletes:
        delete_items(deletes)
    return f"normalize 商品名（改名 {changed} 个，合并删除 {len(deletes)} 行）"


LABELED_PRICE_RE = re.compile(r"^(\d{1,6})\s*档\s*(\d+(?:\.\d+)?)\s*元（([^）]*)）$")
BARE_PRICE_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*元（([^）]*)）$")


def _dedupe_notes() -> str:
    """备注去重：同一价格既有「N 档 X 元」又有裸「X 元」时，只留带档位的那条。"""
    records = pull_sheet(SHEET_VG)
    updates = []
    for record in records:
        values = record.get("values") or {}
        if not values:
            continue
        note = txt(values.get("备注"))
        if not note:
            continue
        parts = [part.strip() for part in re.split(r"[；;]", note) if part.strip()]
        labeled: dict[float, str] = {}
        bare: list[tuple[float, str]] = []
        others: list[str] = []
        for part in parts:
            if "元（" in part:
                price_match = PRICE_RE.search(part)
                value = float(price_match.group(1)) if price_match else 0.0
                if "档" in part and price_match:
                    labeled[value] = part
                elif price_match:
                    bare.append((value, part))
                continue
            if RATIO_RE.search(part):
                ratio = RATIO_RE.search(part).group(0)
                if not any(RATIO_RE.search(item) for item in others):
                    others.append(ratio)
                continue
            others.append(part)
        rebuilt = others + [labeled[key] for key in sorted(labeled, key=float)]
        rebuilt += [part for value, part in bare if value not in labeled]
        # 保序：others 在前，价格按原顺序随后；这里用 dict 去重
        merged = []
        for part in rebuilt:
            if part not in merged:
                merged.append(part)
        text = "；".join(merged)
        if text and text != note:
            updates.append({"record_id": record.get("record_id"), "values": {"备注": cell_text(text)}})
    if updates:
        update_items(updates)
    return f"dedupe 备注价格（{len(updates)} 行）"


def item_values(item: dict) -> dict:
    kind = TYPE_LABEL.get(str(item.get("type") or "other"), "其他")
    status = STATUS_LABEL.get(str(item.get("status") or "on_sale"), "在售")
    return {
        "游戏": cell_text(item.get("game") or ""),
        "商品类型": _select_cell("商品类型", kind),
        "商品名": cell_text(item.get("name") or ""),
        "购买渠道": cell_text(item.get("channel") or ""),
        "证据链接": cell_text(item.get("source") or ""),
        "原文引用": cell_text(item.get("quote") or ""),
        "状态": _select_cell("状态", status),
        "入库日期": str(item.get("capturedAt") or item.get("checkedAt") or "")[:10] or None,
        "备注": cell_text(note_with_price(item, item.get("note") or "")),
    }


def list_items() -> list[dict]:
    records = pull_sheet(SHEET_VG)
    items = []
    for record in records:
        values = record.get("values") or {}
        if not values:
            continue
        items.append(
            {
                "recordId": record.get("record_id") or values.get("record_id"),
                "game": txt(values.get("游戏")),
                "type": txt(values.get("商品类型")),
                "name": txt(values.get("商品名")),
                "channel": txt(values.get("购买渠道")),
                "source": txt(values.get("证据链接")),
                "quote": txt(values.get("原文引用")),
                "status": txt(values.get("状态")),
                "capturedAt": txt(values.get("入库日期")),
                "note": txt(values.get("备注")),
            }
        )
    return items


def known_games(items: list[dict]) -> list[str]:
    seen: dict[str, str] = {}
    for item in items:
        name = str(item.get("game") or "").strip()
        key = norm(name)
        if key and key not in seen:
            seen[key] = name
    return list(seen.values())


def games_from_items(items: list[dict]) -> list[dict]:
    groups: dict[str, dict] = {}
    for item in items:
        name = str(item.get("game") or "").strip()
        if not name:
            continue
        key = norm(name)
        row = groups.setdefault(
            key, {"game": name, "count": 0, "types": {}, "capturedAt": "", "channels": []}
        )
        row["count"] += 1
        kind = str(item.get("type") or "").strip() or "其他"
        row["types"][kind] = row["types"].get(kind, 0) + 1
        captured = str(item.get("capturedAt") or "").strip()[:10]
        if captured and (not row["capturedAt"] or captured < row["capturedAt"]):
            row["capturedAt"] = captured
        channel = str(item.get("channel") or "").strip()
        if channel and channel not in row["channels"]:
            row["channels"].append(channel)
    games = list(groups.values())
    for row in games:
        row["missing"] = [kind for kind in COVER_TYPES if not row["types"].get(kind)]
    games.sort(key=lambda item: (-item["count"], item["game"]))
    return games


def empty_records() -> list[str]:
    records = pull_sheet(SHEET_VG)
    return [
        record.get("record_id")
        for record in records
        if not any(v for v in (record.get("values") or {}).values())
    ]


def add_items(rows: list[dict], reuse: list[str] | None = None) -> dict:
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
                SHEET_VG,
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
                SHEET_VG,
                "--type",
                "add",
                "--key-type",
                "CELL_VALUE_KEY_TYPE_FIELD_TITLE",
                "--records",
                json.dumps(adds, ensure_ascii=False),
            ]
        )
    return result


def update_items(payloads: list[dict]) -> dict:
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
            SHEET_VG,
            "--type",
            "update",
            "--key-type",
            "CELL_VALUE_KEY_TYPE_FIELD_TITLE",
            "--records",
            json.dumps(payloads, ensure_ascii=False),
        ]
    )


def delete_items(record_ids: list[str]) -> dict:
    if not record_ids:
        return {}
    return run_wecom(
        [
            "smartsheet",
            "records",
            "delete",
            "--docid",
            DOC_URL,
            "--sheet-id",
            SHEET_VG,
            "--records",
            json.dumps([{"record_id": rid} for rid in record_ids], ensure_ascii=False),
        ]
    )
