"""验收层：把候选变成可写数据。

四道硬门（缺一不写）：
1. 来源可打开
2. 原文能命中 quote
3. 数字与 quote 一致、币种口径正确
4. Σ(各赏，不含 LAST) == 整套抽数

二手平台域名在来源层直接拒；判定不了的绝不静默写入。

「没结果」要分两种，混在一起就会让人对着一个没有数的条目点「采信」（2026-11-17 复盘）：

- ``pending_review``（待确认）= **候选里有值，但页面我们打不开、人打得开**。
  这是唯一值得交给人看的软失败，人打开来源就能裁。
- ``unavailable``（来源未公布）= 候选里压根没有这个值（一番赏预告页只写「全 15 種」的款式数，
  不写每款几个），或者有值但没有来源 URL。人确认不了不存在的东西，不进待确认队列，
  下一轮按表内缺口自动再补。
"""

from __future__ import annotations

import difflib
import json
import re
import unicodedata
from urllib.parse import urlsplit

from .common import fetch_text, fuzzy_contains, is_secondhand, norm, page_contains
from .table import is_last

EMPTY = (None, "", [])

FIELD_LABEL = {"price": "单抽价", "count": "各赏数量", "sub": "子品结构"}

# 硬失败：数据本身有问题（二手、原文对不上、Σ 不平）→ 判废
HARD = {"secondhand_forbidden", "sum_mismatch", "quote_mismatch", "value_mismatch", "duplicate"}
HARD_TEXT = {
    "secondhand_forbidden": "来源是二手平台",
    "sum_mismatch": "各赏相加不等于整套抽数",
    "quote_mismatch": "引用的原文在页面上找不到",
    "value_mismatch": "数字和原文对不上",
    "duplicate": "表里已经有这盘",
}


# 反爬/验证页：微信「环境异常，完成验证后即可继续访问」、微博「访问过于频繁」这类。
# 命中它不是「原文对不上」，而是「我们打不开」——要进待确认，不能判废。
BLOCK_MARKERS = (
    "环境异常",
    "完成验证后即可继续访问",
    "访问过于频繁",
    "请在微信客户端打开",
    "该内容已被发布者删除",
    "此内容因违规无法查看",
)


def _looks_blocked(page: str) -> bool:
    text = _visible_text(page)[:3000]
    return any(marker in text for marker in BLOCK_MARKERS)


def _page(cache: dict, url: str, render=None, ocr=None) -> tuple[bool, str, str]:
    """取一个页面的正文，按 URL 缓存。

    render 是可选的兜底：一番赏台湾代理（oneone.com.tw 这类）是 JS 壳，urllib 只能拿到导航栏，
    或者干脆连接被重置。这时用登录态浏览器渲染一次再判 —— 只换「怎么拿到正文」，
    判定口径（原文命中 + 数字一致）不变。

    验证页（微信「环境异常」）单独判：渲染能拿到真正文就用渲染结果；
    再不行还有 OCR（真浏览器能过验证页，配图里的原文照样读得出来）；
    两样都没有才返回 blocked_page，让验收层记「打不开」而不是「原文找不到」。
    """
    if url in cache:
        return cache[url]
    ok, body, error = fetch_text(url)
    blocked = ok and _looks_blocked(body)
    needs_render = (not ok) or blocked or len(_visible_text(body)) < 400
    if render and needs_render:
        try:
            rendered = render(url) or ""
        except Exception:  # noqa: BLE001 - 渲染失败按原来的失败处理
            rendered = ""
        rendered_text = _visible_text(rendered)
        if rendered and not _looks_blocked(rendered) and (
            blocked or len(rendered_text) >= 200 or len(_visible_text(body)) < 200
        ):
            ok, body, error = True, rendered, ""
            blocked = False
    if blocked:
        ocr_text = _ocr_text(cache, url, ocr)
        if ocr_text:
            ok, body, error = True, ocr_text, ""
            cache[("ocr_page", url)] = True
        else:
            ok, body, error = False, "", "blocked_page"
    cache[url] = (ok, body, error)
    return cache[url]


def _ocr_text(cache: dict, url: str, ocr) -> str:
    """页面配图的 OCR 文本，按 URL 缓存；没配置 OCR 时返回空串。"""
    if not ocr:
        return ""
    key = ("ocr", url)
    if key in cache:
        return cache[key]
    try:
        text = ocr(url) or ""
    except Exception:  # noqa: BLE001 - OCR 失败按「没有图」处理，不影响原有判定
        text = ""
    cache[key] = text
    return text


def _visible_text(page: str) -> str:
    """页面正文（去脚本/样式/标签，全半角归一，空白压平）。"""
    text = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", " ", page or "", flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"[ \t\u3000]+", " ", text)


# 赏别标记：A賞 / B 賞 / 最後賞。用它切「这个赏别那一段」，避免把隔壁行的数字算到自己头上。
KIND_MARK_RE = re.compile(r"(?<![A-Za-z])([A-Z])\s*賞")
LAST_MARK_RE = re.compile(r"(最後賞|最终赏|最终賞|LAST)", re.I)
PAIR_RE = re.compile(r"(\d{1,3})\s*/\s*(\d{1,3})")
TOTAL_MARK_RE = re.compile(r"(合計|合计)")


def _kind_marks(text: str, kind: str) -> list[int]:
    """这个赏别标记在页面上的所有位置。

    页面顶部会有「恭喜來賓…抽中…A賞…」的中奖跑马灯，同一个 A賞 会出现好几次，
    所以不能只认第一个，要全部收齐再判断。
    """
    if is_last(kind):
        return [match.start() for match in LAST_MARK_RE.finditer(text)]
    pattern = re.compile(rf"(?<![A-Za-z]){re.escape(kind.strip())}\s*賞")
    return [match.start() for match in pattern.finditer(text)]


def snap_count(page: str, kind: str, count: int, window: int = 80) -> tuple[bool, str, str]:
    """在页面正文里找到这个赏别那一段，用「剩餘/總數」的總數当证据。

    为什么不让模型的 quote 决定成败：模型会把页面上的「2/2」写成
    「★ 2/2（剩餘/總數）」，一字之差就判「原文对不上」，值其实是对的。

    做法：拿值去页面上找它自己那一行，只在这个赏别标记往后一小段里找数字
    （跑马灯里也有「A賞」，靠窗口长度和「到下一个赏别就停」把那些排除掉）。
    - 找到、且总数与候选一致 → 算核过，证据是页面那一行原文；
    - 找到、但总数对不上 → value_mismatch（真的错了）；
    - 同一赏别在不同位置给出不同的总数 → value_ambiguous（不猜）；
    - 找不到 → value_unverifiable（判不了，不写）。
    返回 (ok, evidence, reason)。
    """
    text = _visible_text(page)
    if not text:
        return False, "", "value_unverifiable"

    totals: dict[int, str] = {}
    for start in _kind_marks(text, kind):
        segment = text[start : start + window]
        stop = len(segment)
        for pattern in (KIND_MARK_RE, LAST_MARK_RE, TOTAL_MARK_RE):
            found = pattern.search(segment, 1)
            if found and found.start() < stop:
                stop = found.start()
        # 表格一行就是一个赏别：先按行切开，跑马灯那种「同一行里只是顺口提了一句 A賞」自然出局
        newline = segment.find("\n")
        if 0 < newline < stop:
            stop = newline
        segment = segment[:stop]
        pair = PAIR_RE.search(segment)
        if not pair:
            continue
        totals.setdefault(int(pair.group(2)), segment[: pair.end()].strip())

    if not totals:
        return False, "", "value_unverifiable"
    if len(totals) > 1:
        return False, " / ".join(str(total) for total in totals), "value_ambiguous"
    total, evidence = next(iter(totals.items()))
    if total != count:
        return False, evidence, "value_mismatch"
    return True, evidence, ""


