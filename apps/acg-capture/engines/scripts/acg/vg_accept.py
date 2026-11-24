"""游戏虚拟道具候选验收：合并两源、查官方证据、判结论。

判断都在这里；网络只在 _page / _contains。
口径：官方渠道域名 + 原文同时命中「商品名 + 面额/权益 + 价格」才算采信；
应用商店内购页（C 级）需要双源一致；拿不到正文进待确认，不猜价。
"""

from __future__ import annotations

import re

from . import vg_dispatch, vg_table
from .common import fetch_text, host_of, is_secondhand, norm, now_iso, page_contains

TYPE_CODE = {
    "充值代币": "token",
    "代币": "token",
    "token": "token",
    "月卡": "monthly",
    "monthly": "monthly",
    "通行证": "pass",
    "pass": "pass",
    "战令": "pass",
    "礼包": "bundle",
    "bundle": "bundle",
    "其他": "other",
    "other": "other",
}
TYPE_LABEL = {"token": "充值代币", "monthly": "月卡", "pass": "通行证", "bundle": "礼包", "other": "其他"}

PRICE_RE = re.compile(r"(\d{1,5}(?:\.\d{1,2})?)\s*元")
TIME_RE = re.compile(r"(\d{1,3})\s*天")


def _price(value) -> float | None:
    if value in (None, "", "null"):
        return None
    try:
        number = float(str(value).replace(",", "").replace("元", "").strip())
    except ValueError:
        return None
    return number if number > 0 else None


def normalize_candidate(candidate: dict, game: dict, lane: str) -> dict:
    raw_type = str(candidate.get("type") or candidate.get("kind") or "其他").strip()
    type_code = TYPE_CODE.get(raw_type) or TYPE_CODE.get(raw_type.lower()) or "other"
    raw_name = str(candidate.get("name") or candidate.get("sku") or "").strip()
    denom = str(candidate.get("denom") or candidate.get("amount") or "").strip()
    duration = str(candidate.get("duration") or "").strip()
    if not denom and duration:
        denom = duration
    # 「充值1980枚龙晶」这类名字归一成「龙晶」+ 面额 1980，一个商品只留一行
    name, canon_denom = vg_table.canonical_product(raw_name, str(game.get("currency") or ""))
    if canon_denom and not denom:
        denom = canon_denom
    if canon_denom and type_code != "token":
        type_code = "token"
    return {
        "lane": lane,
        "game": str(candidate.get("game") or game.get("game") or "").strip(),
        "gameId": game.get("id"),
        "publisher": game.get("publisher"),
        "type": type_code,
        "typeLabel": TYPE_LABEL[type_code],
        "name": name,
        "denom": denom,
        "price": _price(candidate.get("price")),
        "duration": duration,
        "limit": str(candidate.get("limit") or "").strip(),
        "quote": str(candidate.get("quote") or "").strip(),
        "source": str(candidate.get("source") or candidate.get("url") or "").strip(),
        "channel": str(candidate.get("channel") or "").strip(),
        "status": "pending_review",
        "reasons": [],
        "confidence": 0.5,
        "checkedAt": now_iso(),
    }


def product_key(record: dict) -> str:
    """台账判重键：一个游戏下一个商品名只留一行（各档位价格都进备注）。"""
    return "|".join([norm(record.get("game") or ""), norm(record.get("name") or "")])


def merge_key(record: dict) -> str:
    """合并候选时的键：同一商品不同面额先各自验收，再合成一行。"""
    return "|".join([product_key(record), norm(record.get("denom") or "")])


def key_of(record: dict) -> str:
    return product_key(record)


