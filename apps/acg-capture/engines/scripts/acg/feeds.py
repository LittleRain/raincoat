"""渠道原文 → 候选线索：归一化、按窗口过滤、给验收层留快照、给提示词拼 digest。

口径：
- 微博：时间线正文即证据，source 用 https://m.weibo.cn/detail/<mid>（抓取时就带在帖子里）。
- 小红书：详情页要 xsec_token，只能拿到主页卡片文案，item 标 evidence=xhs_card；
  卡片没有发布日期，date 留空、undated=True，提示词里注明「判不了就跳过」。
- 快照索引是验收层的第一证据源：source 命中了快照就不再走网络，避免「抓得到却验不了」。
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit, urlunsplit

WEIBO_ID_RE = re.compile(r"(?:detail|status|comments)/([0-9]{6,})")
XHS_ID_RE = re.compile(r"/explore/([0-9a-f]{16,})")


def url_key(url: str) -> str:
    """把同一个帖子的多种链接形式归成一个键，验收查快照用。"""
    raw = (url or "").strip()
    if not raw:
        return ""
    host = (urlsplit(raw).hostname or "").lower()
    is_weibo = host.endswith("weibo.com") or host.endswith("weibo.cn")
    weibo = WEIBO_ID_RE.search(raw)
    if weibo:
        return f"weibo:{weibo.group(1)}"
    if is_weibo:
        # weibo.com/<uid>/<mid>：取最后一段纯数字，uid 不是帖子
        segments = [seg for seg in urlsplit(raw).path.split("/") if seg.isdigit() and len(seg) >= 10]
        if segments:
            return f"weibo:{segments[-1]}"
    xhs = XHS_ID_RE.search(raw)
    if xhs:
        return f"xhs:{xhs.group(1)}"
    parts = urlsplit(raw)
    if not parts.scheme:
        return raw.lower()
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def parse_weibo_date(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        return ""
    try:
        return parsedate_to_datetime(text).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        pass
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[: len(fmt) + 2].strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


def _in_window(date: str, since: str, until: str) -> bool:
    if not date:
        return False
    return since <= date <= until


def weibo_items(brand: str, channel: str, posts: list[dict], since: str, until: str) -> list[dict]:
    items = []
    for post in posts:
        text = str(post.get("text") or "").strip()
        url = str(post.get("url") or "")
        if not text or not url:
            continue
        date = parse_weibo_date(str(post.get("created") or ""))
        if not _in_window(date, since, until):
            continue
        items.append(
            {
                "brand": brand,
                "channel": channel,
                "type": "weibo",
                "id": str(post.get("mid") or ""),
                "url": url,
                "date": date,
                "text": text,
                "evidence": "weibo_post",
            }
        )
    return items


def xhs_items(brand: str, channel: str, notes: list[dict], limit: int = 24) -> list[dict]:
    """主页卡片没有日期，只能按「最近这些」给：限 len(notes) 条，避免把整页灌进提示词。"""
    items = []
    for note in notes[: max(1, limit)]:
        text = str(note.get("text") or "").strip()
        url = str(note.get("url") or "")
        if not text or not url:
            continue
        items.append(
            {
                "brand": brand,
                "channel": channel,
                "type": "xhs",
                "id": str(note.get("id") or ""),
                "url": url,
                "date": "",
                "text": text,
                "evidence": "xhs_card",
                "undated": True,
            }
        )
    return items


def snapshot_index(items: list[dict]) -> dict[str, str]:
    index: dict[str, str] = {}
    for item in items:
        key = url_key(item.get("url") or "")
        if key:
            index[key] = str(item.get("text") or "")
    return index


def digest(items: list[dict], limit: int = 220) -> str:
    """给提示词用的线索清单：每条一行，link 必须原样复制。"""
    lines = []
    for item in items:
        text = re.sub(r"\s+", " ", str(item.get("text") or "")).strip()
        if len(text) > limit:
            text = text[:limit] + "…"
        date = item.get("date") or "日期未知"
        flags = "（卡片无日期，判不了就不报）" if item.get("undated") else ""
        brands = item.get("brands") or [item["brand"]]
        brand_text = " / ".join(dict.fromkeys([b for b in brands if b]))
        lines.append(f"- {brand_text}｜{item['channel']}｜{date}{flags}\n  {text}\n  link: {item['url']}")
    return "\n".join(lines)


# ---------------------------------------------------------------- 公众号：DS 搜索

def wechat_queries(brand: str, channel: str, since: str) -> list[str]:
    """公众号一轮给两条查询：品牌名 + 公众号，账号名 + 品牌名，覆盖官方号与转载。"""
    month = f"{since[:4]}年{int(since[5:7])}月" if len(since) >= 7 else ""
    brand_name = re.sub(r"（[^）]*）", "", brand or "").strip()
    account = re.sub(r"^公众号\s*", "", channel or "").strip()
    queries = [f"{brand_name} 公众号 赏 新品 {month}".strip()]
    if account and account != brand_name:
        queries.append(f"{account} {brand_name} 新品 {month}".strip())
    return [q for q in dict.fromkeys(queries) if q]


def wechat_query(brand: str, since: str) -> str:
    """公众号没有可抓的列表页，只能靠搜索找文章；查询词带上月份，避免翻到旧文。"""
    month = f"{since[:4]}年{int(since[5:7])}月" if len(since) >= 7 else ""
    brand_name = re.sub(r"（[^）]*）", "", brand or "").strip()
    return f"{brand_name} 赏 新品 发售 {month}".strip()


def ds_hits(brand: str, channel: str, results: list[dict], since: str, until: str,
            limit: int = 6) -> list[dict]:
    """DS 搜索结果 → 公众号线索。只留带 URL 的，日期能给就带上，不在这里判真伪。"""
    floor = ""
    try:
        floor = (datetime.strptime(since, "%Y-%m-%d") - timedelta(days=30)).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        floor = ""

    def rank(row: dict) -> tuple:
        url = str(row.get("url") or "")
        host = (urlsplit(url).hostname or "").lower()
        return (0 if "mp.weixin.qq.com" in host else 1, str(row.get("date") or "")[::-1])

    hits = []
    for row in sorted(results, key=rank)[:limit]:
        url = str(row.get("url") or row.get("canonical_url") or "")
        if not url.startswith("http"):
            continue
        host = (urlsplit(url).hostname or "").lower()
        # 公众号渠道只收公众号文章：第三方站点交给 Agent 自己搜，避免把下载站/日版资讯混进来
        if "mp.weixin.qq.com" not in host:
            continue
        text = str(row.get("summary") or row.get("snippet") or "").strip()
        if not text:
            continue
        date = str(row.get("date") or "")[:10]
        date = date if len(date) == 10 else ""
        # 公众号不常更新：允许窗口前 30 天的文章当背景，太旧的不进提示词
        if date and floor and date < floor:
            continue
        hits.append(
            {
                "brand": brand,
                "channel": channel,
                "type": "wechat",
                "id": url,
                "url": url,
                "title": str(row.get("title") or "").strip(),
                "site": str(row.get("site_name") or ""),
                "date": date,
                "text": text,
                "evidence": "ds_summary",
            }
        )
    return hits


def ds_digest(hits: list[dict], limit: int = 160) -> str:
    """给提示词的 DS 候选清单：标题 / 日期 / 链接 / 摘要开头。"""
    lines = []
    for hit in hits:
        text = re.sub(r"\s+", " ", str(hit.get("text") or "")).strip()
        if len(text) > limit:
            text = text[:limit] + "…"
        lines.append(
            f"- {hit['brand']}｜{hit.get('site') or '公众号'}｜{hit.get('date') or '日期未知'}\n"
            f"  {hit.get('title') or ''}\n  {text}\n  link: {hit['url']}"
        )
    return "\n".join(lines)