def _key(reason: str) -> str:
    return str(reason).split(":")[0]


def _hard(reasons) -> bool:
    return any(_key(reason) in HARD for reason in reasons)


def _host(url: str) -> str:
    match = re.match(r"https?://([^/?#]+)", str(url or ""))
    return match.group(1) if match else str(url or "")


# 表里「品牌」列就是赏盘名前缀（163 行都这么写），所以品牌从名字推，不从渠道推。
CN_DIGITS = {"一": "1", "二": "2", "三": "3", "四": "4", "五": "5",
             "六": "6", "七": "7", "八": "8", "九": "9", "十": "10"}

BRANDS = (
    "一番赏", "万花赏", "万画赏", "好物赏", "乐淘赏", "磁力赏", "英雄赏",
    "KAYOU赏", "另物赏", "有赏", "甜梦赏", "集换赏", "天降鸿运", "福赏", "秦赏令",
)


def pan_key(value: str, brand: str = "") -> str:
    """去重键：品牌 + 抹掉噪声后的名字主体。

    噪声 = ×、联动、系列、连接符、结尾括注（「（POTEPOTTE坐姿毛绒系列）」这类描述）。
    品牌先归一到名字前缀，所以「忘川风华录」和「一番赏 × 忘川风华录 联动」是同一盘；
    但「Vol.3」和「第四弹」仍是两盘。
    """
    text = norm(value)
    text = re.sub(r"\([^()]*\)$", "", text)
    # 「第4弹 / 第四弾 / Vol.4」是同一个版本号的不同写法，先归一，否则同盘会被当成两条
    text = re.sub(r"第\s*([0-9]+|[一二三四五六七八九十])\s*[弹弾]",
                  lambda m: "vol." + CN_DIGITS.get(m.group(1), m.group(1)), text)
    text = re.sub(r"vol\.?\s*([0-9]+)", r"vol.\1", text)
    text = re.sub(r"[×x*·・|｜/\\\-《》「」『』]", "", text)
    text = re.sub(r"(联动|系列|特别企划|企划)$", "", text)
    canonical = derive_brand(text, brand)
    core = text
    prefix = norm(canonical)
    if prefix:
        # 品牌词可能在名字尾部（「…系列好物赏」），不只在开头：两边都抹掉才算同一个盘
        core = core.replace(prefix, "", 1) if core.startswith(prefix) else core.replace(prefix, "")
    # 抹掉品牌后，原来的「…系列」可能又落到结尾，再收一次尾
    core = re.sub(r"(联动|系列|特别企划|企划)$", "", core)
    return f"{canonical}|{core}"


def derive_brand(name: str, fallback: str = "") -> str:
    """品牌取赏盘名里的品牌词：前缀优先，其次取最靠右的那个。

    「《王者荣耀》峡影逐风系列好物赏」这类名字品牌在尾部，只认前缀会把它判成 IP，
    于是同一盘换个写法就绕过去重。
    """
    text = norm(name)
    for brand in BRANDS:
        if text.startswith(norm(brand)):
            return brand
    best = ("", -1)
    for brand in BRANDS:
        key = norm(brand)
        at = text.rfind(key)
        if at >= 0 and at > best[1]:
            best = (brand, at)
    return best[0] or fallback


def display_name(name: str, brand: str) -> str:
    """表里 128 行都写「一番赏 X」这种前缀式名字；Agent 常只给 IP 名，这里补齐。"""
    text = (name or "").strip()
    if not text or not brand:
        return text
    if norm(brand) in norm(text):
        return text
    return f"{brand} {text}"


def _as_int(value):
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip().replace(",", "")
        if text.isdigit():
            return int(text)
    return None


def _base_name(value: str) -> str:
    """去掉「（日版）」「（日版·一番赏ONLINE）」这类版本后缀再比，Agent 很少原样复述。"""
    text = norm(value)
    text = re.sub(r"\((日版|大陆版|中国代理版|日版·一番赏online)[^)]*\)$", "", text)
    text = re.sub(r"(日版|大陆版|中国代理版)$", "", text)
    # 日文官方赏名写「賞」，表里写「赏」；不归一就差一个字，相似度掉到 0.86 以下匹配不上
    return text.replace("賞", "赏").replace("獎", "奖")


def match_candidate(pan: dict, candidates: list[dict]) -> dict | None:
    target = _base_name(pan.get("pan", ""))
    alias = _base_name(pan.get("alias", ""))
    best = None
    best_ratio = 0.0
    for candidate in candidates:
        raw = str(candidate.get("pan") or candidate.get("name") or "")
        name = _base_name(raw)
        cand_alias = _base_name(str(candidate.get("alias") or ""))
        if not name:
            continue
        if name == target or (target and (target in name or name in target)):
            return candidate
        if alias and (alias == cand_alias or alias in name or name in alias):
            return candidate
        if alias and cand_alias and (alias in cand_alias or cand_alias in alias):
            return candidate
        ratio = difflib.SequenceMatcher(None, target, name).ratio()
        if ratio > best_ratio:
            best, best_ratio = candidate, ratio
    return best if best_ratio >= 0.86 else None


def match_all(pan: dict, candidates: list[dict]) -> list[dict]:
    """所有命中这条盘的候选。判定与 match_candidate 同一套，只是不短路。

    两条通道（workbuddy 翻页面 / DeepSeek 搜索）可能各答一部分，
    合并后再进同一个验收层，所以这里不能只挑第一条。
    """
    target = _base_name(pan.get("pan", ""))
    alias = _base_name(pan.get("alias", ""))
    matched = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        raw = str(candidate.get("pan") or candidate.get("name") or "")
        name = _base_name(raw)
        if not name:
            continue
        cand_alias = _base_name(str(candidate.get("alias") or ""))
        if (
            name == target
            or (target and (target in name or name in target))
            or (alias and (alias == cand_alias or alias in name or name in alias))
            or (alias and cand_alias and (alias in cand_alias or cand_alias in alias))
            or difflib.SequenceMatcher(None, target, name).ratio() >= 0.86
        ):
            matched.append(candidate)
    return matched


