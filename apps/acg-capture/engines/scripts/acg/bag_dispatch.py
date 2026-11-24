"""官方福袋双源派发：workbuddy（翻官方页面） + DeepSeek（全网搜索 + 结构化抽取）。

workbuddy 有两种任务，区别只在「从哪找」：
  - sweep（全量扫街）：每条线索都派，先全网找官方页，已知渠道只当优先入口；
  - channel（定向渠道）：只挑绑了 confirmed 渠道的线索，只认这些渠道的页面。
两者候选在 bag_discover 里合并成一份再验收，判断在 bag_accept.py。
"""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from .common import extract_json

DS_URL = "https://api.deepseek.com/responses"
DS_MODEL = os.environ.get("BAG_DS_MODEL", "deepseek-v4-flash")
DS_CONFIG = Path.home() / ".config" / "qiaomu-ds-search" / "credentials.json"
DS_CLI = Path.home() / ".dsh" / "skills" / "qiaomu-ds-search" / "scripts" / "ds_search.py"


def ds_key() -> str:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key
    try:
        payload = json.loads(DS_CONFIG.read_text(encoding="utf-8"))
        return str(payload.get("api_key") or "").strip()
    except (OSError, json.JSONDecodeError):
        return ""


def lead_queries(lead: dict, since: str, until: str) -> list[str]:
    ip = lead.get("ip") or ""
    publisher = lead.get("publisher") or ""
    carriers = " ".join((lead.get("carriers") or [])[:3]) or "福袋"
    year = (until or "")[:4] or "2026"
    queries = [f"{ip} {publisher} 官方 {carriers} {year} 发售"]
    for keyword in (lead.get("keywords") or [])[:2]:
        queries.append(f"{ip} {keyword} 福袋 官方")
    queries.append(f"{ip} 福袋 价格 元 官方旗舰店")
    return queries


def instructions() -> str:
    return (
        "你是官方商品信息核对员。只输出一个 JSON 数组，不要解释、不要 markdown 围栏。\n"
        "每个元素字段：ip, officialName, carrier, role, tiers[], window{}, channels[], limit, aliases[], source, quote, lane, confidence。\n"
        "- carrier 只能是：福袋/神秘盒子/礼盒/惊喜袋/盲袋/其他；role 是 official_release 或 equivalent_carrier。\n"
        "- source 必须是材料里的「品牌官方页面」URL（自营商城/官网/小程序/官方社媒/平台品牌官旗店）；quote 从该页正文原样复制，含官方商品名与载体词。\n"
        "- tiers 每项：{price(数字,元), items(如「随机2或8件」), quote, source}。price 缺失就不要这一档；"
        "tiers[].source 允许引用材料里的其它页面（例如媒体报道转述官方旗舰店价格），quote 同样从那一页原样复制，且必须含价格。\n"
        "- 经销商、二手、聚合站不作为任何 source。\n"
        "- 材料里没有官方页面就返回 []，禁止编造 URL、价格与档位。"
    )


