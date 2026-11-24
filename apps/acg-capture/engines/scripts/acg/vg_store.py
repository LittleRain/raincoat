"""App Store 内购页解析（确定性通道，不依赖模型）。

App Store 中国区应用页的「App内购买」区块会逐项公示名称与价格，例如：
  6480创世结晶 ¥648.00  祝福礼包 ¥30.00  珍珠纪行 ¥68.00
这是平台官方公示的 iOS 内购价，作为 C 级来源可单片采信（lane=store）。
官网/游戏内价格可能与之不同，差异写进备注，不在本通道里折算。
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse

from . import vg_table
from .common import fetch_text

# 名称里出现这些词就归到对应类型；先判通行证再判月卡，最后判代币
PASS_WORDS = ("纪行", "通行证", "战令", "勋礼", "勋荣", "荣勋", "频道", "珍珠")
MONTHLY_WORDS = ("月卡", "祝福", "补给凭证", "观测卡", "月相观测")
TOKEN_WORDS = ("结晶", "梦华", "回声", "星声", "月相", "源石", "点券", "钻石", "元宝")

STOP_ITEMS = {"进一步了解", "提供者", "版权"}


def _price(value: str) -> float | None:
    try:
        number = float(str(value).replace(",", "").strip())
    except ValueError:
        return None
    return number if number > 0 else None


def _block(page: str) -> str:
    """取「App内购买」到「进一步了解」之间的片段；取不到就返回整页（宁可多解析也不误判）。"""
    plain = re.sub(r"<[^>]+>", " ", page or "")
    plain = re.sub(r"\s+", " ", plain)
    start = plain.find("App内购买")
    if start < 0:
        return ""
    end = plain.find("进一步了解", start)
    return plain[start:end if end > start else start + 1200]


def parse_items(game: dict, url: str, page: str) -> list[dict]:
    """把一块「名称 ¥价格」文本解析成候选项。名称与面额拆开，quote 保留原文。"""
    block = _block(page)
    if not block:
        return []
    currency = str(game.get("currency") or "")
    items: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for match in re.finditer(r"([^\s¥]{1,40})\s*¥\s*([\d]+(?:\.\d{1,2})?)", block):
        raw_name = match.group(1).strip()
        if not raw_name or raw_name in STOP_ITEMS:
            continue
        price = _price(match.group(2))
        if price is None:
            continue
        quote = f"{raw_name} ¥{match.group(2)}"
        digits = re.match(r"^(\d{1,6})\s*(?:枚|个|颗)?\s*(.*)$", raw_name)
        canon, canon_denom = vg_table.canonical_product(raw_name, currency)
        if digits and currency and currency in raw_name:
            name = currency
            denom = digits.group(1)
            kind = "token"
        elif canon_denom:
            # 未知代币（新游戏没配 currency）也按「数字+币种」归一：1980枚龙晶 → 龙晶/1980
            name, denom, kind = canon, canon_denom, "token"
        elif any(word in raw_name for word in PASS_WORDS):
            name, denom, kind = raw_name, "", "pass"
        elif any(word in raw_name for word in MONTHLY_WORDS):
            name, denom, kind = raw_name, "", "monthly"
        elif any(word in raw_name for word in TOKEN_WORDS):
            # 只有币种词、没有数字面额（如「开采一箱源石」）：是固定礼包，不是可拆档的代币
            name, denom, kind = raw_name, "", "bundle"
        else:
            name, denom, kind = raw_name, "", "bundle"
        key = (name, denom)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "game": game.get("game") or "",
                "type": kind,
                "name": name,
                "denom": denom,
                "price": price,
                "duration": "",
                "limit": "",
                "quote": quote,
                "source": url,
                "channel": "App Store 中国区（内购项目）",
                "lane": "store",
            }
        )
    return items


ITUNES_SEARCH = "https://itunes.apple.com/search"
APP_NOISE = ("攻略", "图鉴", "助手", "模拟器", "壁纸", "百科", "礼包码", "兑换码", "开箱", "助手", "模组", "社区", "计算器", "论坛")


def norm_app_name(value: str) -> str:
    return re.sub(r"[\s·・:：!！?？\-—_/（）()\[\]【】]", "", str(value or "")).lower()


def resolve_app_store(name: str, country: str = "cn") -> str:
    """按游戏名在中国区 App Store 找官方应用，只接受名称完全一致的结果。

    热度榜里很多是 IP 系列名或端游（塞尔达、魔兽、DOTA），iTunes 会返回攻略站、
    图鉴、私服之类的同名 App；这里宁可不解析，也不把别人的 App 当成官方内购页。
    """
    term = str(name or "").strip()
    if not term:
        return ""
    query = urllib.parse.urlencode(
        {"term": term, "country": country, "entity": "software", "limit": "10"}
    )
    ok, text, _error = fetch_text(f"{ITUNES_SEARCH}?{query}", timeout=15, retries=2)
    if not ok:
        return ""
    try:
        results = json.loads(text).get("results") or []
    except ValueError:
        return ""
    key = norm_app_name(term)
    for row in results:
        track = str(row.get("trackName") or "")
        if norm_app_name(track) != key:
            continue
        if norm_app_name(track).startswith("云"):
            continue
        if any(word in track for word in APP_NOISE):
            continue
        track_id = row.get("trackId")
        if track_id:
            return f"https://apps.apple.com/cn/app/id{track_id}"
    return ""


def collect(game: dict) -> dict:
    """拉一个游戏的 App Store 页并解析；没有配置或抓不到就返回空，不抛。"""
    url = str(game.get("appStore") or "")
    if not url.startswith("http"):
        return {"ok": False, "error": "no_app_store_url", "items": []}
    ok, text, error = fetch_text(url, timeout=25)
    if not ok:
        # App Store 对本机 IP 会限流（http_429）：退避后重试一次，仍失败就如实上报
        if "429" in str(error):
            time.sleep(6)
            ok, text, error = fetch_text(url, timeout=25)
        if not ok:
            return {"ok": False, "error": "rate_limited" if "429" in str(error) else (error or "unreachable"), "items": []}
    items = parse_items(game, url, text)
    return {"ok": bool(items), "error": "" if items else "no_items", "items": items}