def _has_value(value) -> bool:
    if isinstance(value, dict):
        return _as_int(value.get("value")) is not None
    return value not in (None, "", [], 0)


def _merge_prizes(base: list[dict], extra: list[dict]) -> list[dict]:
    """按赏别合并：同一 kind 取「带 count」的那条，新 kind 追加，LAST 排最后。"""
    by_kind: dict[str, dict] = {}
    for prize in list(base) + list(extra):
        if not isinstance(prize, dict):
            continue
        kind = str(prize.get("kind") or "").strip().upper()
        if not kind:
            continue
        current = by_kind.get(kind)
        if current is None:
            by_kind[kind] = prize
            continue
        if _as_int(current.get("count")) is None and _as_int(prize.get("count")) is not None:
            by_kind[kind] = prize
    return [by_kind[kind] for kind in sorted(by_kind, key=lambda k: (k == "LAST", k))]


def _candidate_lanes(candidate: dict) -> list[str]:
    """一条候选来自哪些通道：派发层写 `lane`，合并后写 `lanes`，两个都要认。"""
    lanes: set[str] = set()
    lane = str(candidate.get("lane") or "").strip()
    if lane:
        lanes.add(lane)
    for name in candidate.get("lanes") or []:
        name = str(name).strip()
        if name:
            lanes.add(name)
    return sorted(lanes)


def merge_candidates(matched: list[dict]) -> dict | None:
    """同一盘的多通道候选互补合并。

    以「赏别最全、有价格」的那条为底，用其它通道补空缺的 price / total / 各赏 count；
    有值的字段一律不覆盖——通道之间不一致时留给验收层按页面原文判，不在这里猜。
    """
    usable = [c for c in matched if isinstance(c, dict)]
    if not usable:
        return None
    if len(usable) == 1:
        single = dict(usable[0])
        lanes = _candidate_lanes(single)
        if lanes:
            single["lanes"] = lanes
        return single
    ranked = sorted(
        usable,
        key=lambda c: (len(c.get("prizes") or []), 1 if _has_value(c.get("price")) else 0),
        reverse=True,
    )
    merged = json.loads(json.dumps(ranked[0], ensure_ascii=False))
    lanes: set[str] = set()
    for candidate in usable:
        lanes.update(_candidate_lanes(candidate))
    if lanes:
        merged["lanes"] = sorted(lanes)
    for other in ranked[1:]:
        if not _has_value(merged.get("price")) and _has_value(other.get("price")):
            merged["price"] = other.get("price")
        if not _has_value(merged.get("total")) and _has_value(other.get("total")):
            merged["total"] = other.get("total")
        merged["prizes"] = _merge_prizes(merged.get("prizes") or [], other.get("prizes") or [])
    return merged


def _verify_price(price: dict, page_cache: dict, render=None, ocr=None) -> dict:
    """核对单抽价。返回 {value, reasons, blocked, dropped}。

    blocked 是「页面我们打不开」的来源明细 —— 只有这种失败才值得交给人。
    """
    result: dict = {"value": None, "reasons": [], "blocked": [], "dropped": []}
    value = _as_int(price.get("value"))
    quote = str(price.get("quote") or "")
    source = str(price.get("source") or "")
    if value is None:
        result["reasons"].append("price_missing")
        result["dropped"].append({"reason": "price_missing"})
        return result
    if is_secondhand(source):
        result["reasons"].append("secondhand_forbidden")
        result["dropped"].append({"reason": "secondhand_forbidden", "source": source})
        return result
    ok, page, error = _page(page_cache, source, render, ocr)
    if not ok:
        result["reasons"].append(f"source_unreachable:{error}")
        result["blocked"].append({"source": source, "error": error or "unreachable"})
        return result
    page_is_ocr = bool(page_cache.get(("ocr_page", source)))
    if not page_contains(page, quote) and not fuzzy_contains(page, quote):
        ocr_text = _ocr_text(page_cache, source, ocr)
        if ocr_text and (page_contains(ocr_text, quote) or fuzzy_contains(ocr_text, quote, 0.8)):
            # 原文只印在配图里（公众号图鉴/海报）：OCR 命中同样是原文，后面的数字校验照旧
            result.setdefault("warnings", []).append("quote_ocr")
            page = ocr_text
            page_is_ocr = True
        elif page_is_ocr:
            # 页面本身就是 OCR 出来的：图里认不出的字不该变成判废理由
            result.setdefault("warnings", []).append("quote_ocr_unreadable")
            return result
        else:
            result["reasons"].append("quote_mismatch")
            result["dropped"].append({"reason": "quote_mismatch", "source": source})
            return result
    if not page_contains(page, quote):
        # 小红书/微博常把同一句话改写或加表情：措辞放宽，但下面仍然核数字
        result.setdefault("warnings", []).append("quote_fuzzy")
    if str(value) not in quote.replace(",", ""):
        result["reasons"].append("value_mismatch")
        result["dropped"].append({"reason": "value_mismatch", "source": source})
        return result
    currency = str(price.get("currency") or "").upper()
    if currency not in ("CNY", "JPY"):
        currency = "JPY" if "円" in quote else ("CNY" if "元" in quote else "")
    if not currency:
        result["reasons"].append("currency_unknown")
        result["dropped"].append({"reason": "currency_unknown", "source": source})
        return result
    result["value"] = {"value": value, "currency": currency, "quote": quote, "source": source}
    return result


STYLE_RE = re.compile(r"全\s*(\d+)\s*[种種]")
PIECES_RE = re.compile(r"共\s*(\d+)\s*[个個]")


def _style_number(quote: str) -> int | None:
    """「全 N 种」里的 N 是款式数，不是一箱里几个。只写款式数时不能拿它当 count。"""
    match = STYLE_RE.search(quote or "")
    return int(match.group(1)) if match else None


def _quote_count_ok(quote: str, count: int) -> bool:
    """原文引用逐字命中之后，还要看引用里的数字对不对得上。

    台湾代理页一行是「A賞 名称 3/5」（剩餘/總數），单套数量应该是 5。
    只验「这段文字在页面上」是不够的：模型把 count 写成 3、引用写「3/5」也会命中，
    所以这里把引用里的数取出来对一遍。

    另外区分「全 N 种」（款式数）与「共 M 个」（一箱里的个数）：
    只有款式数、没有个数时，count 就等于款式数的一律不采信——这是今天最容易写错的一类。
    """
    pair = PAIR_RE.search(quote or "")
    if pair:
        return int(pair.group(2)) == count
    pieces = PIECES_RE.search(quote or "")
    if pieces:
        return int(pieces.group(1)) == count
    bare = re.search(r"(\d+)\s*[个個]", quote or "")
    if bare:
        return int(bare.group(1)) == count
    style = _style_number(quote)
    if style is not None and style == count:
        return False
    return str(count) in (quote or "")


