"""游戏虚拟道具的来源配置：发现源（版号/榜单/发行商）与渠道等级。

一个文件两段：
  - discovery / thresholds：怎么发现新游戏、什么门槛算「值得跟踪」；
  - channels：发行商官方渠道与可信等级（A/B/C/D），验收层按它判官方性。

tier 口径与官方福袋一致：
  A 官方商城/官网/充值中心  可自动采信
  B 官方社媒/社区公告       需正文含商品名、面额与价格
  C 应用商店内购页          需双源一致或人工确认
  D 游戏内/需登录/线下      只能人工录入
"""

from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path

from .common import VG_SOURCES_FILE, fetch_text, now_iso

TIERS = {"A", "B", "C", "D"}
STATUSES = {"confirmed", "pending", "dead"}
TYPES = {"official-site", "official-mall", "official-social", "appstore", "official-ingame"}
CAN_ANSWER = {"name", "price", "denom", "duration", "limit", "channel"}

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def load(path: Path = VG_SOURCES_FILE) -> dict:
    if not path.exists():
        return {"version": 1, "updatedAt": now_iso(), "discovery": {}, "thresholds": {}, "channels": []}
    data = json.loads(path.read_text(encoding="utf-8"))
    data.setdefault("channels", [])
    data.setdefault("discovery", {})
    data.setdefault("thresholds", {})
    return data


def save(data: dict, path: Path = VG_SOURCES_FILE) -> None:
    data["updatedAt"] = now_iso()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def channels(path: Path = VG_SOURCES_FILE) -> list[dict]:
    return load(path)["channels"]


def by_id(path: Path = VG_SOURCES_FILE) -> dict[str, dict]:
    return {row.get("id"): row for row in channels(path)}


def discovery(path: Path = VG_SOURCES_FILE) -> dict:
    return load(path).get("discovery") or {}


def thresholds(path: Path = VG_SOURCES_FILE) -> dict:
    data = (load(path).get("thresholds") or {})
    return {
        "maxNewPerRun": int(data.get("maxNewPerRun") or 10),
        "minReservation": int(data.get("minReservation") or 100000),
        "chartTop": int(data.get("chartTop") or 50),
        "windowDays": int(data.get("windowDays") or 60),
        "publishers": [str(x) for x in (load(path).get("discovery") or {}).get("publishers") or []],
    }


def blank() -> dict:
    return {
        "id": "",
        "publisher": "",
        "channel": "",
        "type": "official-site",
        "tier": "C",
        "url": "",
        "gameScope": [],
        "canAnswer": ["name", "price", "denom"],
        "status": "pending",
        "lastVerified": "",
        "note": "",
    }


def normalize(row: dict) -> dict:
    out = {key: row.get(key) for key in blank() if key in row}
    for key in ("gameScope", "canAnswer"):
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


def validate(row: dict) -> list[str]:
    errors: list[str] = []
    if not ID_RE.match(str(row.get("id") or "")):
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
    unknown = [x for x in (row.get("canAnswer") or []) if x not in CAN_ANSWER]
    if unknown:
        errors.append(f"canAnswer 有不认识的值：{', '.join(unknown)}")
    return errors


def upsert(row: dict, path: Path = VG_SOURCES_FILE) -> dict:
    data = load(path)
    incoming = normalize(row)
    index = next((i for i, item in enumerate(data["channels"]) if item.get("id") == incoming.get("id")), None)
    merged = {**blank(), **incoming} if index is None else {**data["channels"][index], **incoming}
    errors = validate(merged)
    if errors:
        raise ValueError("；".join(errors))
    if index is None:
        data["channels"].append(merged)
    else:
        data["channels"][index] = merged
    save(data, path)
    return merged


def usable(channel: dict) -> bool:
    """参与抓取的渠道：confirmed 且 tier 不是 D；url 可以空（靠搜索结果页验证）。"""
    return channel.get("status") == "confirmed" and channel.get("tier") in {"A", "B", "C"}


def host_of(url: str) -> str:
    try:
        return (urllib.parse.urlparse(url).hostname or "").lower()
    except ValueError:
        return ""


def probe(row: dict, timeout: int = 15) -> dict:
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