def combine_products(records: list[dict]) -> list[dict]:
    """把同一商品的多条验收结论合成一行：价格全部收进 prices[]，状态取最保守。"""
    groups: dict[str, dict] = {}
    for record in records:
        key = product_key(record)
        group = groups.get(key)
        if group is None:
            group = {**record, "prices": [], "notes": [], "reasons": list(record.get("reasons") or [])}
            groups[key] = group
        if record.get("price"):
            entry = {
                "price": record["price"],
                "channel": record.get("channel") or "",
                "denom": record.get("denom") or "",
            }
            if entry["price"] not in [row["price"] for row in group["prices"]]:
                group["prices"].append(entry)
        if record.get("note"):
            for part in str(record["note"]).split("；"):
                if part and part not in group["notes"]:
                    group["notes"].append(part)
        if len(str(record.get("quote") or "")) > len(str(group.get("quote") or "")):
            group["quote"] = record.get("quote") or ""
            group["source"] = record.get("source") or group.get("source")
        if not group.get("channel") and record.get("channel"):
            group["channel"] = record["channel"]
        statuses = {group.get("status"), record.get("status")}
        if "accepted" in statuses and group.get("status") != "rejected":
            group["status"] = "accepted"
        elif "pending_review" in statuses:
            group["status"] = "pending_review"
        if record.get("reasons"):
            for reason in record["reasons"]:
                if reason not in group["reasons"]:
                    group["reasons"].append(reason)
    out = []
    for group in groups.values():
        group["note"] = "；".join(group.get("notes") or [])
        group.pop("notes", None)
        out.append(group)
    return out


def merge(candidates: list[dict]) -> list[dict]:
    merged: dict[str, dict] = {}
    for candidate in candidates:
        key = merge_key(candidate)
        current = merged.get(key)
        if not current:
            merged[key] = {**candidate, "lanes": {candidate["lane"]}}
            continue
        current["lanes"].add(candidate["lane"])
        current["lane"] = "both" if len(current["lanes"]) > 1 else candidate["lane"]
        if not current.get("price") and candidate.get("price"):
            current["price"] = candidate["price"]
        if len(candidate.get("quote") or "") > len(current.get("quote") or ""):
            current["quote"] = candidate["quote"]
            current["source"] = candidate["source"] or current.get("source")
        if not current.get("limit") and candidate.get("limit"):
            current["limit"] = candidate["limit"]
        if not current.get("channel") and candidate.get("channel"):
            current["channel"] = candidate["channel"]
    # lanes 内部用 set 合并，落盘前转成可 JSON 化的数组
    return [
        {**row, "lanes": sorted(row.get("lanes") or [], key=str)}
        for row in merged.values()
    ]


def _page(cache: dict, url: str) -> tuple[bool, str, str]:
    """取正文：直连 HTML；正文太短（SPA/JS 壳）时用 DeepSeek fetch 兜底。"""
    if url in cache:
        return cache[url]
    ok, text, error = fetch_text(url, timeout=20)
    best = text if ok and text.strip() else ""
    if len(best) < 500:
        fetched = vg_dispatch.fetch_page(url)
        if fetched.get("ok") and len(fetched.get("content") or "") > len(best):
            best = fetched["content"]
            error = ""
    cache[url] = (bool(best), best, "" if best else (error or "unreachable"))
    return cache[url]


def _contains(cache: dict, url: str, quote: str) -> tuple[bool, str]:
    ok, _page_text, error = _page(cache, url)
    if not ok:
        return False, f"unreachable:{error}"
    if page_contains(_page_text, quote):
        return True, ""
    fetched = vg_dispatch.fetch_page(url)
    if fetched.get("ok") and page_contains(fetched.get("content") or "", quote):
        return True, ""
    return False, "mismatch"


def _host_matches(host: str, allowed: str) -> bool:
    return bool(host and allowed) and (
        host == allowed or host.endswith("." + allowed) or allowed.endswith("." + host)
    )


def same_publisher(left: str, right: str) -> bool:
    """发行商写成法定全名时也能对上关注名单里的简称。"""
    a, b = norm(left), norm(right)
    return bool(a and b) and (a in b or b in a)


def channel_for(url: str, channels: list[dict]) -> dict | None:
    """命中的官方渠道：取最长域名匹配，避免 apps.apple.com 被 apple.com 顶掉。"""
    host = host_of(url)
    best: dict | None = None
    best_len = -1
    for channel in channels:
        allowed = host_of(str(channel.get("url") or ""))
        if not allowed or not _host_matches(host, allowed):
            continue
        if len(allowed) > best_len:
            best, best_len = channel, len(allowed)
    return best