def _style_only(quote: str, count: int) -> bool:
    """是不是「只有款式数、没有任何个数表达」——只有这种情况才当款式数误读。"""
    text = quote or ""
    if PAIR_RE.search(text) or PIECES_RE.search(text) or re.search(r"(\d+)\s*[个個]", text):
        return False
    style = _style_number(text)
    return style is not None and style == count



def _verify_counts(prizes: list[dict], total, page_cache: dict, render=None, ocr=None) -> dict:
    """核对各赏数量。返回 {counts, total, expected, sum_ok, reasons, blocked, dropped}。

    expected = 候选里真的带了数量的赏别数。少一条都不成立：缺一条 Σ 就必然不平，
    所以只要有一条没核实，整条不写，也别拿它当「Σ 不平」判废。
    来源没写整套抽数时，逐条核过的数量仍然成立，只是 Σ 平衡这轮验不了（记 warning）。
    """
    result: dict = {
        "counts": [],
        "total": _as_int(total),
        "expected": 0,
        "sum_ok": False,
        "reasons": [],
        "blocked": [],
        "dropped": [],
    }
    for prize in prizes:
        kind = str(prize.get("kind") or "").strip()
        count = _as_int(prize.get("count"))
        source = str(prize.get("source") or "")
        if not kind or count is None:
            continue
        # LAST / 最终赏固定 1 个、按约定不填单套数量，也不占整套抽数：不验、不算 expected
        if is_last(kind):
            continue
        result["expected"] += 1
        if is_secondhand(source):
            result["reasons"].append("secondhand_forbidden")
            result["dropped"].append({"kind": kind, "reason": "secondhand_forbidden", "source": source})
            continue
        if not source:
            result["reasons"].append(f"source_missing:{kind}")
            result["dropped"].append({"kind": kind, "reason": "source_missing"})
            continue
        ok, page, error = _page(page_cache, source, render, ocr)
        if not ok:
            result["reasons"].append(f"source_unreachable:{kind}")
            result["blocked"].append({"kind": kind, "source": source, "error": error or "unreachable"})
            continue

        quote = str(prize.get("quote") or "")
        verified = None
        if quote and page_contains(page, quote):
            if _quote_count_ok(quote, count):
                verified = {"kind": kind, "count": count, "source": source,
                            "name": prize.get("name_cn") or "", "evidence": quote[:160]}
            else:
                result["reasons"].append(f"value_mismatch:{kind}")
                result["dropped"].append({"kind": kind, "reason": "value_mismatch",
                                          "source": source, "evidence": quote[:160]})
                continue
        elif snap_count(page, kind, count)[0]:
            # 模型的 quote 不逐字命中（常见：它把「2/2」写成「★ 2/2（剩餘/總數）」）：
            # 不谈信任问题，直接拿这个值去页面上找它自己那一行
            _, evidence, _ = snap_count(page, kind, count)
            verified = {"kind": kind, "count": count, "source": source,
                        "name": prize.get("name_cn") or "", "evidence": evidence, "how": "snapped"}

        if verified is None and render:
            # 还没核成：可能只拿到了 JS 壳，正文要渲染之后才出现。
            # 渲染结果按 URL 缓存，所以同一页只会多花一次时间。
            rendered = render(source) or ""
            # 相等说明这一页本来就是渲染结果（_page 里已经渲染过），不用再来一遍
            if rendered and rendered != page:
                if quote and page_contains(rendered, quote) and _quote_count_ok(quote, count):
                    verified = {"kind": kind, "count": count, "source": source,
                                "name": prize.get("name_cn") or "", "evidence": quote[:160],
                                "how": "rendered"}
                else:
                    snapped, evidence, _ = snap_count(rendered, kind, count)
                    if snapped:
                        verified = {"kind": kind, "count": count, "source": source,
                                    "name": prize.get("name_cn") or "", "evidence": evidence,
                                    "how": "rendered"}
                page = rendered

        if verified is None:
            # 正文里没有，但可能印在配图里（公众号图鉴）：OCR 出原文再按同一套口径核
            ocr_text = _ocr_text(page_cache, source, ocr)
            if ocr_text:
                exact = bool(quote) and page_contains(ocr_text, quote)
                loose = bool(quote) and not exact and fuzzy_contains(ocr_text, quote, 0.8)
                if (exact or loose) and _quote_count_ok(quote, count):
                    verified = {"kind": kind, "count": count, "source": source,
                                "name": prize.get("name_cn") or "", "evidence": quote[:160],
                                "how": "ocr"}
                elif exact:
                    # 数字对不上就判废只在「正文逐字命中」时成立。OCR 的数字不可靠
                    # （2↔已、3↔习/彐、8↔日），认错字不该升级成判废，退回「未核实」。
                    result.setdefault("warnings", []).append(f"count_ocr_mismatch:{kind}")
                else:
                    snapped, evidence, _ = snap_count(ocr_text, kind, count)
                    if snapped:
                        verified = {"kind": kind, "count": count, "source": source,
                                    "name": prize.get("name_cn") or "", "evidence": evidence,
                                    "how": "snapped_ocr"}

        if verified:
            result["counts"].append(verified)
            continue

        snapped, evidence, reason = snap_count(page, kind, count)
        result["reasons"].append(f"{reason}:{kind}")
        result["dropped"].append({"kind": kind, "reason": reason, "source": source, "evidence": evidence})

    if result["expected"] and len(result["counts"]) == result["expected"]:
        non_last = sum(p["count"] for p in result["counts"] if not is_last(p["kind"]))
        total_int = result["total"]
        result["sum_ok"] = total_int is None or non_last == total_int
        if total_int is not None and non_last != total_int:
            result["reasons"].append(f"sum_mismatch:{non_last}!={total_int}")
    return result


_SIZE_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:cm|mm|厘米|毫米|米|m)", re.I)


def _name_forms(name: str) -> list[str]:
    """赏名的可接受写法：原样 + 去掉尺寸（「装骨50cm大娃」→「装骨大娃」）。

    模型常把规格写进名字（50cm / 27cm），页面只写名字本体；尺寸不是身份信息，
    去掉后仍然要求逐字命中，不放宽到模糊匹配。
    """
    forms = [name]
    core = _SIZE_RE.sub("", name).strip()
    if core and core != name and len(core) >= 4:
        forms.append(core)
    return forms


