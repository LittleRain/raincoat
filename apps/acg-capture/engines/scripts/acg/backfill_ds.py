"""官方赏补齐的 DeepSeek 通道：搜索取材料 → 结构化抽取（与 workbuddy 同 schema）。

只负责把问题发出去、把原文拿回来；判断在 accept.py（同一个验收层，口径不变）。
workbuddy 擅长翻官方页面的赏别表；DeepSeek 通道补它翻不到的长尾——
台湾代理整箱页、日台新闻、公众号正文里写明的抽数与单抽价。

用法：acg_run.py --kind backfill --lanes workbuddy,deepseek
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .bag_dispatch import DS_MODEL, DS_URL, _material, ds_key, ds_search
from .common import extract_json

# 补齐只认这几类页面；二手/聚合站只当线索，不当来源（验收层还会再拦一次）
OFFICIAL_HINTS = ("1kuji.com", "oneone.com.tw", "cc1kuji.com", "bandai", "官方", "代理")

_SUFFIX = re.compile(r"[（(](?:日版|中国版|国行|代理版)[^）)]*[）)]\s*$")


def clean_name(name: str) -> str:
    """去掉「（日版·一番赏ONLINE）」这类渠道后缀，检索时只留盘名本体。"""
    return _SUFFIX.sub("", str(name or "")).strip()


def pan_queries(pan: dict) -> list[str]:
    """一个盘要搜什么：日版优先日文原名，国产用中文名 + 抽数口径。"""
    name = clean_name(pan.get("pan") or "")
    alias = clean_name(pan.get("alias") or "")
    is_jp = "日版" in str(pan.get("pan") or "") or bool(alias)
    queries: list[str] = []
    if alias:
        queries.append(f"{alias} 一番くじ 各賞 数量 抽数")
        queries.append(f"{alias} 1kuji 全種 価格")
        queries.append(f"{alias} oneone 整箱 剩餘")
    if name:
        queries.append(f"{name} 一番赏 单抽价 各赏 数量")
        queries.append(f"{name} 抽赏 一箱 多少抽 价格")
    if is_jp and name and name != alias:
        queries.append(f"{name} 日版 一番赏 抽数 价格")
    return queries[:5]


def instructions() -> str:
    return (
        "你是官方抽赏（一番赏）配置核对员。只输出一个 JSON 数组，不要解释、不要 markdown 围栏。\n"
        "每个盘一个对象：{pan, price:{value,currency,quote,source}, total, prizes:[{kind,name_cn,alias,count,quote,source}], missing:[]}\n"
        "- pan 原样抄目标盘名；currency 写 JPY 或 CNY。\n"
        "- prizes 按赏别 A、B、C … LAST 逐条列出；kind 只写字母或 LAST；count 是**这一赏在一整套里的个数**，"
        "不是剩余数、不是中奖概率；alias 是日文原名，没有就空串。\n"
        "- **count 的硬约束**：Σ(除 LAST 外各赏 count) 必须等于整套抽数 total；算不平就说明你抄错了，"
        "该赏 count 写 null，不要为了凑数编。total 拿不到写 null。\n"
        "- price.value 只认页面明写的单抽价数字（含税）；币种按页面；拿不到写 null，禁止按同 IP 推测、禁止写区间。\n"
        "- quote 必须是来源页面正文里连续的一段原文（≥10 字），能同时看到赏别/数量和价格；source 必须是 http(s) 链接。\n"
        "- **只要材料里出现这个盘就报一条**（赏名、单抽价、数量任一有就报，缺的写 null）；source 用材料里的 URL 原样复制，"
        "quote 从该页正文抄。官方性、二手与否由后面的验收层判断，你不要因为「拿不准是不是官方」就不报。\n"
        "- 二手/聚合站（千岛、闲鱼、抖音、拆卡店）只能当线索：照实报，但 quote 必须真在那一页；验收层会拦。\n"
        "- 材料里完全没有这个盘的信息才返回 []；只有赏名没有数字也报，数字写 null。禁止编造 URL、价格与数量。"
    )


def parse_items(text: str) -> list[dict]:
    """把模型输出解析成候选；解析不了返回空列表（不抛）。"""
    value = extract_json(text or "")
    if not isinstance(value, list):
        return []
    items = [row for row in value if isinstance(row, dict)]
    for row in items:
        row["lane"] = "deepseek"
    return items


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
    except Exception as error:  # noqa: BLE001 - 通道失败不能让整轮补齐挂掉
        return {"ok": False, "error": error.__class__.__name__, "items": [], "text": ""}
    text = ""
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") in ("output_text", "text"):
                text += content.get("text") or ""
    return {"ok": True, "error": "", "items": parse_items(text), "text": text[:8000]}


def ds_pan(pan: dict, timeout: int = 150) -> dict:
    """一个盘：多路搜索取材料，再抽取结构化候选。"""
    started = time.time()
    results: list[dict] = []
    seen: set[str] = set()
    errors: list[str] = []
    for query in pan_queries(pan):
        found = ds_search(query, count=5)
        if not found.get("ok"):
            errors.append(str(found.get("error")))
            continue
        for row in found.get("results") or []:
            url = str(row.get("url") or "")
            if not url or url in seen:
                continue
            seen.add(url)
            results.append(row)
    if not results:
        return {
            "ok": False,
            "error": errors[0] if errors else "no_results",
            "items": [],
            "elapsed": round(time.time() - started, 1),
            "sources": 0,
        }

    prompt = (
        f"目标盘：{pan.get('pan')}\n别名：{pan.get('alias') or '无'}\n"
        f"表里缺：{', '.join(pan.get('gaps') or [])}\n\n"
        f"搜索结果材料：\n{_material(results)}\n\n"
        "请只根据上面的材料抽取这一个盘的配置；材料里没有它就把这一条排除。"
    )
    extracted = _extract(prompt, timeout=timeout)
    items = [row for row in extracted.get("items") or [] if isinstance(row, dict)]
    return {
        "ok": bool(extracted.get("ok")),
        "error": extracted.get("error") or "",
        "items": items,
        "elapsed": round(time.time() - started, 1),
        "sources": len(results),
    }


def run_pans(batch: list[dict], workers: int = 4) -> dict:
    """整批盘并发跑 DeepSeek 通道；单盘失败只记错误，不影响其它盘。"""
    started = time.time()
    items: list[dict] = []
    per_pan: dict[str, dict] = {}
    errors: list[str] = []
    if not batch:
        return {"items": [], "perPan": {}, "errors": [], "elapsed": 0.0, "sources": 0}

    def job(pan: dict) -> tuple[str, dict]:
        return str(pan.get("panRecordId") or pan.get("pan")), ds_pan(pan)

    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(batch)))) as pool:
        for key, result in pool.map(job, batch):
            per_pan[key] = {
                "ok": result["ok"],
                "error": result["error"],
                "items": len(result["items"]),
                "sources": result["sources"],
                "elapsed": result["elapsed"],
            }
            items.extend(result["items"])
            if not result["ok"]:
                errors.append(f"{key}:{result['error']}")
    return {
        "items": items,
        "perPan": per_pan,
        "errors": errors,
        "elapsed": round(time.time() - started, 1),
        "sources": sum(v.get("sources") or 0 for v in per_pan.values()),
    }
