"""游戏虚拟道具双源派发：workbuddy（翻官方页面）+ DeepSeek（搜索 + 结构化抽取）。

只负责把问题发出去、把原文拿回来；判断在 vg_accept.py。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

from .bag_dispatch import DS_CLI, DS_MODEL, DS_URL, _material, ds_fetch, ds_key, ds_search
from .common import extract_json

TYPE_WORDS = ("充值代币", "月卡", "通行证", "礼包", "其他")


def product_queries(game: dict, window_days: int = 7) -> list[str]:
    name = game.get("game") or ""
    currency = game.get("currency") or ""
    publisher = game.get("publisher") or ""
    hints = [str(x) for x in (game.get("skuHints") or []) if str(x).strip()]
    queries = [f"{name} {publisher} 充值 价格 官方 商城"]
    if currency:
        queries.append(f"{name} {currency} 价格 档位 充值 比例")
    if hints:
        queries.append(f"{name} {' '.join(hints[:2])} 价格 官方")
    queries.append(f"{name} 月卡 通行证 价格 有效期")
    return queries[:4]


def discovery_queries(thresholds: dict, discovery: dict) -> list[str]:
    month = ""
    queries = [
        "2026年 新游戏 公测 上线 充值 月卡 通行证",
        "国家新闻出版署 版号 公示 最新 国产网络游戏 审批",
        "TapTap 新品榜 手游 2026 内购",
    ]
    publishers = thresholds.get("publishers") or []
    if publishers:
        queries.append(f"{' '.join(publishers[:4])} 新游戏 上线 预约 2026")
    return queries


def product_instructions() -> str:
    return (
        "你是游戏内购商品信息核对员。只输出一个 JSON 数组，不要解释、不要 markdown 围栏。\n"
        "每个元素字段：game, type, name, denom, price, duration, limit, quote, source, lane。\n"
        "- type 只能是：充值代币/月卡/通行证/礼包/其他。\n"
        "- name 是商品名（如「创世结晶」「空月祝福」「无名勋礼」）；denom 是面额或权益档（如「60」「980」「30天」）。\n"
        "- price 是人民币标价（数字，元）；拿不到写 null，禁止写 0、禁止折算外币。\n"
        "- duration 是时效，limit 是限购说明；没有写空串。\n"
        "- **只要材料里出现「商品名 + 价格」就报**，source 用材料里的 URL，quote 从材料原文复制；"
        "官方性、双源一致性由后面的验收环节判断，你不要因为「不确定是否官方」而返回 []。\n"
        "- 材料里完全没有商品名或价格时才返回 []；禁止编造材料里不存在的 URL 与价格。"
    )


def discovery_instructions() -> str:
    return (
        "你是游戏行业新品观察员。只输出一个 JSON 数组，不要解释、不要 markdown 围栏。\n"
        "每个元素字段：game, publisher, status, platform, monetization, license, source, quote, "
        "reservation, currency, appStore, chart。\n"
        "- status 只能是：已上线/预约/测试；platform 如「iOS/Android/PC」。\n"
        "- monetization 说明它卖什么：代币/月卡/通行证 的组合；license 是版号信息（没有写「无版号」）。\n"
        "- currency 是内购代币名（如 创世结晶 / 古老梦华 / 回声 / 月相），不确定写「未知」。\n"
        "- appStore 是中国区 App Store 游戏页完整 URL（apps.apple.com/cn/app/…）；没有就写空串。\n"
        "- chart 是它在 App Store 或第三方畅销榜的名次（如「畅销榜第 12 名」），没上榜单写空串。\n"
        "- source 优先给可打开的官方页面（发行商官网/官方公告）或权威公示页（版号公示）；"
        "quote 从该页原文复制，能证明「这是新游戏」或「它有内购」；拿不到就写空串。\n"
        "- 只要中国大陆可玩或已获版号的游戏；已停运、纯海外服、买断制无内购的不要报。\n"
        "- 材料里出现的新游戏都要报（预约/测试/刚上线都算），缺少的字段写空串或 0，"
        "不要因为字段不全就返回 []；只有在材料里完全没有游戏信息时才返回 []，禁止编造。"
    )


def _ds_extract(prompt: str, instructions: str, timeout: int = 120) -> dict:
    key = ds_key()
    if not key:
        return {"ok": False, "error": "missing_api_key", "items": [], "text": ""}
    payload = {"model": DS_MODEL, "input": prompt, "instructions": instructions}
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
    except Exception as error:  # noqa: BLE001
        return {"ok": False, "error": error.__class__.__name__, "items": [], "text": ""}
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
    return {"ok": True, "error": "", "items": items, "text": text[:8000]}


def ds_products(game: dict, window_days: int = 7) -> dict:
    """一个游戏：先搜索取材料，再抽取结构化候选。"""
    results: list[dict] = []
    seen: set[str] = set()
    errors: list[str] = []
    for query in product_queries(game):
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
        return {"ok": False, "error": errors[0] if errors else "no_results", "items": [], "text": ""}
    prompt = (
        f"游戏：{game.get('game')}；发行商：{game.get('publisher')}；"
        f"代币名：{game.get('currency') or '未知'}；已知商品名：{'、'.join(game.get('skuHints') or []) or '无'}。\n"
        f"要查的三类：充值代币（含各面额档位与折算比例）、月卡（价格与有效期）、通行证（价格与档位）。\n\n"
        f"搜索结果材料：\n{_material(results)}\n\n"
        "请尽量抽取：材料里出现的商品名与价格都报，缺失字段写空；官方性由验收判断。"
    )
    return _ds_extract(prompt, product_instructions())


def ds_discover(
    thresholds: dict, discovery: dict, known: list[str], since: str = "", until: str = ""
) -> dict:
    results: list[dict] = []
    seen: set[str] = set()
    errors: list[str] = []
    for query in discovery_queries(thresholds, discovery):
        found = ds_search(query, count=6)
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
        return {"ok": False, "error": errors[0] if errors else "no_results", "items": [], "text": ""}
    prompt = (
        "当前中国大陆有热度、且有内购（代币/月卡/通行证）的游戏，不限新老、不限上线时间。\n"
        "表里已经有的游戏也要报：我们会按「游戏 + 商品名」去重，只补缺的商品。\n"
        "请尽量补齐 App Store 链接（appStore）与榜单名次（chart），这是热度门槛的依据；"
        "字段不全也要报，缺的写空串；只有在材料里完全没有游戏信息时才返回 []。\n\n"
        f"搜索结果材料：\n{_material(results)}\n\n"
        "请根据材料抽取游戏事实。"
    )
    return _ds_extract(prompt, discovery_instructions())


def workbuddy_products_prompt(games: list[dict], channels: list[dict], since: str, until: str) -> str:
    game_lines = []
    for game in games:
        game_lines.append(
            f"- {game['game']}（发行商 {game.get('publisher') or '未知'}）：代币 {game.get('currency') or '未知'}；"
            f"已知商品名 {'、'.join(game.get('skuHints') or []) or '无'}"
        )
    channel_lines = []
    for channel in channels:
        channel_lines.append(
            f"- {channel.get('publisher')} · {channel.get('channel')}（{channel.get('tier')} 级，{channel.get('status')}）"
            f"{channel.get('url') or ''} 能回答：{'、'.join(channel.get('canAnswer') or [])}"
        )
    return f"""范围：本轮全部游戏（可能跨多个发行商，共 {len(games)} 个）
