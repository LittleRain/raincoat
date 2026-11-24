"""官方福袋线索：仓库 JSON 的读写与校验。

线索一条 = 一个 IP。它是订阅而不是待办：status 只有 active/paused，
抓取结果只写 lastRunId / lastResult / lastHitAt，不改 status。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from .common import BAG_LEADS_FILE, now_iso

IP_TYPES = {"game", "toy", "anime", "other"}
PRIORITIES = {"P0", "P1", "P2"}
STATUSES = {"active", "paused"}
SCOPES = {"cn", "jp", "global"}
RESULTS = {"", "captured", "empty", "blocked", "error", "partial"}

ID_RE = re.compile(r"^lead-[a-z0-9][a-z0-9-]*$")

FIELDS = (
    "id",
    "ip",
    "ipType",
    "publisher",
    "carriers",
    "keywords",
    "channelIds",
    "scope",
    "priority",
    "status",
    "windowHint",
    "lastRunId",
    "lastResult",
    "lastHitAt",
    "source",
    "note",
    "createdAt",
    "updatedAt",
)


def load(path: Path = BAG_LEADS_FILE) -> dict:
    if not path.exists():
        return {"version": 1, "updatedAt": now_iso(), "leads": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("leads", [])
    return data


def save(data: dict, path: Path = BAG_LEADS_FILE) -> None:
    data["updatedAt"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def blank(lead_id: str = "") -> dict:
    return {
        "id": lead_id,
        "ip": "",
        "ipType": "game",
        "publisher": "",
        "carriers": [],
        "keywords": [],
        "channelIds": [],
        "scope": "cn",
        "priority": "P2",
        "status": "active",
        "windowHint": "",
        "lastRunId": "",
        "lastResult": "",
        "lastHitAt": "",
        "source": "manual",
        "note": "",
        "createdAt": now_iso(),
        "updatedAt": now_iso(),
    }


def validate(lead: dict, channel_ids: set[str] | None = None) -> list[str]:
    """返回错误列表；空列表表示合法。"""
    errors: list[str] = []
    lead_id = str(lead.get("id") or "")
    if not ID_RE.match(lead_id):
        errors.append("id 必须形如 lead-<小写字母数字与连字符>")
    if not str(lead.get("ip") or "").strip():
        errors.append("ip 不能为空")
    if str(lead.get("ipType") or "") not in IP_TYPES:
        errors.append(f"ipType 只能是 {'/'.join(sorted(IP_TYPES))}")
    if not str(lead.get("publisher") or "").strip():
        errors.append("publisher 不能为空")
    carriers = lead.get("carriers")
    if not isinstance(carriers, list) or not carriers:
        errors.append("carriers 至少一个载体词")
    else:
        for carrier in carriers:
            if not isinstance(carrier, str) or not carrier.strip():
                errors.append("carriers 里不能有空值")
                break
    if str(lead.get("scope") or "cn") not in SCOPES:
        errors.append(f"scope 只能是 {'/'.join(sorted(SCOPES))}")
    if str(lead.get("priority") or "") not in PRIORITIES:
        errors.append(f"priority 只能是 {'/'.join(sorted(PRIORITIES))}")
    if str(lead.get("status") or "") not in STATUSES:
        errors.append(f"status 只能是 {'/'.join(sorted(STATUSES))}")
    if str(lead.get("lastResult") or "") not in RESULTS:
        errors.append("lastResult 取值不合法")
    channel_ids = channel_ids or set()
    unknown = [cid for cid in (lead.get("channelIds") or []) if cid not in channel_ids]
    if unknown:
        errors.append(f"引用了不存在的渠道：{', '.join(unknown)}")
    keywords = lead.get("keywords") or []
    if not isinstance(keywords, list):
        errors.append("keywords 必须是数组")
    return errors


def normalize(lead: dict) -> dict:
    """只保留下游用得到的字段，避免外部输入塞进随机键。"""
    out = {key: lead.get(key) for key in FIELDS if key in lead}
    for key in ("carriers", "keywords", "channelIds"):
        value = out.get(key)
        if isinstance(value, str):
            value = [x.strip() for x in value.replace("，", ",").split(",") if x.strip()]
        if not isinstance(value, list):
            value = []
        out[key] = [str(x).strip() for x in value if str(x).strip()]
    for key in ("ip", "publisher", "windowHint", "note", "source"):
        out[key] = str(out.get(key) or "").strip()
    out["ipType"] = str(out.get("ipType") or "game")
    out["scope"] = str(out.get("scope") or "cn")
    out["priority"] = str(out.get("priority") or "P2")
    out["status"] = str(out.get("status") or "active")
    return out


def upsert(lead: dict, channel_ids: set[str] | None = None, path: Path = BAG_LEADS_FILE) -> dict:
    data = load(path)
    incoming = normalize(lead)
    existing = next((row for row in data["leads"] if row.get("id") == incoming.get("id")), None)
    if existing:
        merged = {**existing, **incoming, "createdAt": existing.get("createdAt") or now_iso()}
    else:
        merged = {**blank(), **incoming}
    errors = validate(merged, channel_ids)
    if errors:
        raise ValueError("；".join(errors))
    merged["updatedAt"] = now_iso()
    if existing:
        index = data["leads"].index(existing)
        data["leads"][index] = merged
    else:
        data["leads"].append(merged)
    save(data, path)
    return merged


def remove(lead_id: str, path: Path = BAG_LEADS_FILE) -> bool:
    data = load(path)
    before = len(data["leads"])
    data["leads"] = [row for row in data["leads"] if row.get("id") != lead_id]
    if len(data["leads"]) == before:
        return False
    save(data, path)
    return True


def stats(leads: list[dict], channels: list[dict]) -> dict:
    from datetime import datetime, timedelta

    dead = {row.get("id") for row in channels if row.get("status") == "dead"}
    today = datetime.now().date()
    counts = {
        "total": len(leads),
        "active": sum(1 for row in leads if row.get("status") == "active"),
        "paused": sum(1 for row in leads if row.get("status") == "paused"),
        "P0": sum(1 for row in leads if row.get("priority") == "P0"),
        "P1": sum(1 for row in leads if row.get("priority") == "P1"),
        "P2": sum(1 for row in leads if row.get("priority") == "P2"),
        "noChannel": sum(1 for row in leads if not row.get("channelIds")),
        "deadChannel": sum(1 for row in leads if dead & set(row.get("channelIds") or [])),
        "stale": 0,
        "emptyStreak": 0,
    }
    for row in leads:
        last = str(row.get("lastHitAt") or row.get("updatedAt") or "")[:10]
        try:
            if last and (today - datetime.strptime(last, "%Y-%m-%d").date()) > timedelta(days=30):
                counts["stale"] += 1
        except ValueError:
            counts["stale"] += 1
        if row.get("lastResult") == "empty":
            counts["emptyStreak"] += 1
    return counts