def _verify_sub(prizes: list[dict], total, page_cache: dict, render=None, ocr=None) -> dict:
    """核对整套子品结构（sub 缺口）：这个盘表里 0 行子品，要从来源把「赏别 + 赏名」建出来。

    和 _verify_counts 的差别：这里连**名称**一起验，名称必须在来源正文里逐字命中。
    数量有就核、没有就留空 —— 一番赏预告页常常只给「全 N 種」的款式名，
    「结构成立、数量为空」是正确状态，不该因为缺数量把整批赏名丢掉。

    返回 {prizes, total, expected, sum_ok, countsMissing, reasons, blocked, dropped}
    """
    result: dict = {
        "prizes": [],
        "total": _as_int(total),
        "expected": 0,
        "sum_ok": False,
        "countsMissing": 0,
        "reasons": [],
        "blocked": [],
        "dropped": [],
        "warnings": [],
    }
    for prize in prizes:
        kind = str(prize.get("kind") or "").strip()
        if not kind:
            continue
        name = str(prize.get("name_cn") or prize.get("name") or "").strip()
        alias = str(prize.get("alias") or "").strip()
        count = _as_int(prize.get("count"))
        source = str(prize.get("source") or "")
        quote = str(prize.get("quote") or "")
        result["expected"] += 1
        if not name:
            result["reasons"].append(f"name_missing:{kind}")
            result["dropped"].append({"kind": kind, "reason": "name_missing"})
            continue
        if is_secondhand(source):
            result["reasons"].append("secondhand_forbidden")
            result["dropped"].append({"kind": kind, "reason": "secondhand_forbidden", "source": source})
            continue
        if not source:
            result["reasons"].append(f"source_missing:{kind}")
            result["dropped"].append({"kind": kind, "reason": "source_missing"})
            continue
        ok, page, error = _page(page_cache, source, render, ocr)
        if not ok:
            result["reasons"].append(f"source_unreachable:{kind}")
            result["blocked"].append({"kind": kind, "source": source, "error": error or "unreachable"})
            continue

        verified = None
        forms = _name_forms(name)
        if any(page_contains(page, form) for form in forms) or (alias and page_contains(page, alias)):
            verified = {"kind": kind, "name": name, "alias": alias, "count": count,
                        "source": source, "evidence": name}
        elif fuzzy_contains(page, name) or (alias and fuzzy_contains(page, alias)):
            # 小红书笔记多用简称/译名：措辞可放宽，数量仍走下面的 value_mismatch
            verified = {"kind": kind, "name": name, "alias": alias, "count": count,
                        "source": source, "evidence": name, "how": "fuzzy"}
        elif render:
            # 代理页是 JS 壳：渲染一次再找赏名，口径不放宽（仍然只认原文命中）
            rendered = render(source) or ""
            if rendered and rendered != page and any(page_contains(rendered, form) for form in forms):
                verified = {"kind": kind, "name": name, "alias": alias, "count": count,
                            "source": source, "evidence": name, "how": "rendered"}
                page = rendered
        if verified is None:
            # 赏名只印在图里（公众号图鉴）：OCR 命中同样是原文；OCR 会认错字，阈值比正文严
            ocr_text = _ocr_text(page_cache, source, ocr)
            if ocr_text and (
                any(page_contains(ocr_text, form) for form in forms)
                or (alias and page_contains(ocr_text, alias))
                or fuzzy_contains(ocr_text, name, 0.85)
            ):
                verified = {"kind": kind, "name": name, "alias": alias, "count": count,
                            "source": source, "evidence": name, "how": "ocr"}
                page = ocr_text
        if verified is None:
            result["reasons"].append(f"name_unverified:{kind}")
            result["dropped"].append({"kind": kind, "reason": "name_unverified",
                                      "source": source, "evidence": name})
            continue

        if is_last(kind):
            # LAST 固定 1 个、按约定不写单套数量
            verified["count"] = None
        elif count is not None:
            quote_exact = bool(quote) and page_contains(page, quote)
            quote_seen = quote_exact or (bool(quote) and fuzzy_contains(page, quote))
            if quote_seen and _quote_count_ok(quote, count):
                verified["evidence"] = quote[:160]
            elif snap_count(page, kind, count)[0]:
                _, evidence, _ = snap_count(page, kind, count)
                verified["evidence"] = evidence
                verified["how"] = "snapped"
            else:
                # 页面来自 OCR，或者这个赏名是走 OCR 认出来的：两种都算「OCR 证据」
                page_is_ocr = verified.get("how") == "ocr" or bool(page_cache.get(("ocr_page", source)))
                if _style_only(quote, count):
                    # 把「全 N 种」当成了个数：数量作废，但赏名结构仍然成立（结构比数量值钱）
                    verified["count"] = None
                    result["countsMissing"] += 1
                    result["warnings"].append(f"style_number:{kind}")
                elif page_is_ocr or not quote_exact:
                    # 数量「没核到」不等于「数字错了」：
                    # - OCR 认错字（「共3个」读成「共习个」）；
                    # - 或者这段原文压根不在正文/配图里（模型自己拼的数）。
                    # 两种情况都保留赏名结构、数量留空；只有正文逐字命中且数字冲突才判废。
                    verified["count"] = None
                    result["countsMissing"] += 1
                    result["warnings"].append(
                        f"count_ocr_unreadable:{kind}" if page_is_ocr else f"count_unverifiable:{kind}"
                    )
                else:
                    result["reasons"].append(f"value_mismatch:{kind}")
                    result["dropped"].append({"kind": kind, "reason": "value_mismatch",
                                              "source": source, "evidence": quote[:160] or name})
                    continue
        else:
            result["countsMissing"] += 1

        result["prizes"].append(verified)

    if result["expected"] and len(result["prizes"]) == result["expected"]:
        total_int = result["total"]
        if result["countsMissing"]:
            # 有赏别拿不到数量：Σ 这轮验不了，但结构（赏名）成立，仍然可以建行
            result["sum_ok"] = True
        else:
            non_last = sum(p["count"] for p in result["prizes"] if not is_last(p["kind"]))
            result["sum_ok"] = total_int is None or non_last == total_int
            if total_int is not None and non_last != total_int:
                result["reasons"].append(f"sum_mismatch:{non_last}!={total_int}")
    return result


def _field_state(reasons: list[str], blocked: list[dict]) -> str:
    """单个缺口的结论：rejected / pending / unavailable（accepted 由调用方在验过值后自己置）。"""
    if _hard(reasons):
        return "rejected"
    if blocked:
        return "pending"
    return "unavailable"