def _quote_hits(record: dict, game: dict) -> tuple[bool, bool, bool]:
    """返回 (命中商品名, 命中价格, 命中面额/权益)。"""
    quote = record.get("quote") or ""
    text = norm(quote)
    names = [record.get("name") or ""] + [str(x) for x in (game.get("skuHints") or [])]
    name_hit = any(norm(word) and norm(word) in text for word in names)

    price = record.get("price")
    price_hit = bool(PRICE_RE.search(quote))
    if isinstance(price, (int, float)):
        price_hit = str(int(price)) in text or f"{price:g}" in text

    denom = str(record.get("denom") or "")
    denom_hit = bool(denom) and norm(denom) in text
    if not denom_hit:
        digits = re.search(r"\d{1,6}", denom)
        if digits:
            denom_hit = digits.group(0) in text
    if not denom_hit:
        days = TIME_RE.search(denom)
        if days:
            denom_hit = f"{days.group(1)}天" in text
    return name_hit, price_hit, denom_hit


PLATFORM_HOSTS = (
    "apps.apple.com", "store.steampowered.com", "store.playstation.com", "store.ea.com",
    "shop.battlenet.com.cn", "store.epicgames.com", "pay.qq.com", "game.qq.com", "lol.qq.com",
)


def verify(record: dict, game: dict, channels: list[dict], page_cache: dict, policy: str = "strict") -> dict:
    """policy=strict：只认已确认官方渠道（每周例行抓取的口径）。

    policy=open：不做渠道归属判断，只要页面能打开、原文命中商品名+价格、面额自洽就采信，
    渠道与置信度按来源域名分级。用于「按清单把行业里这些游戏的虚拟道具都查一遍」。
    """
    def fail(reason: str, status: str = "rejected") -> dict:
        record["reasons"].append(reason)
        record["status"] = status
        return record

    if not record["name"]:
        return fail("name_missing")
    if norm(game.get("game") or "") not in norm(record["game"] + record["name"]):
        return fail("game_mismatch", "pending_review")
    if not record["source"]:
        return fail("source_missing")
    if is_secondhand(record["source"]):
        return fail("secondhand_forbidden")

    # 1) 渠道：strict 只认该游戏/发行商配置的官方渠道域名；open 只记录来源，不做归属判断
    scopes = set(game.get("gameScope") or [])
    scoped = [
        row
        for row in channels
        if row.get("id") in set(game.get("channelIds") or [])
        or (same_publisher(row.get("publisher"), game.get("publisher")) and row.get("status") == "confirmed")
        or (scopes & set(row.get("gameScope") or []) and row.get("status") == "confirmed")
        # 全局渠道（应用商店内购页，gameScope 为空）对所有游戏可用
        or (not row.get("gameScope") and row.get("status") == "confirmed")
    ]
    channel = channel_for(record["source"], scoped)
    tier = str((channel or {}).get("tier") or "")
    open_policy = policy == "open"
    host = host_of(record["source"])
    if channel is None and open_policy:
        platform = any(host.endswith(item) for item in PLATFORM_HOSTS)
        record["channel"] = record.get("channel") or host or "来源页"
        record["sourceTier"] = "platform" if platform else "third_party"
    elif channel is None:
        if record.get("lane") == "deepseek":
            # DeepSeek 搜到的第三方页（9game / 游民 / 百科…）只能当线索：
            # 直接判废，不占待确认队列，也不再去抓它的页面。
            return fail("deepseek_non_official")
        record["reasons"].append("channel_unverified")
        record["status"] = "pending_review"
    elif not record.get("channel"):
        record["channel"] = str(channel.get("channel") or "")

    # 2) 页面能打开 + 原文命中
    ok, _page_text, error = _page(page_cache, record["source"])
    if not ok:
        if "429" in str(error):
            # 限流不是「来源不可信」，进待确认，下轮重试
            return fail("rate_limited", "pending_review")
        return fail(f"source_unreachable:{error}")
    if not record["quote"]:
        return fail("quote_missing", "pending_review")
    matched, reason = _contains(page_cache, record["source"], record["quote"])
    if not matched and reason == "mismatch" and open_policy:
        # open 口径：模型给的 quote 常是搜索摘要而不是页面原话。
        # 退一步只要求「同一页里同时出现商品名和价格」——价格仍必须在来源页上，不接受凭空的数。
        ok_page, page_text, _error = _page(page_cache, record["source"])
        name_hit, price_hit, denom_hit = _quote_hits(record, game)
        page_norm = norm(page_text)
        price_ok = bool(record.get("price")) and (
            str(int(record["price"])) in page_norm or f"{record['price']:g}" in page_norm
        ) if record.get("price") else False
        denom_ok = not record.get("denom") or norm(record.get("denom") or "").replace(" ", "") in page_norm
        name_ok = any(norm(word) and norm(word) in page_norm for word in [record.get("name") or ""] + [str(x) for x in (game.get("skuHints") or [])])
        if ok_page and name_ok and price_ok and denom_ok:
            # reasons 只放「拦住这条」的原因，证据不足另行留痕，否则会把自己判成待确认
            record["evidence"] = "page_name_price"
        else:
            return fail("quote_unverified", "pending_review")
    elif not matched:
        if reason == "mismatch":
            return fail("quote_unverified", "pending_review")
        return fail("source_unreachable")

    # 3) 商品名 / 面额 / 价格三件套
    name_hit, price_hit, denom_hit = _quote_hits(record, game)
    if not name_hit:
        return fail("name_mismatch", "pending_review")
    if not record.get("price"):
        return fail("price_missing", "pending_review")
    if not price_hit:
        return fail("price_conflict", "pending_review")
    # 档位只在代币上强制（面额是拆赏的关键）；月卡/通行证用商品名 + 价格即可
    if record["type"] == "token" and not denom_hit:
        return fail("denom_missing", "pending_review")

    # 4) 代币折算自洽：面额/价格 = 1 元兑多少币；比例 <1 说明面额与价格对不上
    note_bits = []
    if record["type"] == "token":
        digits = re.search(r"\d{1,6}", record.get("denom") or "")
        denom_value = int(digits.group(0)) if digits else 0
        if denom_value and record["price"]:
            ratio = denom_value / record["price"]
            if ratio < 1:
                return fail("ratio_conflict", "pending_review")
            note_bits.append(f"约 1 元={round(ratio, 2):g} 币")

    # 5) 等级：A/B 可直接采信；C 级（应用商店内购页）要双源一致；D 级只能人工
    #    open 口径不按渠道等级卡，改按来源域名给置信度：平台商店 0.9、其它公开页 0.72
    if open_policy:
        base = 0.9 if record.get("sourceTier") == "platform" else 0.72
    else:
        if tier == "C" and record.get("lane") not in ("both", "store"):
            record["reasons"].append("c_tier_single_lane")
        if tier == "D":
            record["reasons"].append("d_tier_manual")
        base = 0.95 if tier in ("A", "B") else 0.85 if tier == "C" else 0.8
    if record.get("lane") == "both":
        base = min(0.99, base + 0.03)
    record["confidence"] = round(max(0.5, base), 2)
    if record.get("limit"):
        note_bits.append(record["limit"])
    record["note"] = "；".join(note_bits)
    record["status"] = "pending_review" if record["reasons"] else "accepted"
    return record


