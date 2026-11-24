"""官方福袋渠道：仓库 JSON 的读写、校验与试抓。

tier 表达「这个来源能不能当官方事实」：
  A 自营商城/官网/小程序  可自动采信
  B 官方社媒公告          需正文含名称与价格
  C 平台品牌官旗店        需核验店铺主体，2026-11-17 起允许直接采信（原文命中即可）
  D 游戏内/线下/需登录     只能人工录入
"""

from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path

from .common import BAG_CHANNELS_FILE, fetch_text, now_iso

TIERS = {"A", "B", "C", "D"}
STATUSES = {"confirmed", "pending", "dead"}
TYPES = {
    "official-mall",
    "official-flagship",
    "official-social",
    "official-miniapp",
    "official-site",
    "official-ingame",
}
CAN_ANSWER = {"name", "price", "tier", "items", "window", "limit", "channel"}

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def load(path: Path = BAG_CHANNELS_FILE) -> dict:
    if not path.exists():
        return {"version": 1, "updatedAt": now_iso(), "channels": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("channels", [])
    return data


def save(data: dict, path: Path = BAG_CHANNELS_FILE) -> None:
    data["updatedAt"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def blank() -> dict:
    return {
        "id": "",
        "publisher": "",
        "channel": "",
        "type": "official-site",
        "tier": "C",
        "url": "",
        "ipScope": [],
        "canAnswer": ["name", "price", "window"],
        "status": "pending",
        "lastVerified": "",
        "note": "",
    }


def normalize(row: dict) -> dict:
    out = {key: row.get(key) for key in blank() if key in row}
    for key in ("ipScope", "canAnswer"):
        value = out.get(key)
        if isinstance(value, str):
            value = [x.strip() for x in value.replace("，", ",").split(",") if x.strip()]
        out[key] = [str(x).strip() for x in (value or []) if str(x).strip()]
    for key in ("id", "publisher", "channel", "url", "note", "lastVerified"):
        out[key] = str(out.get(key) or "").strip()
    out["type"] = str(out.get("type") or "official-site")
    out["tier"] = str(out.get("tier") or "C").upper()
    out["status"] = str(out.get("status") or "pending")
    return out


def validate(row: dict, existing_ids: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    channel_id = str(row.get("id") or "")
    if not ID_RE.match(channel_id):
        errors.append("id 必须是小写字母数字与连字符")
    if not str(row.get("publisher") or "").strip():
        errors.append("publisher 不能为空")
    if not str(row.get("channel") or "").strip():
        errors.append("channel 不能为空")
    if str(row.get("tier") or "") not in TIERS:
        errors.append("tier 只能是 A/B/C/D")
    if str(row.get("type") or "") not in TYPES:
        errors.append(f"type 只能是 {'/'.join(sorted(TYPES))}")
    if str(row.get("status") or "") not in STATUSES:
        errors.append("status 只能是 confirmed/pending/dead")
    url = str(row.get("url") or "")
    if url and not url.startswith("http"):
        errors.append("url 必须是 http(s) 地址，留空表示只能人工核对")
    can = [x for x in (row.get("canAnswer") or []) if x not in CAN_ANSWER]
    if can:
        errors.append(f"canAnswer 有不认识的值：{', '.join(can)}")
    return errors


def upsert(row: dict, path: Path = BAG_CHANNELS_FILE) -> dict:
    data = load(path)
    incoming = normalize(row)
    index = next((i for i, item in enumerate(data["channels"]) if item.get("id") == incoming.get("id")), None)
    if index is None:
        merged = {**blank(), **incoming}
    else:
        merged = {**data["channels"][index], **incoming}
    errors = validate(merged)
    if errors:
        raise ValueError("；".join(errors))
    if index is None:
        data["channels"].append(merged)
    else:
        data["channels"][index] = merged
    save(data, path)
    return merged


def remove(channel_id: str, path: Path = BAG_CHANNELS_FILE) -> bool:
    data = load(path)
    before = len(data["channels"])
    data["channels"] = [row for row in data["channels"] if row.get("id") != channel_id]
    if len(data["channels"]) == before:
        return False
    save(data, path)
    return True


def usable(channel: dict) -> bool:
    """参与抓取的渠道：confirmed、tier 不是 D；url 可以空（靠搜索结果页验证）。"""
    return channel.get("status") == "confirmed" and channel.get("tier") in {"A", "B", "C"}


def host_of(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def probe(row: dict, timeout: int = 15) -> dict:
    """试抓：HTTP 状态 + title + 正文样例。url 为空时返回 manual_channel。"""
    url = str(row.get("url") or "")
    if not url.startswith("http"):
        return {"ok": False, "status": 0, "title": "", "samples": [], "error": "manual_channel"}
    ok, text, error = fetch_text(url, timeout=timeout)
    if not ok:
        return {"ok": False, "status": 0, "title": "", "samples": [], "error": error}
    title_match = re.search(r"<title[^>]*>([\s\S]*?)</title>", text, re.I)
    samples: list[str] = []
    for match in re.finditer(r"<(h1|h2|h3|a)[^>]*>([\s\S]*?)</\1>", text, re.I):
        value = re.sub(r"<[^>]+>", " ", match.group(2))
        value = re.sub(r"\s+", " ", value).strip()
        if 2 <= len(value) <= 80:
            samples.append(value)
        if len(samples) >= 5:
            break
    title = re.sub(r"\s+", " ", title_match.group(1)).strip()[:120] if title_match else ""
    return {"ok": True, "status": 200, "title": title, "samples": samples, "error": ""}