def _ask_text(record: dict, gaps: list[str]) -> str:
    """一句话说清「这条为什么要人看、要看什么」。空串 = 不需要人处理。"""
    status = record["status"]
    fields = record.get("fields") or {}
    if status == "accepted":
        warnings = record.get("warnings") or []
        if "count_not_published" in warnings:
            return "子品结构按原文逐条核过后建行；来源没写逐赏个数，单套数量这轮留空。"
        if "total_not_published" in warnings:
            return "数量逐条核过原文后写入；来源没写整套抽数，Σ 平衡这轮没法验。"
        return ""
    names = "、".join(FIELD_LABEL.get(gap, gap) for gap in gaps if gap in fields) or "缺口"
    if status == "rejected":
        why = "、".join(
            dict.fromkeys(HARD_TEXT.get(_key(reason), _key(reason)) for reason in record["reasons"] if _key(reason) in HARD)
        )
        return f"{names}：{why}。已判废，不需要你处理。"
    if status == "pending_review":
        parts = []
        for field, state in fields.items():
            if state != "pending":
                continue
            blocks = [b for b in record.get("blocked") or [] if b.get("field") == field]
            hosts = "、".join(sorted({_host(b.get("source")) for b in blocks if _host(b.get("source"))}))
            errors = "、".join(sorted({str(b.get("error")) for b in blocks if b.get("error")}))
            found = (record.get("found") or {}).get(field)
            head = f"{FIELD_LABEL.get(field, field)}：候选里已经有值"
            if found:
                head += f"（{found} 个赏别）"
            parts.append(f"{head}，但 {hosts or '来源'} 打不开（{errors or '网络错误'}），机器核不了原文")
        parts.append("你能打开来源核对，就填 URL 点「采信并写入」；核不了就判废，等下一轮")
        return "；".join(parts)
    parts = []
    for field, state in fields.items():
        if state == "unavailable":
            if field == "sub":
                parts.append("子品结构：来源页没给出这套盘的赏别构成（常见原因：预告期只公开「全 N 種」的款式数）")
                continue
            parts.append(
                f"{FIELD_LABEL.get(field, field)}：来源页没有这个数"
                f"（常见原因：一番赏预告页只写「全 N 種」的款式数，不写每款几个）"
            )
    parts.append("这轮没有可确认的东西，等官方或代理页更新后下一轮会自动再补")
    return "；".join(parts)


def verify_item(item: dict, candidate: dict | None, page_cache: dict, render=None, ocr=None) -> dict:
    gaps = list(item.get("gaps") or [])
    record = {
        # 条目 id 用 pan record_id 派生：重启/重新验收后仍然稳定，前端才能定位到它
        "id": item.get("id") or (f"i-{item['panRecordId']}" if item.get("panRecordId") else None),
        "pan": item["pan"],
        "panRecordId": item.get("panRecordId"),
        "brand": item.get("brand", ""),
        "gap": "+".join(gaps),
        "status": "unavailable",
        "reasons": [],
        "warnings": [],
        # 逐字段结论：前端据此决定「能不能点采信」和要人看什么
        "fields": {gap: "unavailable" for gap in gaps},
        # 打不开的来源（进待确认的依据）与有值但没验过的来源（说明为什么没写）
        "blocked": [],
        "dropped": [],
        "found": {},
        "ask": "",
        "price": None,
        "counts": None,
        "subs": None,
        "total": None,
        "candidate": candidate or {},
    }
    if not candidate:
        record["reasons"] = ["no_candidate"]
        record["ask"] = "本轮没拿到这条的候选（模型没返回或没对上盘名）。这轮不需要你确认，下一轮会自动再补。"
        return record

    if "price" in gaps:
        price_candidate = candidate.get("price") or {}
        if _as_int(price_candidate.get("value")) is None:
            record["reasons"].append("price_not_published")
            record["dropped"].append({"field": "price", "reason": "price_not_published"})
        else:
            result = _verify_price(price_candidate, page_cache, render, ocr)
            record["reasons"].extend(result["reasons"])
            record["warnings"].extend(result.get("warnings") or [])
            record["blocked"].extend({**entry, "field": "price"} for entry in result["blocked"])
            record["dropped"].extend({**entry, "field": "price"} for entry in result["dropped"])
            record["fields"]["price"] = _field_state(result["reasons"], result["blocked"])
            if result["value"]:
                record["price"] = result["value"]
                record["fields"]["price"] = "accepted"

    if "count" in gaps:
        result = _verify_counts(candidate.get("prizes") or [], candidate.get("total"), page_cache, render, ocr)
        record["found"]["count"] = result["expected"]
        record["reasons"].extend(result["reasons"])
        record["warnings"].extend(result.get("warnings") or [])
        record["blocked"].extend({**entry, "field": "count"} for entry in result["blocked"])
        record["dropped"].extend({**entry, "field": "count"} for entry in result["dropped"])
        if not result["expected"]:
            record["reasons"].append("count_not_published")
            record["dropped"].append({"field": "count", "reason": "count_not_published"})
        elif result["sum_ok"]:
            record["counts"] = result["counts"]
            record["total"] = result["total"]
            record["fields"]["count"] = "accepted"
            if result["total"] is None:
                record["warnings"].append("total_not_published")
        else:
            record["fields"]["count"] = _field_state(result["reasons"], result["blocked"])

    if "sub" in gaps:
        result = _verify_sub(candidate.get("prizes") or [], candidate.get("total"), page_cache, render, ocr)
        record["found"]["sub"] = result["expected"]
        record["reasons"].extend(result["reasons"])
        record["warnings"].extend(result.get("warnings") or [])
        record["blocked"].extend({**entry, "field": "sub"} for entry in result["blocked"])
        record["dropped"].extend({**entry, "field": "sub"} for entry in result["dropped"])
        if not result["expected"]:
            record["reasons"].append("sub_not_published")
            record["dropped"].append({"field": "sub", "reason": "sub_not_published"})
        elif result["prizes"] and len(result["prizes"]) == result["expected"] and result["sum_ok"]:
            record["subs"] = result["prizes"]
            record["total"] = result["total"]
            record["fields"]["sub"] = "accepted"
            if result["countsMissing"]:
                record["warnings"].append("count_not_published")
            if result["total"] is None:
                record["warnings"].append("total_not_published")
        else:
            record["fields"]["sub"] = _field_state(result["reasons"], result["blocked"])

    states = set(record["fields"].values())
    if "rejected" in states or _hard(record["reasons"]):
        record["status"] = "rejected"
    elif "pending" in states:
        record["status"] = "pending_review"
    elif "accepted" in states:
        record["status"] = "accepted"
    else:
        record["status"] = "unavailable"
    record["ask"] = _ask_text(record, gaps)
    return record