APP_STORE_RE = re.compile(r"apps\.apple\.com/[a-z]{2}/app/[^\"'\s]*id(\d+)")


def app_store_url(candidate: dict) -> str:
    """从 appStore 字段或 source/url 里还原中国区商店页；没有就空串。"""
    for key in ("appStore", "app_store", "storeUrl", "source", "url"):
        match = APP_STORE_RE.search(str(candidate.get(key) or ""))
        if match:
            return f"https://apps.apple.com/cn/app/id{match.group(1)}"
    return ""


def chart_rank(candidate: dict) -> int:
    """把「畅销榜第 12 名」/「12」这类写法归一成名次；没有名次返回 0。"""
    raw = candidate.get("chart") or candidate.get("chartRank") or candidate.get("rank")
    match = re.search(r"\d{1,3}", str(raw or ""))
    return int(match.group(0)) if match else 0


def filter_new_games(
    candidates: list[dict], known_games: list[str], thresholds: dict
) -> tuple[list[dict], list[dict]]:
    """热门游戏候选：候选去重 + 热度门槛 + 每轮上限。返回 (保留, 丢弃)。

    2026-11-18 起不再区分新老游戏：每轮都把行业里有热度的游戏抓一遍，
    靠台账按「游戏 + 商品名」去重，只补缺的行。热度＝发行商名单 / 预约量 / 榜单名次，
    三条至少命中一条；App Store 页只说明抓得到商品，不算热度。
    """
    kept: list[dict] = []
    dropped: list[dict] = []
    known = {norm(name) for name in (known_games or [])}
    publishers = [str(x) for x in (thresholds.get("publishers") or [])]
    max_new = int(thresholds.get("maxNewPerRun") or 10)
    min_reservation = int(thresholds.get("minReservation") or 100000)
    chart_top = int(thresholds.get("chartTop") or 50)
    seen: set[str] = set()

    for candidate in candidates:
        game = str(candidate.get("game") or candidate.get("name") or "").strip()
        row = {
            "game": game,
            "publisher": str(candidate.get("publisher") or "").strip(),
            "status": str(candidate.get("status") or "").strip() or "已上线",
            "platform": str(candidate.get("platform") or "").strip(),
            "monetization": str(candidate.get("monetization") or "").strip(),
            "license": str(candidate.get("license") or "").strip(),
            "source": str(candidate.get("source") or candidate.get("url") or "").strip(),
            "quote": str(candidate.get("quote") or "").strip(),
            "currency": str(candidate.get("currency") or "").strip(),
            "appStore": app_store_url(candidate),
            "lane": candidate.get("lane") or "deepseek",
            "reservation": candidate.get("reservation"),
        }
        key = norm(game)
        if not game:
            dropped.append({**row, "reason": "name_missing"})
            continue
        if key in seen:
            dropped.append({**row, "reason": "duplicate"})
            continue
        if row["status"] not in ("已上线", "预约", "测试"):
            dropped.append({**row, "reason": "not_launched"})
            continue
        monetization_text = row["monetization"]
        if not any(word in monetization_text for word in ("代币", "月卡", "通行证", "充值", "内购", "礼包")):
            dropped.append({**row, "reason": "no_monetization"})
            continue
        if not row["source"].startswith("http") or is_secondhand(row["source"]):
            dropped.append({**row, "reason": "source_missing"})
            continue
        try:
            reservation = int(float(str(row.get("reservation") or 0)))
        except ValueError:
            reservation = 0
        rank = chart_rank(candidate)
        publisher_hit = bool(row["publisher"]) and any(
            name and (name in row["publisher"] or row["publisher"] in name) for name in publishers
        )
        heat: list[str] = []
        if publisher_hit:
            heat.append("发行商名单")
        if reservation >= min_reservation:
            heat.append(f"预约 {reservation}")
        if rank and rank <= chart_top:
            heat.append(f"榜单第 {rank}")
        if not heat:
            dropped.append({**row, "reason": "threshold_missed"})
            continue
        row["heat"] = heat
        row["chartRank"] = rank
        row["priority"] = "P0" if "发行商名单" in heat and "代币" in monetization_text else "P1"
        seen.add(key)
        kept.append(row)

    kept.sort(key=lambda item: (item["priority"], item["game"]))
    overflow = kept[max_new:]
    for row in overflow:
        dropped.append({**row, "reason": "over_limit"})
    return kept[:max_new], dropped