def ds_search(query: str, count: int = 5, timeout: int = 90) -> dict:
    """DeepSeek 官方 Search（qiaomu CLI）：返回带 content 的结果列表。"""
    if not DS_CLI.exists():
        return {"ok": False, "error": "ds_cli_missing", "results": []}
    try:
        result = subprocess.run(
            ["python3", str(DS_CLI), "search", query, "--count", str(count), "--need-content"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        return {"ok": False, "error": error.__class__.__name__, "results": []}
    if result.returncode != 0:
        return {"ok": False, "error": (result.stderr or result.stdout)[:200], "results": []}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "bad_json", "results": []}
    if not payload.get("ok"):
        return {"ok": False, "error": str((payload.get("error") or {}).get("code") or "search_error"), "results": []}
    return {"ok": True, "error": "", "results": payload.get("results") or []}


def _material(results: list[dict], limit: int = 8) -> str:
    blocks = []
    for index, row in enumerate(results[:limit], 1):
        content = (row.get("content") or row.get("summary") or row.get("snippet") or "").strip()
        blocks.append(
            f"[{index}] {row.get('title') or ''}\nURL: {row.get('url') or ''}\n"
            f"站点：{row.get('site_name') or row.get('source_family') or ''}\n正文：{content[:2600]}"
        )
    return "\n\n".join(blocks)


def ds_extract(lead: dict, since: str, until: str, timeout: int = 120) -> dict:
    """一个线索：先 DeepSeek Search 取材料，再用 DeepSeek 抽取结构化候选。"""
    key = ds_key()
    if not key:
        return {"ok": False, "error": "missing_api_key", "items": [], "text": "", "citations": []}

    results: list[dict] = []
    seen: set[str] = set()
    errors: list[str] = []
    for query in lead_queries(lead, since, until)[:3]:
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
        return {"ok": False, "error": errors[0] if errors else "no_results", "items": [], "text": "", "citations": []}

    payload = {
        "model": DS_MODEL,
        "input": (
            f"目标 IP：{lead.get('ip')}；发行方：{lead.get('publisher')}；"
            f"载体词：{'、'.join(lead.get('carriers') or ['福袋'])}；"
            f"关注关键词：{'、'.join(lead.get('keywords') or []) or '无'}；窗口：{since} ~ {until}。\n\n"
            f"搜索结果材料：\n{_material(results)}\n\n"
            "请只根据上面的材料抽取「官方发售」事实。"
        ),
        "instructions": instructions(),
    }
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
        return {"ok": False, "error": f"http_{error.code}", "items": [], "text": "", "citations": []}
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "error": error.__class__.__name__, "items": [], "text": "", "citations": []}

    text = ""
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") in ("output_text", "text"):
                text += content.get("text") or ""
    value = extract_json(text)
    items = [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    for row in items:
        row["lane"] = "deepseek"
        # DeepSeek 一路本来就是全网搜索，归到 sweep；渠道定向只由 workbuddy 承担。
        row["mode"] = "sweep"
    citations = [str(row.get("url")) for row in results if row.get("url")]
    return {"ok": True, "error": "", "items": items, "text": text[:8000], "citations": citations[:20]}


def ds_fetch(url: str, timeout: int = 60) -> dict:
    """HTML 抓不到时用 DeepSeek fetch 取 Markdown 正文。"""
    if not DS_CLI.exists():
        return {"ok": False, "error": "ds_cli_missing", "content": ""}
    try:
        result = subprocess.run(
            ["python3", str(DS_CLI), "fetch", url],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (subprocess.TimeoutExpired, OSError) as error:
        return {"ok": False, "error": error.__class__.__name__, "content": ""}
    if result.returncode != 0:
        return {"ok": False, "error": (result.stderr or result.stdout)[:200], "content": ""}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": "bad_json", "content": ""}
    return {"ok": bool(payload.get("ok")), "error": str(payload.get("error") or ""), "content": payload.get("content") or ""}


def _lead_lines(leads: list[dict]) -> str:
    lines = []
    for lead in leads:
        lines.append(
            f"- {lead['ip']}（{lead.get('ipType')}）：载体词 {'、'.join(lead.get('carriers') or ['福袋'])}；"
            f"关键词 {'、'.join(lead.get('keywords') or []) or '无'}"
        )
    return chr(10).join(lines)


def _channel_lines(channels: list[dict]) -> str:
    lines = []
    for channel in channels:
        lines.append(
            f"- {channel.get('channel')}"
            f"（{channel.get('tier')} 级，{channel.get('status')}）{channel.get('url') or ''}"
            f" 能回答：{'、'.join(channel.get('canAnswer') or [])}"
        )
    return chr(10).join(lines) or "（这批 IP 还没配 confirmed 渠道，直接全网找官方页）"


def _output_rules(mode: str) -> str:
    return f"""只输出 JSON 数组，每个元素：
{{"ip":"","officialName":"","carrier":"","role":"official_release|equivalent_carrier",
 "tiers":[{{"price":0,"items":"","quote":"","source":""}}],
 "window":{{"start":"","end":""}},"channels":[""],"limit":"","aliases":[],
 "source":"","quote":"","lane":"workbuddy","mode":"{mode}","confidence":0}}

硬要求：
1. source 必须是可打开的官方页面 URL；quote 必须在该页原文里连续出现，且同时含载体词与价格。
2. 价格/档位/件数只能来自原文，拿不到写空，禁止推测；同一 SKU 多档放进 tiers。
3. 经销商、二手平台（千岛/闲鱼/抖音/聚合站）、B 站会员购都不算官方来源。
4. 没有就返回 []，禁止编造。"""


def workbuddy_prompt(publisher: str, leads: list[dict], channels: list[dict], since: str, until: str) -> str:
    """定向任务：只认线索绑定的 confirmed 渠道，用来把「已经知道官方口子」的 IP 抓准。"""
    return f"""发行方：{publisher}
窗口：{since} ~ {until}
要查的 IP：
{_lead_lines(leads)}

官方渠道（只认这些来源）：
{_channel_lines(channels)}

任务：查这些 IP 在窗口内有没有「官方发售」的福袋或等价载体（神秘盒子/礼盒/惊喜袋/盲袋）。
这些渠道已经确认过是官方口子，直接翻它们的商城/官旗店/官微/小程序页面找在售商品。

{_output_rules("channel")}"""


def sweep_prompt(leads: list[dict], since: str, until: str) -> str:
    """全量扫街：一张 IP 清单全网搜，不按发行方切、不限定渠道、不要求逐页核对。

    刻意写得轻：只给窗口、关键词和「尽量以公开的官方信息和电商平台信息为准」；
    输出只要三样（商品名称 / 内容 / IP），按一行一条给，下游用 parse_text_candidates 兜底解析。
    """
    lines = []
    for lead in leads:
        publisher = str(lead.get("publisher") or "").strip()
        lines.append(f"- {lead.get('ip')}、{publisher}" if publisher else f"- {lead.get('ip')}")
    keys = "、".join((leads[0].get("carriers") or ["福袋"])[:4]) if leads else "福袋、惊喜福袋、礼盒、神秘盒子"
    return f"""窗口：{since} ~ {until}
查询以下IP在时间窗口内发布的福袋商品，关键词：{keys}，尽量以公开的官方信息和电商平台信息为准
{chr(10).join(lines)}
输出商品名称、内容、IP

格式：一行一个商品，三列用 | 隔开，例如
商品名称 | 内容（价格、件数、开售时间、来源链接都写在这里） | IP
没查到就写「无」，不要编造。"""


def submit(prompt: str, title: str, workdir: Path) -> dict:
    from . import dispatch

    return dispatch.submit_workbuddy(prompt, title, workdir)