def restatus(record: dict, gaps: list[str]) -> dict:
    """离线重判：口径变了以后，用 run.json 里已经存下的候选与 reason 重新归类，不联网。

    只处理还没人裁过的条目；已经 accepted / rejected 的保持原样。判定顺序和新口径一致：
    候选里没值 → 来源未公布；有值但本轮来源打不开 → 待确认；有值且逐条对过 → 采信。
    这个函数不验原文（没法离线验），所以它只「归类」，不会把没核过的东西变成已采信。
    """
    if record.get("decidedBy") == "human":
        return record
    if record.get("status") in ("accepted", "rejected"):
        return record

    candidate = record.get("candidate") or {}
    reasons = list(record.get("reasons") or [])
    fields: dict[str, str] = {}
    blocked: list[dict] = []
    found: dict = dict(record.get("found") or {})

    for gap in gaps:
        if gap == "price":
            price = candidate.get("price") or {}
            if _as_int(price.get("value")) is None:
                fields["price"] = "unavailable"
                if "price_not_published" not in reasons:
                    reasons.append("price_not_published")
            elif any(reason.startswith("source_unreachable") for reason in reasons):
                fields["price"] = "pending"
                blocked.append({"field": "price", "kind": "", "source": price.get("source") or "",
                                "error": "本轮没取到"})
            elif any(_key(reason) in HARD for reason in reasons):
                fields["price"] = "rejected"
            else:
                # 有值、本轮也没报错：按新口径本来就该采信（旧口径可能被 total_missing 之类拦住）
                fields["price"] = "accepted"
        elif gap == "count":
            counted = [
                prize for prize in candidate.get("prizes") or []
                if prize.get("kind") and _as_int(prize.get("count")) is not None
            ]
            found["count"] = len(counted)
            if not counted:
                fields["count"] = "unavailable"
                if "count_not_published" not in reasons:
                    reasons.append("count_not_published")
                continue
            unreachable = {reason.split(":", 1)[1] for reason in reasons if reason.startswith("source_unreachable:")}
            hard_kinds = {
                reason.split(":", 1)[1] for reason in reasons
                if _key(reason) in HARD and ":" in reason
            }
            blocked_kinds = [prize for prize in counted if str(prize.get("kind")) in unreachable]
            if blocked_kinds:
                fields["count"] = "pending"
                for prize in blocked_kinds:
                    blocked.append({"field": "count", "kind": prize.get("kind"),
                                    "source": prize.get("source") or "", "error": "本轮没取到"})
            elif hard_kinds & {str(prize.get("kind")) for prize in counted}:
                fields["count"] = "rejected"
            else:
                fields["count"] = "accepted"
                record["counts"] = [
                    {"kind": str(prize.get("kind")), "count": _as_int(prize.get("count")),
                     "source": prize.get("source") or "", "name": prize.get("name_cn") or ""}
                    for prize in counted
                ]
                record["total"] = _as_int(candidate.get("total"))
                if record["total"] is None and "total_not_published" not in (record.get("warnings") or []):
                    record.setdefault("warnings", []).append("total_not_published")
        elif gap == "sub":
            named = [
                prize for prize in candidate.get("prizes") or []
                if prize.get("kind") and str(prize.get("name_cn") or prize.get("name") or "").strip()
            ]
            found["sub"] = len(named)
            if not named:
                fields["sub"] = "unavailable"
                if "sub_not_published" not in reasons:
                    reasons.append("sub_not_published")
                continue
            unreachable = {reason.split(":", 1)[1] for reason in reasons if reason.startswith("source_unreachable:")}
            hard_kinds = {
                reason.split(":", 1)[1] for reason in reasons
                if _key(reason) in HARD and ":" in reason
            }
            blocked_kinds = [prize for prize in named if str(prize.get("kind")) in unreachable]
            if blocked_kinds:
                fields["sub"] = "pending"
                for prize in blocked_kinds:
                    blocked.append({"field": "sub", "kind": prize.get("kind"),
                                    "source": prize.get("source") or "", "error": "本轮没取到"})
            elif hard_kinds & {str(prize.get("kind")) for prize in named}:
                fields["sub"] = "rejected"
            else:
                fields["sub"] = "accepted"
                record["subs"] = [
                    {"kind": str(prize.get("kind")),
                     "name": str(prize.get("name_cn") or prize.get("name") or ""),
                     "alias": str(prize.get("alias") or ""),
                     "count": _as_int(prize.get("count")),
                     "source": prize.get("source") or ""}
                    for prize in named
                ]
                record["total"] = _as_int(candidate.get("total"))
                if record["total"] is None and "total_not_published" not in (record.get("warnings") or []):
                    record.setdefault("warnings", []).append("total_not_published")

    record["fields"] = fields
    record["blocked"] = blocked
    record["found"] = found
    record["reasons"] = list(dict.fromkeys(reasons))
    states = set(fields.values())
    if "rejected" in states or _hard(record["reasons"]):
        record["status"] = "rejected"
    elif "pending" in states:
        record["status"] = "pending_review"
    elif "accepted" in states:
        record["status"] = "accepted"
    else:
        record["status"] = "unavailable"
    gaps_with_fields = [gap for gap in gaps if gap in fields] or list(fields)
    record["ask"] = _ask_text(record, gaps_with_fields)
    return record

def plan_manual_write(item: dict, entry: dict | None, candidate: dict) -> dict:
    """人工采信只写这条的缺口字段，不做「顺手把别的列也写了」。

    - 缺数量的盘不要拿候选价格去覆盖单抽价：价格本来就有，写了是白写，
      还会把「数量其实没写进去」这件事盖住（2026-11-17 复盘：点了采信变「已采信」，数量仍是空）。
    - 一条都写不进去 → 返回空计划，调用方必须报错，不能标记成功。
    """
    gaps = list(item.get("gaps") or [])
    if not gaps and item.get("gap"):
        gaps = [part for part in str(item["gap"]).split("+") if part]
    plan: dict = {"price": None, "counts": [], "subs": [], "missing": []}

    if "price" in gaps:
        candidate_price = item.get("price") or (candidate or {}).get("price") or {}
        value = _as_int(candidate_price.get("value"))
        quote = str(candidate_price.get("quote") or "")
        currency = str(candidate_price.get("currency") or "").upper()
        if currency not in ("CNY", "JPY"):
            currency = "JPY" if "円" in quote else ("CNY" if "元" in quote else "")
        # 表格只有人民币 / 日元两种写法；台币等代理价不写，避免把 330 写成「330元/抽」
        if value is not None and currency in ("CNY", "JPY"):
            plan["price"] = {"record_id": item.get("panRecordId"), "value": value, "currency": currency}
        else:
            plan["missing"].append("price")

    if "count" in gaps:
        verified = [
            {"kind": str(p.get("kind")), "count": int(p["count"])}
            for p in (item.get("counts") or [])
            if p.get("kind") and _as_int(p.get("count")) is not None
        ]
        pool = verified or [
            {"kind": str(p.get("kind")), "count": _as_int(p.get("count"))}
            for p in ((candidate or {}).get("prizes") or [])
            if p.get("kind") and _as_int(p.get("count")) is not None
        ]
        mapping = {str(row.get("kind")): row.get("recordId") for row in ((entry or {}).get("rows") or [])}
        for prize in pool:
            record_id = mapping.get(prize["kind"])
            if record_id:
                plan["counts"].append({"record_id": record_id, "kind": prize["kind"], "count": prize["count"]})
        if not plan["counts"]:
            plan["missing"].append("count")

    if "sub" in gaps:
        pool = [
            prize for prize in (item.get("subs") or (candidate or {}).get("prizes") or [])
            if prize.get("kind") and str(prize.get("name_cn") or prize.get("name") or "").strip()
        ]
        for prize in pool:
            plan["subs"].append(
                {
                    "pan_record_id": item.get("panRecordId"),
                    "pan_name": item.get("pan") or "",
                    "kind": str(prize["kind"]),
                    "name": str(prize.get("name_cn") or prize.get("name") or ""),
                    "alias": str(prize.get("alias") or ""),
                    "count": _as_int(prize.get("count")),
                }
            )
        if not plan["subs"]:
            plan["missing"].append("sub")

    return plan



