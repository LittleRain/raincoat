"""抓新品的 DeepSeek 通道：按品牌搜索 → 取材料 → 抽取新盘候选。

与 workbuddy 通道的关系：
- 两条通道覆盖同一批品牌、都不指定渠道，各自独立取证；
- 都用 accept.verify_discover 这一个验收层（来源可打开 + quote 命中），
  所以「两个模型都这么说」不算证据，只有原文命中才算。

为什么按品牌而不是按公众号：公众号只是渠道之一，官方也可能先发微博/小红书/新闻稿。
按品牌搜能把「品牌上新」这件事搜全，渠道自然落在 source 上。
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .backfill_ds import _extract as _backfill_extract  # noqa: F401 - 保留同类实现的可发现性
from .bag_dispatch import DS_MODEL, DS_URL, _material, ds_key, ds_search
from .common import extract_json

SECONDHAND = ("goofish", "xianyu", "qiandao", "2.taobao", "douyin", "kujihunter", "kujimap")


def queries(brand: str, since: str) -> list[str]:
    """一个品牌两条查询：泛搜「上新」+ 搜「赏盘/开售」。不做渠道限定。"""
    month = f"{since[:4]}年{int(since[5:7])}月" if len(since) >= 7 else ""
    return [
        f"{brand} 新赏 上新 {month}".strip(),
        f"{brand} 抽赏 开售 新品 {month}".strip(),
    ]


def instructions() -> str:
    return (
        "你在做抽赏（一番赏/万画赏/卡游赏等）新盘发现。只输出 JSON 数组，不要解释、不要 markdown 围栏。\n"
        "每个新盘一个对象：{brand,name,alias,release,stage,price,source,quote}\n"
        "- 只要材料里能确认「这个品牌新上了一个赏盘」就报；已发售和预告都报，stage 写「已发售」或「预告」。\n"
        "- name 用官方叫法写全（含第几弹/系列名）；brand 写盘名前的品牌前缀，不要用发稿账号名。\n"
        "- source 必须是材料里真实出现过的 http(s) URL，原样复制；不要用闲鱼/千岛/抖音拆卡这类二手页。\n"
        "- quote 从该 URL 的正文里原样抄一段（≥8 字），要能说明这盘存在；不要改写、不要拼接、不要编。\n"
        "- release 拿不到就写空串；price 只写页面明写的数字，没有就空。\n"
        "- 只看中国大陆版：日本本土发售（一番くじ 日版、1kuji.com、日本新闻稿）不要报。\n"
        "- 不是赏盘的（纯周边/通贩/快闪/门店活动）不要报；材料里没有新盘就返回 []。"
    )


def _extract(prompt: str, timeout: int = 150) -> dict:
    key = ds_key()
    if not key:
        return {"ok": False, "error": "missing_api_key", "items": [], "text": ""}
    payload = {"model": DS_MODEL, "input": prompt, "instructions": instructions()}
    request = urllib.request.Request(
        DS_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return {"ok": False, "error": f"http_{error.code}", "items": [], "text": ""}
    except Exception as error:  # noqa: BLE001 - 单品牌失败不拖垮整轮
        return {"ok": False, "error": error.__class__.__name__, "items": [], "text": ""}
    text = ""
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") in ("output_text", "text"):
                text += content.get("text") or ""
    return {"ok": True, "error": "", "items": parse_items(text), "text": text[:4000]}


def _bad_source(url: str) -> bool:
    host = re.sub(r"^https?://", "", str(url or "")).split("/")[0].lower()
    return any(bad in host for bad in SECONDHAND)


def parse_items(text: str) -> list[dict]:
    value = extract_json(text or "")
    if not isinstance(value, list):
        return []
    items = []
    for row in value:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or row.get("pan") or "").strip()
        source = str(row.get("source") or "").strip()
        quote = str(row.get("quote") or "").strip()
        if not name or not source.startswith("http") or len(quote) < 8:
            continue
        if _bad_source(source):
            continue
        row["name"] = name
        row["source"] = source
        row["quote"] = quote
        row["lane"] = "deepseek"
        items.append(row)
    return items


def brand_pans(brand: str, since: str, until: str, timeout: int = 150) -> dict:
    """一个品牌：两条查询取材料 → 抽取新盘。"""
    started = time.time()
    results: list[dict] = []
    seen: set[str] = set()
    errors: list[str] = []
    for query in queries(brand, since):
        found = ds_search(query, count=6)
        if not found.get("ok"):
            errors.append(str(found.get("error")))
            continue
        for row in found.get("results") or []:
            url = str(row.get("url") or "")
            if not url.startswith("http") or url in seen:
                continue
            seen.add(url)
            results.append(row)
    if not results:
        return {"ok": False, "error": errors[0] if errors else "no_results", "items": [], "sources": 0, "elapsed": round(time.time() - started, 1)}

    prompt = (
        f"品牌：{brand}\n窗口：{since} ~ {until}（北京时间）\n\n"
        f"搜索结果材料：\n{_material(results, limit=10)}\n\n"
        f"请只根据上面的材料，找出「{brand}」在窗口内新上线的赏盘；材料里没有就返回 []。"
    )
    extracted = _extract(prompt, timeout=timeout)
    items = [row for row in extracted.get("items") or [] if isinstance(row, dict)]
    for row in items:
        row.setdefault("brand", brand)
    return {
        "ok": bool(extracted.get("ok")),
        "error": extracted.get("error") or "",
        "items": items,
        "sources": len(results),
        "elapsed": round(time.time() - started, 1),
    }


def run(brands: list[str], since: str, until: str, workers: int = 3, timeout: int = 150) -> dict:
    """整批品牌并发跑；单品牌失败只记错误。"""
    started = time.time()
    items: list[dict] = []
    per_brand: dict[str, dict] = {}
    errors: list[str] = []
    if not brands:
        return {"items": [], "perBrand": {}, "errors": [], "elapsed": 0.0, "sources": 0}

    def job(brand: str) -> tuple[str, dict]:
        return brand, brand_pans(brand, since, until, timeout=timeout)

    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(brands)))) as pool:
        for brand, result in pool.map(job, brands):
            per_brand[brand] = {
                "ok": result["ok"],
                "error": result["error"],
                "items": len(result["items"]),
                "sources": result["sources"],
                "elapsed": result["elapsed"],
            }
            items.extend(result["items"])
            if not result["ok"] and result["error"] not in ("no_results", ""):
                errors.append(f"{brand}:{result['error']}")
    return {
        "items": items,
        "perBrand": per_brand,
        "errors": errors,
        "elapsed": round(time.time() - started, 1),
        "sources": sum(v.get("sources") or 0 for v in per_brand.values()),
    }
