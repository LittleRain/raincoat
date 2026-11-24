"""产品类型口径：哪些算赏盘、哪些要先问用户。

背景（2026-11-17）：卡游抽卡机渠道发的是收藏卡 / 典藏包，没有赏品和抽数，
形状不像传统赏盘；用户确认这类「算」，但同类边界品不要再自作主张入库——
`confirm` 里的类型一律停在待确认，由人点头。
"""

from __future__ import annotations

import json

from .common import WORKFLOW, norm

TYPES_FILE = WORKFLOW / "references" / "product-types.json"

FALLBACK = {
    "inScope": ["收藏卡", "典藏包", "卡包", "TD收藏卡", "抽卡机", "卡牌"],
    "confirm": ["盲盒", "盲袋", "手办", "毛绒", "徽章", "立牌", "流麻", "BJD", "挂件", "抱枕"],
}


def load() -> dict:
    data = dict(FALLBACK)
    if TYPES_FILE.exists():
        try:
            payload = json.loads(TYPES_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return data
        for key in ("inScope", "confirm"):
            if isinstance(payload.get(key), list):
                data[key] = [str(x) for x in payload[key] if str(x).strip()]
    return data


def classify(name: str, text: str = "") -> str:
    """返回 ok / confirm。只看盘名，不扫正文。

    2026-11-20 修正：以前正文里出现「手办 / 毛绒」也算 confirm，结果几乎所有一番赏
    正文都写「角色手办化」，正常盘全被拦在待确认。赏型应该由盘名决定，
    正文只用来佐证这个盘存在，不用来改类型。text 参数保留兼容。
    """
    rules = load()
    title = norm(name)
    for token in rules["inScope"]:
        if norm(token) in title:
            return "ok"
    for token in rules["confirm"]:
        if norm(token) in title:
            return "confirm"
    return "ok"
