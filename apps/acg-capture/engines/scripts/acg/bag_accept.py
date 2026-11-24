"""官方福袋候选验收：合并两源、查证据、判结论。判断都在这里，网络只在 _page/_fetch。"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import urlparse

from . import bag_dispatch
from .common import fetch_text, host_of, is_secondhand, norm, now_iso, page_contains, today

PRICE_RE = re.compile(r"(\d{2,5})\s*元")
DATE_RE = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})")
CARRIERS = ["福袋", "神秘盒子", "礼盒", "惊喜袋", "盲袋"]


def _slug(value: str, limit: int = 14) -> str:
    text = re.sub(r"[^0-9a-z\u4e00-\u9fff]+", "-", str(value or "").lower())
    return re.sub(r"-+", "-", text).strip("-")[:limit] or "x"


def bag_id(ip: str, name: str) -> str:
    """候选 id：日期 + IP/商品名短 slug + 全名哈希。

    slug 是截断的，同 IP 且名字前 10 个字相同的候选会撞成同一个 id
    （实测一轮 86 条只有 82 个唯一 id），逐条裁决和前端渲染都会认错条目。
    后缀是对完整 ip+name 的短哈希，保证同一天内稳定且唯一。
    """
    digest = hashlib.sha1(f"{ip}\x1f{name}".encode("utf-8")).hexdigest()[:6]
    return f"bag-{today().replace('-', '')}-{_slug(ip, 8)}-{_slug(name, 10)}-{digest}"


def _as_tiers(candidate: dict) -> list[dict]:
    tiers = candidate.get("tiers")
    if not isinstance(tiers, list):
        tiers = []
    out = []
    for tier in tiers:
        if not isinstance(tier, dict):
            continue
        price = tier.get("price")
        try:
            price = int(float(str(price).replace(",", ""))) if price not in (None, "") else None
        except ValueError:
            price = None
        out.append(
            {
                "price": price,
                "items": str(tier.get("items") or "").strip(),
                "quote": str(tier.get("quote") or "").strip(),
                "source": str(tier.get("source") or "").strip(),
            }
        )
    return out


def normalize_candidate(candidate: dict, lead: dict, lane: str, mode: str = "") -> dict:
    tiers = _as_tiers(candidate)
    source = str(candidate.get("source") or "").strip()
    quote = str(candidate.get("quote") or "").strip()
    if not source:
        source = next((tier["source"] for tier in tiers if tier["source"]), "")
    if not quote:
        quote = next((tier["quote"] for tier in tiers if tier["quote"]), "")
    carrier = str(candidate.get("carrier") or "").strip() or "福袋"
    return {
        "lane": lane,
        # sweep = 全网扫街（全量任务 / DeepSeek），channel = 只翻已确认渠道的定向任务
        "mode": str(mode or candidate.get("mode") or "sweep").strip() or "sweep",
        "ip": str(candidate.get("ip") or lead.get("ip") or "").strip(),
        "leadId": lead.get("id"),
        "officialName": str(candidate.get("officialName") or candidate.get("name") or "").strip(),
        "carrier": carrier,
        "role": "equivalent_carrier"
        if str(candidate.get("role") or "").strip() == "equivalent_carrier" or carrier != "福袋"
        else "official_release",
        "tiers": tiers,
        "window": candidate.get("window") if isinstance(candidate.get("window"), dict) else {},
        "channels": candidate.get("channels") if isinstance(candidate.get("channels"), list) else [],
        "limit": str(candidate.get("limit") or "").strip(),
        "aliases": [str(x).strip() for x in (candidate.get("aliases") or []) if str(x).strip()],
        "source": source,
        "quote": quote,
        "confidence": candidate.get("confidence"),
    }


def _page(cache: dict, url: str) -> tuple[bool, str, str]:
    """取正文：直连 HTML；正文太短（SPA/JS 壳）或抓不到时用 DeepSeek fetch 兜底，取更长的一份。"""
    if url in cache:
        return cache[url]
    ok, text, error = fetch_text(url, timeout=20)
    best = text if ok and text.strip() else ""
    if len(best) < 500:
        fetched = bag_dispatch.ds_fetch(url)
        if fetched.get("ok") and len(fetched.get("content") or "") > len(best):
            best = fetched["content"]
            error = ""
    if best:
        cache[url] = (True, best, "")
    else:
        cache[url] = (False, "", error or "unreachable")
    return cache[url]


def _contains(cache: dict, url: str, quote: str) -> tuple[bool, str]:
    """原文命中：先看在缓存正文，不在就再走一次 DeepSeek fetch（JS 渲染页常只有壳）。"""
    ok, page, error = _page(cache, url)
    if not ok:
        return False, f"unreachable:{error}"
    if page_contains(page, quote):
        return True, ""
    fetched = bag_dispatch.ds_fetch(url)
    if fetched.get("ok") and page_contains(fetched.get("content") or "", quote):
        return True, ""
    return False, "mismatch"


def _date_of(value) -> str:
    """把「2021-09-30 24:00」「2026年11月6日」这类写法压成 YYYY-MM-DD；解析不了返回空。"""
    match = DATE_RE.search(str(value or ""))
    if not match:
        return ""
    year, month, day = (int(part) for part in match.groups())
    if not (1 <= month <= 12 and 1 <= day <= 31):
        return ""
    return f"{year:04d}-{month:02d}-{day:02d}"


def _outside_window(candidate: dict, since: str, until: str) -> bool:
    """官方窗口整段落在抓取窗口之外（过期的周年活动、去年的双11）就不该进台账。"""
    window = candidate.get("window") or {}
    start = _date_of(window.get("start"))
    end = _date_of(window.get("end"))
    if end and since and end < since:
        return True
    if start and until and start > until:
        return True
    return False


def _host_allowed(url: str, channel_urls: list[str]) -> bool:
    host = host_of(url)
    if not host:
        return False
    for channel_url in channel_urls:
        allowed = host_of(channel_url)
        if not allowed:
            continue
        if host == allowed or host.endswith("." + allowed) or allowed.endswith("." + host):
            return True
    return False


def _quote_ok(quote: str, carriers: list[str], tiers: list[dict]) -> tuple[bool, bool]:
    """返回 (含载体词, 含价格)。"""
    text = norm(quote)
    carrier_hit = any(norm(word) in text for word in carriers if word)
    prices = [str(tier["price"]) for tier in tiers if tier.get("price")]
    price_hit = any(price in quote for price in prices) if prices else bool(PRICE_RE.search(quote))
    return carrier_hit, price_hit


def verify(candidate: dict, lead: dict, channels: dict[str, dict], page_cache: dict, window: tuple[str, str] | None = None) -> dict:
    record = {
        "id": bag_id(candidate["ip"], candidate["officialName"]),
        "leadId": lead.get("id"),
        "lane": candidate["lane"],
        "modes": candidate.get("modes") or [candidate.get("mode") or "sweep"],
        "ip": candidate["ip"],
        "ipType": lead.get("ipType"),
        "publisher": lead.get("publisher"),
        "officialName": candidate["officialName"],
        "carrier": candidate["carrier"],
        "role": candidate["role"],
        "tiers": candidate["tiers"],
        "window": candidate["window"],
        "channels": candidate["channels"],
        "limit": candidate["limit"],
        "aliases": candidate["aliases"],
        "source": candidate["source"],
        "quote": candidate["quote"],
        "status": "pending_review",
        "reasons": [],
        "confidence": 0.5,
        "decidedBy": "engine",
        "checkedAt": now_iso(),
    }

    def fail(reason: str, status: str = "rejected") -> dict:
        record["reasons"].append(reason)
        record["status"] = status
        return record

    if not candidate["officialName"]:
        return fail("name_missing")
    if norm(lead.get("ip") or "") not in norm(candidate["ip"] + candidate["officialName"]):
        return fail("publisher_mismatch", "pending_review")
    if not candidate["source"]:
        # 轻量任务只要求「商品名称/内容/IP」，经常没有来源 URL：机器既证实不了也证伪不了，
        # 交人工比直接判废更合适（判废会把整批好线索一起丢掉）。
        return fail("source_missing", "pending_review")
    if is_secondhand(candidate["source"]):
        return fail("secondhand_forbidden")
    if window and _outside_window(candidate, window[0], window[1]):
        return fail("out_of_window")

    carriers = list(lead.get("carriers") or ["福袋"])
    if not any(norm(word) in norm(candidate["quote"] + candidate["officialName"]) for word in carriers if word):
        return fail("carrier_missing")

    # 1) 官方页：必须能打开且原文命中（证明官方确实发过这个商品）
    ok, page, error = _page(page_cache, candidate["source"])
    if not ok:
        record["reasons"].append(f"source_unreachable:{error}")
        record["status"] = "rejected"
        return record
    if candidate["quote"]:
        matched, reason = _contains(page_cache, candidate["source"], candidate["quote"])
        if not matched:
            if reason == "mismatch":
                # 页面能打开但正文取不到（JS 渲染页常见）：不判死，交人工确认
                return fail("quote_unverified", "pending_review")
            return fail("source_unreachable")
    # 2) 档位：每档的价格必须在自己引用的页面原文里命中；允许价格来自媒体转述（降置信度）
    tiers = [tier for tier in candidate["tiers"] if tier.get("price")]
    if not tiers:
        return fail("tier_missing", "pending_review")
    price_pages = 0
    for tier in tiers:
        tier_source = tier.get("source") or candidate["source"]
        tier_quote = tier.get("quote") or ""
        if is_secondhand(tier_source):
            return fail("secondhand_forbidden")
        if not tier_quote or str(tier["price"]) not in tier_quote:
            return fail("tier_conflict")
        tier_ok, tier_page, tier_error = _page(page_cache, tier_source)
        if not tier_ok:
            record["reasons"].append(f"tier_source_unreachable:{tier_error}")
            record["status"] = "pending_review"
            return record
        tier_matched, tier_reason = _contains(page_cache, tier_source, tier_quote)
        if not tier_matched:
            if tier_reason == "mismatch":
                return fail("tier_unverified", "pending_review")
            return fail("source_unreachable")
        if host_of(tier_source) == host_of(candidate["source"]):
            price_pages += 1

    # 3) 渠道等级与域名
    lead_channels = [channels[cid] for cid in (lead.get("channelIds") or []) if cid in channels]
    channel_urls = [str(channel.get("url") or "") for channel in lead_channels if channel.get("url")]
    tier_levels = {str(channel.get("tier")) for channel in lead_channels if channel.get("tier")}
    if channel_urls and not _host_allowed(candidate["source"], channel_urls):
        record["reasons"].append("channel_unverified")
        record["status"] = "pending_review"
        return record
    if not channel_urls:
        record["reasons"].append("channel_unverified")

    confidence = 0.95 if tier_levels & {"A", "B"} else 0.85 if "C" in tier_levels else 0.8
    if price_pages < len(tiers):
        confidence -= 0.1  # 价格只有媒体转述，官方页没写
    if candidate["lane"] == "both":
        confidence = min(0.99, confidence + 0.03)
    record["confidence"] = round(max(0.5, confidence), 2)
    if record["reasons"]:
        record["status"] = "pending_review"
    else:
        record["status"] = "accepted"
    return record


def merge(candidates: list[dict]) -> list[dict]:
    """同 IP + 官方商品名 + 年份合并；档位对齐，lane 标 both。

    modes 记这一条是从哪条路找到的：sweep（全量扫街）/ channel（定向翻官方渠道），
    两条路都命中说明证据更硬，界面上可以直接看出来。
    """
    merged: dict[str, dict] = {}
    for candidate in candidates:
        key = f"{norm(candidate['ip'])}|{norm(candidate['officialName'])}"
        current = merged.get(key)
        if not current:
            merged[key] = {**candidate, "lanes": {candidate["lane"]}, "modes": {candidate.get("mode") or "sweep"}}
            continue
        current["lanes"].add(candidate["lane"])
        current["lane"] = "both" if len(current["lanes"]) > 1 else candidate["lane"]
        current["modes"].add(candidate.get("mode") or "sweep")
        known = {(tier["price"], tier["items"]) for tier in current["tiers"]}
        for tier in candidate["tiers"]:
            if (tier["price"], tier["items"]) not in known:
                current["tiers"].append(tier)
        if not current.get("quote") and candidate.get("quote"):
            current["quote"] = candidate["quote"]
            current["source"] = candidate["source"]
    out = []
    for candidate in merged.values():
        item = dict(candidate)
        item["modes"] = sorted(candidate.get("modes") or [])
        item.pop("lanes", None)
        out.append(item)
    return out