核对窗口：{since} ~ {until}（价格可以更早，但要标出页面日期/版本）
要查的游戏：
{chr(10).join(game_lines)}

官方渠道（只认这些来源；没列到的发行商，用它的官网/官方商城/官方社媒）：
{chr(10).join(channel_lines)}

任务：查这些游戏当前在卖的虚拟道具：充值代币（各面额档位与折算比例）、月卡（价格/有效期）、通行证（价格/档位）。
每个游戏都要覆盖，每个游戏最多 10 条；不要只报前几个游戏。
只输出 JSON 数组，每个元素：
{{"game":"","type":"充值代币|月卡|通行证|礼包|其他","name":"","denom":"","price":0,
 "duration":"","limit":"","quote":"","source":"","lane":"workbuddy","confidence":0}}

硬要求：
1. source 优先给可打开的官方页面（发行商官网/官方商城/官方社媒/应用商店内购页）；quote 尽量从该页原文复制，
   且同时含商品名、面额/权益与价格；拿不到官方页时也报，官方性由验收层判断，字段不全写空。
2. 价格只认人民币标价；首充双倍、赠送、限购写进 limit，不改进 price。拿不到就写 null，禁止推测。
3. 代充、折扣店、二手、账号交易、聚合站只能当线索，不要当官方来源。
4. 材料里完全没有商品名与价格时才返回 []，禁止编造。"""


def workbuddy_discover_prompt(discovery: dict, thresholds: dict, since: str, until: str, known: list[str]) -> str:
    license_row = discovery.get("license") or {}
    rankings = discovery.get("rankings") or []
    rank_lines = "\n".join(f"- {row.get('name')}：{row.get('url')}" for row in rankings)
    return f"""范围：当前中国大陆有热度、且有内购（代币、月卡、通行证）的游戏，不限新老、不限上线时间。
表里已有的游戏也要报：我们会按「游戏 + 商品名」去重，只补缺的商品。

任务：找出这些有热度的游戏（畅销榜 / 预约榜 / 大厂在营都算）。
只输出 JSON 数组，每个元素：
{{"game":"","publisher":"","status":"已上线|预约|测试","platform":"","monetization":"",
 "currency":"","appStore":"","chart":"","license":"","source":"","quote":"","reservation":0}}

字段说明：
- currency：内购代币名（创世结晶 / 古老梦华 / 回声 / 月相），不确定写「未知」。
- appStore：中国区 App Store 游戏页完整 URL；没有写空串。
- chart：榜单名次，如「畅销榜第 12 名」；没上榜单写空串。
- reservation：预约人数，没有写 0。

可以看的地方：
- 版号公示：{license_row.get('name') or '国家新闻出版署'} {license_row.get('url') or ''}
{rank_lines}

硬要求：
1. 最多报 10 个，按热度排序（大厂/高预约/榜单靠前优先）；不要逐个打开游戏官网深挖，拿到名字、发行商、
   预约量、榜单名次、App Store 链接即可。
2. 至少给出一个可打开的官方页面或权威公示页作为 source，quote 从原文复制；拿不到写空串也要报。
3. 停运、纯海外服、买断制无内购的游戏不要报。
4. 没有就返回 []，禁止编造。"""


def submit(prompt: str, title: str, workdir: Path) -> dict:
    from . import dispatch

    return dispatch.submit_workbuddy(prompt, title, workdir)


def fetch_page(url: str) -> dict:
    return ds_fetch(url)