KANA_RE = re.compile(r"[\u3040-\u30ff]")
JP_HOSTS = (
    "1kuji.com",
    "hobby.watch.impress.co.jp",
    "dengekionline.com",
    "yasuee.com.hk",
    "prtimes.jp",
)


def _quote_specific(name: str, quote: str) -> bool:
    """quote 必须能对上这个盘，不能是页面上的通稿话术。

    2026-11-20 实测：磁力赏三条候选的 quote 都是「本信息为发售前的店铺汇总信息…」，
    逐字命中却和盘名无关，等于没证据。这里要求 quote 覆盖盘名主体（去掉品牌前缀）。
    """
    brand = derive_brand(name, "")
    core = norm(name)
    if brand:
        core = core.replace(norm(brand), "", 1)
    core = re.sub(r"[^0-9a-zA-Z\u4e00-\u9fff]", "", core)
    if len(core) < 4:
        return True  # 名字太短，判不了，交给后面的规则
    if core in (quote or ""):
        return True
    # 中英混排的盘名（HUNTER×HUNTER、GIRLS BAND CRY）整体覆盖率容易被英文拉低，
    # 改用「公共子串」判：只要有一段 ≥4 字的连续重合，就说明 quote 指的是这个盘。
    hay = norm(quote or "")
    needle = norm(core)
    need = 4 if len(needle) >= 6 else max(2, len(needle) // 2)
    best = 0
    for start in range(len(needle)):
        for end in range(len(needle), start + best, -1):
            if needle[start:end] in hay:
                best = max(best, end - start)
                break
    return best >= need


def _jp_scope(name: str, source: str) -> bool:
    """日版盘不属于「中国大陆新品」：名字全是假名 + 来源是日本站，交人确认。"""
    if not KANA_RE.search(name or ""):
        return False
    host = (urlsplit(source).hostname or "").lower()
    return any(host.endswith(item) or item in host for item in JP_HOSTS)


def _accept_with_scope(name: str, source: str, verdict: dict, quote: str) -> dict:
    """命中之后再过两道：quote 是否真对这个盘、是不是日版跑偏。"""
    if _jp_scope(name, source):
        return {"status": "pending_review", "reasons": ["scope_jp"], "evidence": verdict.get("evidence", "")}
    if not _quote_specific(name, quote):
        return {"status": "pending_review", "reasons": ["quote_not_specific"], "evidence": verdict.get("evidence", "")}
    return verdict


def verify_discover(candidate: dict, existing_keys: set[str], page_cache: dict,
                    snapshots: dict | None = None, render=None) -> dict:
    """验收一条新盘候选（discover 专用）。

    和 backfill 的差别：新盘只需要「名字 + 品牌 + 来源」，没有价格/配率要核对，
    所以四道门收敛成三道：
    1. source 必须是 http(s) 链接——账号名、uid、平台名一律判废（source_not_url）；
    2. 来源没被二手平台污染；
    3. quote 必须能在来源正文里命中：先查本轮抓下来的快照（微博/小红书），
       快照没有再走网络（公众号文章、新闻站）。
    证据不足（页面打不开、quote 太短）判「待确认」，不写、不猜。
    render 是可选的兜底：公众号文章现在是 JS 壳，urllib 只拿到空白外壳，
    这时用浏览器渲染一次再判（仍然只认原文命中，不放宽口径）。
    """
    from .feeds import url_key

    name = str(candidate.get("name") or candidate.get("pan") or "").strip()
    source = str(candidate.get("source") or "").strip()
    quote = str(candidate.get("quote") or "").strip()
    if not name:
        return {"status": "rejected", "reasons": ["name_missing"], "evidence": ""}
    if not source:
        return {"status": "rejected", "reasons": ["source_missing"], "evidence": ""}
    if not source.lower().startswith("http"):
        return {"status": "rejected", "reasons": ["source_not_url"], "evidence": ""}
    if is_secondhand(source):
        return {"status": "rejected", "reasons": ["secondhand_forbidden"], "evidence": ""}
    if pan_key(name, str(candidate.get("brand") or "")) in existing_keys:
        return {"status": "rejected", "reasons": ["duplicate"], "evidence": ""}
    if not quote:
        return {"status": "pending_review", "reasons": ["quote_missing"], "evidence": ""}
    if len(norm(quote)) < 10:
        return {"status": "pending_review", "reasons": ["quote_too_short"], "evidence": ""}

    page = ""
    evidence = ""
    key = url_key(source)
    if key and key in (snapshots or {}):
        page = snapshots[key]
        evidence = "snapshot"
    elif render and "mp.weixin.qq.com" in str(source).lower():
        # 公众号文章 urllib 只能拿到 JS 壳，直接走渲染；渲染不出来就交人看
        page = render(source) or ""
        evidence = "rendered"
        if not page:
            return {"status": "pending_review", "reasons": ["render_failed"], "evidence": ""}
    else:
        ok, body, error = _page(page_cache, source)
        if not ok:
            return {"status": "pending_review", "reasons": [f"source_unreachable:{error}"], "evidence": ""}
        page = body
        evidence = "fetched"
    if page_contains(page, quote):
        return _accept_with_scope(name, source, {"status": "accepted", "reasons": [], "evidence": evidence}, quote)
    if fuzzy_contains(page, quote):
        # 小红书/微博正文常带表情、换行、简称：措辞放宽，来源仍要能打开
        return _accept_with_scope(
            name, source, {"status": "accepted", "reasons": [], "evidence": f"{evidence}:fuzzy"}, quote
        )
    if not page_contains(page, quote):
        rendered = ""
        if render:
            try:
                rendered = render(source) or ""
            except Exception:  # noqa: BLE001 - 渲染失败按原判据处理
                rendered = ""
        if rendered and page_contains(rendered, quote):
            return {"status": "accepted", "reasons": [], "evidence": "rendered"}
        if render is not None and len(norm(rendered)) < 800:
            # 浏览器只渲染出一小段（公众号预览壳 / 渲染失败）：判不了，交人看，不硬判废
            return {"status": "pending_review", "reasons": ["render_incomplete"], "evidence": evidence}
        return {"status": "rejected", "reasons": ["quote_mismatch"], "evidence": evidence}
    return {"status": "accepted", "reasons": [], "evidence": evidence}
