"""渠道表：品牌 → 渠道 → 爬取方式 → 状态。

只有 status=confirmed 的渠道会被抓新品使用；pending 只能在渠道页试抓对齐。
文件在仓库里，跟着 git 走，插件通过 HTTP 改它。
"""

from __future__ import annotations

import json
import re

from .common import CHANNELS_FILE, fetch_text


def load() -> dict:
    if not CHANNELS_FILE.exists():
        return {"brands": []}
    try:
        data = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"brands": []}
    data.setdefault("brands", [])
    return data


def save(data: dict) -> None:
    CHANNELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CHANNELS_FILE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(CHANNELS_FILE)


def confirmed() -> list[dict]:
    return [row for row in load().get("brands", []) if row.get("status") == "confirmed"]


def probe(channel: dict) -> dict:
    """试抓一次：HTTP 状态 + 页面标题 + 前几条可见文本，作为对齐证据。"""
    url = channel.get("url") or ""
    if url.startswith("uid:"):
        return {"ok": False, "error": "manual_channel", "status": 0, "samples": []}
    ok, page, error = fetch_text(url, timeout=20, retries=1)
    if not ok:
        return {"ok": False, "error": error, "status": 0, "samples": []}
    title = ""
    found = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    if found:
        title = re.sub(r"\s+", " ", found.group(1)).strip()[:120]
    samples = []
    for match in re.finditer(r"<(h1|h2|h3|a)[^>]*>(.*?)</\1>", page, re.S | re.I):
        text = re.sub(r"<[^>]+>", "", match.group(2))
        text = re.sub(r"\s+", " ", text).strip()
        if 2 <= len(text) <= 80:
            samples.append(text)
        if len(samples) >= 5:
            break
    return {"ok": True, "error": "", "status": 200, "title": title, "samples": samples}
