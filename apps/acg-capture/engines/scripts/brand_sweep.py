#!/usr/bin/env python3
"""[已停用 2026-10-23] 全品牌赏盘巡检：一轮扫完 brand-sources.md 里登记的所有微博账号，列出本轮缺哪些盘。

用法:
  python3 scripts/brand_sweep.py --since 2026-03-01 --pages 15
  python3 scripts/brand_sweep.py --since 2026-08-01 --json -o runtime/sweep.json
  python3 scripts/brand_sweep.py --brands 好物赏,卡游 --since 2026-03-01 \
      --skip-fetch --runtime-dir runtime/kuji-check --pan-json runtime/kuji-check/pan-now.json

输入:
  - references/brand-sources.md 的「## 微博账号清单（脚本读取）」表格（品牌 | 账号名 | uid | 覆盖范围说明）
    与该节里的追踪表 URL；账号只认这一节，uid 必须 4–12 位纯数字。
  - 各账号时间线 JSON（默认 <workspace>/runtime/weibo_<uid>.json）：缓存年龄 ≤ --max-age-hours
    且翻页数够（脚本会记 pages 元数据）时直接复用，--refresh 强制重拉；--runtime-dir 可指向别的缓存目录。
  - 追踪表 tmNNY2 的现有「商品名称」：默认调 wecom-cli 现读，--pan-json 可复用已导出的 records JSON。

输出:
  - 默认：表「品牌 | 账号 | 日期 | 盘名 | 状态(缺/已在表/预告排除) | 证据片段」+ 品牌结论 + 汇总行。
  - --json：结构化 JSON（accounts / items / excluded / blocked / brands / summary），-o 同时落盘。

退出码:
  0  巡检跑完（缺盘是正常结果，同样返回 0）
  1  参数错误（argparse）
  2  配置错误：读不到 brand-sources.md、账号清单为空、ego-browser / weibo_timeline.mjs 不存在
  3  表格读取失败：wecom-cli 报错、返回非 JSON 或没有 records
  4  其他未预期异常（打印 traceback，不静默返回空结果）

判定口径:
  - 发售：正文出现「正式发售 / 起陆续发售 / 已开售 / 开售 / 正式上线 / 现已上线 / 已发售 / 上新」等。
  - 排除：正文出现「即将上线 / 敬请期待 / 预告 / 预约 / 预售 / 上线日期待定 / 企划公开 / 阵容公开 /
    构成公开」等；同一帖既有明确发售词又有「预约/预售」时按发售处理，只有预告词没有发售词时才排除。
  - 判定前先降噪：剥掉 #话题标签# 与品牌赏词（乐淘赏/好物赏/KAYOU赏 等，清单从
    brand-sources.md 解析）。降噪后要有赏盘结构信号（赏品 / LAST赏 / 最终赏 / A赏 /
    兑换券 / 全N抽 / 一抽），或正文里出现品牌赏词（「系列好物赏」这类命名）才算赏盘。
  - 降噪后有发售词、但没有赏盘证据的（盲盒、毛绒、徽章、立牌、BJD 等周边），归 non_kuji，
    reason 写「周边/盲盒，非赏盘」，在汇总里单独计数（summary.non_kuji），不混进「预告排除」。
    只对本来带「赏」字样的帖子做这层判定；纯卡牌/周边帖直接忽略，避免汇总被灌满。
    发售词之前出现「盲盒/盲袋/BJD/流麻/录音机」的，即使带品牌赏词也按周边处理。
  - 汇总：缺盘 missing / 已在表 in_sheet / 预告排除 excluded / 周边排除 non_kuji / blocked 分开计数。
  - 日期：优先正文「M月D日」「YYYY年M月D日」，取不到用帖子 created（email.utils 解析 +0800 格式）；
    无年份的「M月D日」按 created 年份补，若 M 月比 created 月大 6 个月以上视为上一年。
  - 命中：商品名称与帖子正文都做归一化（去品牌赏名、系列、第N弹、括号内容、空格标点）后做包含匹配；
    两边都出现弹号但不重叠时直接判不命中（避免第3弹错配第4弹）。

注意:
  ego-browser 不把父进程环境变量传给脚本，因此本脚本为每个 uid 生成一个
  runtime/_sweep_job_<uid>.mjs 包装文件（内部 setenv 后再 import weibo_timeline.mjs）。
  手工拉时间线也要用同样的包装写法，见 README「最短路径」。
"""

# 停用说明：2026-10-23 起巡检改为「workbuddy + bitto 双 Agent 并查 + 官方渠道复核」，
# 本脚本只扫微博、且与双 Agent 检索重复，保留文件仅供回查历史结果，不再作为流程步骤。

import argparse
import datetime as dt
import email.utils
import html
import json
import os
import re
import subprocess
import sys
import time
import traceback
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKFLOW = HERE.parent
WS = WORKFLOW.parent.parent
BRAND_SOURCES = WORKFLOW / "references" / "brand-sources.md"
TIMELINE_SCRIPT = HERE / "weibo_timeline.mjs"

SHEET_ID = "tmNNY2"
DEFAULT_DOC = (
    "https://doc.weixin.qq.com/smartsheet/s3_Af0A3AZAAEcCNLf1EXDRzSXK0El6U"
    "?scode=ANYAEAdoABEnhQb30GAf0A3AZAAEc&tab=tmNNY2&viewId=viVT9X"
)
SECTION_TITLE = "## 微博账号清单（脚本读取）"

# 明确发售口径：出现即视为“已发售/已开售”的帖。
SALE_DEFINITE = [
    "正式发售", "起陆续发售", "陆续发售", "全网发售", "正式开售", "已开售",
    "全渠道开售", "现已全渠道开售", "正式上线", "今日正式上线", "今日全新上线",
    "今日上线", "全新上线", "现已上线", "现已正式上线", "重磅上线", "热血上线",
    "萌趣上线", "正式上新", "全新上新", "现已发售", "已发售", "现已上市",
    "现已登陆", "正式登场", "开售",
]
# 弱发售口径：没有明确词时兜底，但会被预告词优先覆盖。
SALE_SOFT = ["上线", "上新", "发售", "开卖", "登陆"]

# 排除口径（首个命中位置决定原因）；有序不代表优先级。
EXCLUDE_TERMS = [
    ("上线日期待定", "日期待定"), ("发售日期待定", "日期待定"), ("日期待定", "日期待定"),
    ("产品构成公开", "阵容/构成公开"), ("构成公开", "阵容/构成公开"),
    ("阵容公开", "阵容/构成公开"), ("赏品公开", "阵容/构成公开"),
    ("企划正式开启", "企划公开"), ("企划公开", "企划公开"), ("企划开启", "企划公开"),
    ("即将开售", "预告（即将开售）"), ("即将上线", "预告（即将上线）"),
    ("即将登场", "预告（即将登场）"), ("即将来袭", "预告（即将来袭）"),
    ("即将上市", "预告（即将上市）"), ("即将登陆", "预告（即将登陆）"),
    ("敬请期待", "预告（敬请期待）"), ("新品预告", "预告"), ("预告", "预告"),
    ("预约", "预约"), ("预售", "预售"),
    ("图透", "仅图透"), ("亮相", "仅亮相"), ("官宣", "仅官宣"),
]

# 活动/促销词：没有明确发售词时，这类帖不是赏盘。有明确发售词时不算，避免误杀开售帖。
ACTIVITY_TERMS = [
    "抽奖", "优惠券", "满赠", "签到", "打榜", "榜单", "兑换",
    "会员", "快讯", "周报", "日历", "攻略", "福利", "活动", "义卖",
]

DATE_RE = re.compile(r"(?:(\d{4})\s*年\s*)?(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]")
EMOJI_RE = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\uFE0F\u200d\u2B00-\u2BFF]+")
LABEL_RE = re.compile(
    r"^(?:新品上线|新品预告|新品实拍|新品上市|新品|实拍展示|实拍视频|实拍|视频展示|"
    r"产品展示|壁纸分享|企划开启|企划公开|重磅上线|正式上线|全新上线|官方首发|"
    r"官宣|情报|活动预告|预告|上新)[\s｜|丨:：]*"
)
TAIL_RE = re.compile(
    r"(系列|正式|今日|明日|现已|即将|重磅|全新|新品|首发|开售|发售|上线|登场|"
    r"来袭|公开|开启|亮相|预约|预售).*$"
)
SPLIT_RE = re.compile(r"[，。！!？?：:；;、\n｜|丨~～…︴]+")
# 赏盘结构信号：出现在「降噪后」正文里才算数（标签里的 #抽赏# 不算）。
STRUCT_RE = re.compile(
    r"(赏品|最终赏|[Ll][Aa][Ss][Tt]\s*赏|[A-Z]赏|[A-Za-z]{2,10}赏"
    r"|兑换券总数|共计\s*\d+\s*个?\s*兑换券|\d+\s*个\s*兑换券"
    r"|\d+\s*抽(?!\s*/\s*[盒箱包])|一抽)"
)
# 周边形态词：出现在发售词之前（标题位）时，即使带品牌赏词也不当赏盘。
PERIPHERAL_RE = re.compile(r"(盲盒|盲袋|BJD|流麻|录音机)")
HASHTAG_RE = re.compile(r"#[^#\n]{1,40}#")
TRAILING_TAG_RE = re.compile(r"#[^\s#]{1,30}")
BRAND_TOKEN_RE = re.compile(
    r"(好物赏|KAYOU赏|卡游赏|英雄赏|另物赏|磁力赏|乐淘赏|万花赏|万画赏|"
    r"甜梦赏|田野赏|美味赏|一番赏|福赏|有赏|秦赏令)"
)


class SweepConfigError(RuntimeError):
    """配置/环境错误：账号清单、脚本、ego-browser。"""


class SweepSheetError(RuntimeError):
    """追踪表读取失败。"""


# ---------------------------------------------------------------- 基础工具


def eprint(*args):
    print(*args, file=sys.stderr)


def display_width(text):
    width = 0
    for ch in text:
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def pad(text, width):
    return text + " " * max(0, width - display_width(text))


def truncate(text, limit):
    if display_width(text) <= limit:
        return text
    out = ""
    for ch in text:
        if display_width(out + ch) > limit - 1:
            break
        out += ch
    return out + "…"


def first_term_pos(text, terms):
    """返回 terms 中在 text 里最早出现的下标，找不到返回 None。"""
    best = None
    for term in terms:
        pos = text.find(term)
        if pos >= 0 and (best is None or pos < best):
            best = pos
    return best


def first_exclude_hit(text):
    """返回 (位置, 命中词, 原因)，按最早出现的位置取。"""
    best = None
    for term, reason in EXCLUDE_TERMS:
        pos = text.find(term)
        if pos >= 0 and (best is None or pos < best[0]):
            best = (pos, term, reason)
    return best


def parse_created(raw):
    """解析微博 created_at，如 'Wed Sep 30 13:00:00 +0800 2026'。"""
    if not raw:
        return None
    try:
        parsed = email.utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone(dt.timedelta(hours=8)))
    return parsed


def collapse(text, limit=110):
    text = EMOJI_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" -—·•|｜丨:：,，。!！?？~～\"“”'‘’")
    return truncate(text, limit)


def evidence_at(text, pos, limit=90):
    start = max(0, pos - 34)
    end = min(len(text), pos + 40)
    return collapse(text[start:end], limit)


def clean_title(raw):
    title = html.unescape(raw)
    title = EMOJI_RE.sub(" ", title)
    title = title.strip(" -—·•|｜丨:：,.，。!！?？~～\"“”'‘’")
    title = re.sub(r"#.*$", "", title).strip()
    title = title.replace("【", "").replace("】", "")
    title = re.sub(r"^@[^\s]{1,24}\s*", "", title)
    title = title.strip("「」『』【】《》〈〉")
    title = re.sub(r"^(?:授权|官方授权|联合出品|出品|今日|明日|现已|正式|全新|官方|全网|全渠道)+", "", title)
    title = title.strip("「」『』【】《》〈〉 ")
    title = re.sub(r"(?:今日|明日|现已|正式|全新|重磅|新品|首发|上线|开售|啦|了|！)+$", "", title)
    title = re.sub(r"\s+", " ", title).strip(" -—·•|｜丨:：,.，。")
    title = re.sub(r"^(.{4,24}?)\s+\1$", r"\1", title)
    return title[:44].strip()


def extract_title(text):
    """从帖文里抽一个可读的盘名，只用于报告；命中判定用的是整段正文。"""
    body = text.strip()
    body = re.sub(r"\s*\.{0,3}全文\s*$", "", body)
    body = re.sub(r"\s*查看图片\s*$", "", body)
    for _ in range(2):
        match = LABEL_RE.match(body)
        if match and match.end() > 0:
            body = body[match.end():]
        else:
            break

    match = re.search(r"《([^》]{1,40})》", body)
    if match:
        ip_name = match.group(1).strip()
        rest = body[match.end():]
        partner = re.match(r"\s*[×xX]\s*《([^》]{1,40})》", rest)
        if partner:
            ip_name += "×" + partner.group(1).strip()
            rest = rest[partner.end():]
        name = TAIL_RE.sub("", rest, count=1)
        name = clean_title(name)
        return (ip_name + " " + name).strip() if name else ip_name

    body = EMOJI_RE.sub("︴", body)
    spans = []
    cursor = 0
    for match in SPLIT_RE.finditer(body):
        if match.start() > cursor:
            spans.append((cursor, match.start()))
        cursor = match.end()
    if cursor < len(body):
        spans.append((cursor, len(body)))

    kpos = first_term_pos(body, SALE_DEFINITE)
    if kpos is None:
        kpos = first_term_pos(body, SALE_SOFT)
    best = None
    for start, end in spans:
        raw = re.sub(r"【[^】]{0,12}】", "", body[start:end]).strip()
        if len(raw) < 2:
            continue
        candidate = clean_title(TAIL_RE.sub("", raw, count=1)) or clean_title(raw)
        if len(candidate) < 2:
            continue
        if re.fullmatch(r"(?:LAST|last|[A-Z]|第[0-9一二三四五六七八九十]+)\s*赏", candidate):
            continue
        if re.fullmatch(r"[0-9:：.\s]+", candidate):
            continue
        score = min(len(raw) / 24.0, 1.2)
        if "赏" in raw or "賞" in raw:
            score += 3
        if 4 <= len(candidate) <= 30:
            score += 1
        if kpos is not None and start <= kpos < end:
            score += 2.5
        if DATE_RE.search(candidate) and len(candidate) <= 10:
            score -= 4
        if DATE_RE.match(candidate) and len(candidate) <= 14:
            score -= 4
        if re.match(r"(超|更|还|另|以及|同时|并且|而且|其中|此外|不仅|另有|还有)", candidate):
            score -= 2
        if re.search(r"[与和及、]$", raw.strip()):
            score -= 2
        if re.search(
            r"(活动|福利|抽奖|满赠|优惠券|会员|快闪|门店|展位|攻略|日历|转发|评论|点赞|"
            r"产品信息|规格|价格|尺寸|cm|内含|兑换券|赏卡—|领取|获取)",
            raw,
        ):
            score -= 2
        if best is None or score > best[0]:
            best = (score, candidate)
    if best is not None:
        return best[1]
    return clean_title(TAIL_RE.sub("", body[:34], count=1))


def resolve_date(text, created):
    """返回 (date, source)；source 为 'text' 或 'post'。"""
    matches = list(DATE_RE.finditer(text))
    if not matches:
        return created.date(), "post"

    candidates = []
    for match in matches:
        year = int(match.group(1)) if match.group(1) else created.year
        month = int(match.group(2))
        day = int(match.group(3))
        # "Vol.29月11日" 这类：版本号尾数字被吞进月份（29 月），按个位还原
        if month > 12:
            month = month - 20 if month >= 20 else month - 10
        if not 1 <= month <= 12 or not 1 <= day <= 31:
            continue
        if not match.group(1) and month > created.month + 6:
            year -= 1
        try:
            value = dt.date(year, month, day)
        except ValueError:
            continue
        candidates.append({"start": match.start(), "date": value})
    if not candidates:
        return created.date(), "post"

    kpos = first_term_pos(text, SALE_DEFINITE)
    if kpos is None:
        kpos = first_term_pos(text, SALE_SOFT)
    if kpos is None:
        return candidates[0]["date"], "text"

    before = [item for item in candidates if item["start"] <= kpos]
    chosen = before[-1] if before else candidates[0]
    return chosen["date"], "text"


def key_norm(value):
    return re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", (value or "").lower())


_CN_DIGITS = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6,
              "七": 7, "八": 8, "九": 9}


def cn_number(raw):
    """把「五」「十二」「二十三」转成 5/12/23；已是数字就原样返回。"""
    if raw.isdigit():
        return raw
    if raw == "十":
        return "10"
    if "十" in raw:
        left, _, right = raw.partition("十")
        tens = _CN_DIGITS.get(left, 1) if left else 1
        ones = _CN_DIGITS.get(right, 0) if right else 0
        return str(tens * 10 + ones)
    return str(_CN_DIGITS.get(raw, raw))


def dan_numbers(text):
    """抽正文/商品名里的弹号，用于避免「第3弹」错配「第4弹」。"""
    found = set()
    for raw in re.findall(r"第([0-9一二三四五六七八九十百]+)弹", text or ""):
        found.add(cn_number(raw))
    return found


def norm_text(value):
    """归一化：去品牌赏名、赏、系列、第N弹、括号内容、标点空格。"""
    value = html.unescape(value or "")
    value = value.replace("（", "(").replace("）", ")")
    value = re.sub(r"\([^)]{0,60}\)", "", value)
    value = BRAND_TOKEN_RE.sub("", value)
    value = value.replace("賞", "赏").replace("赏", "")
    value = re.sub(r"第[0-9一二三四五六七八九十百]+弹", "", value)
    value = re.sub(r"(系列|全新|新品|官方|正版|授权|周边|商品|产品|正式|今日|现已|上线|发售|开售)", "", value)
    value = re.sub(r"[^0-9a-z\u4e00-\u9fff]", "", value.lower())
    return value


# ---------------------------------------------------------------- 账号清单


def extract_brand_tokens(cells):
    """从品牌单元格里拆出「XX赏」品牌词，用于降噪与信号判定。"""
    tokens = set()
    for cell in cells:
        for piece in re.split(r"[（）()/／\s、,，:：|]+", cell or ""):
            piece = piece.strip().strip("`")
            if not piece:
                continue
            if piece == "秦赏令":
                tokens.add(piece)
            elif re.fullmatch(r"[A-Za-z]{2,10}赏", piece) or re.fullmatch(
                r"[\u4e00-\u9fff]{1,8}赏", piece
            ):
                tokens.add(piece)
    return sorted(tokens, key=len, reverse=True)


def strip_hashtags(text):
    """剥掉 #...# 话题标签，避免把 #乐淘赏# / #抽赏# 当成赏盘证据。"""
    text = HASHTAG_RE.sub(" ", text or "")
    text = TRAILING_TAG_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def strip_brand_tokens(text, tokens):
    for token in tokens:
        if token in text:
            text = text.replace(token, " ")
    return re.sub(r"\s+", " ", text).strip()


def load_brand_sources(path):
    if not path.exists():
        raise SweepConfigError("读不到品牌信息源：%s" % path)
    text = path.read_text(encoding="utf-8")
    match = re.search(
        r"^" + re.escape(SECTION_TITLE) + r"[^\n]*\n(.*?)(?=^##\s|\Z)",
        text,
        re.S | re.M,
    )
    if not match:
        raise SweepConfigError(
            "brand-sources.md 缺少「%s」一节，脚本拒绝猜测账号" % SECTION_TITLE
        )
    section = match.group(1)

    accounts = []
    seen = set()
    for line in section.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [cell.strip().strip("`").strip() for cell in line.strip("|").split("|")]
        if len(cells) < 4:
            continue
        uid = cells[2]
        if not re.fullmatch(r"\d{4,12}", uid):
            continue
        if uid in seen:
            continue
        seen.add(uid)
        accounts.append(
            {"brand": cells[0], "account": cells[1], "uid": uid, "scope": cells[3]}
        )
    if not accounts:
        raise SweepConfigError("「%s」里没有解析出任何账号行" % SECTION_TITLE)

    brand_cells = [acc["brand"] for acc in accounts]
    brand_table = re.search(r"^## 国内抽赏品牌[^\n]*\n(.*?)(?=^##\s|\Z)", text, re.S | re.M)
    if brand_table:
        for line in brand_table.group(1).splitlines():
            line = line.strip()
            if not line.startswith("|"):
                continue
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if cells and cells[0] and not cells[0].startswith("---"):
                brand_cells.append(cells[0])
    tokens = extract_brand_tokens(brand_cells)

    doc = DEFAULT_DOC
    doc_match = re.search(r"https://doc\.weixin\.qq\.com/smartsheet/[^\s)|>]+", section)
    if not doc_match:
        doc_match = re.search(r"https://doc\.weixin\.qq\.com/smartsheet/[^\s)|>]+", text)
    if doc_match:
        doc = doc_match.group(0)
    return accounts, doc, tokens


# ---------------------------------------------------------------- 追踪表


def cell_text(values, key):
    value = values.get(key)
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and item.get("text"):
                return str(item["text"]).strip()
        return ""
    if isinstance(value, dict) and value.get("text"):
        return str(value["text"]).strip()
    return str(value).strip()


def load_sheet_rows(doc, sheet_id, limit, pan_json=None):
    if pan_json:
        path = Path(pan_json)
        if not path.exists():
            raise SweepSheetError("--pan-json 文件不存在：%s" % path)
        raw = path.read_text(encoding="utf-8")
    else:
        cmd = [
            "wecom-cli", "smartsheet", "records", "list",
            "--docid", doc, "--sheet-id", sheet_id,
            "--type", "records", "--limit", str(limit),
        ]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except FileNotFoundError:
            raise SweepSheetError("wecom-cli 不在 PATH 里，无法读取追踪表")
        except subprocess.TimeoutExpired:
            raise SweepSheetError("wecom-cli 读取追踪表超时（180s）")
        if proc.returncode != 0:
            raise SweepSheetError(
                "wecom-cli 返回 %s：%s" % (proc.returncode, (proc.stderr or proc.stdout).strip()[:400])
            )
        raw = proc.stdout

    data = None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        if start >= 0:
            try:
                data = json.loads(raw[start:])
            except json.JSONDecodeError:
                data = None
    if not isinstance(data, dict) or "records" not in data:
        raise SweepSheetError("追踪表返回内容不是 records JSON：%s" % raw.strip()[:200])
    if data.get("errcode") not in (0, None):
        raise SweepSheetError(
            "追踪表返回 errcode=%s errmsg=%s" % (data.get("errcode"), data.get("errmsg"))
        )

    rows = []
    for record in data["records"]:
        values = record.get("values") or {}
        name = cell_text(values, "商品名称")
        if not name:
            continue
        rows.append(
            {
                "record_id": record.get("record_id", ""),
                "brand": cell_text(values, "品牌"),
                "name": name,
                "date": cell_text(values, "发售日期"),
                "alias": cell_text(values, "商品别名"),
                "already": cell_text(values, "是否已发售"),
                "norm": norm_text(name),
            }
        )
    if not rows:
        raise SweepSheetError("追踪表 tmNNY2 里没有带「商品名称」的行，比对无法进行")
    return rows, len(data["records"])


def match_sheet(post_norm, rows, post_text):
    """表格「商品名称」归一化后与帖子正文做包含匹配。

    归一化会去掉「第N弹」，因此额外用弹号做一次冲突过滤：两边都写了弹号且不重叠时，
    这一行直接不算命中（避免「第3弹」错配「第4弹」）。3 段以上的表名允许缺一段副标题，
    以兼容卡游系「同一盘不同叫法」。
    """
    post_dan = dan_numbers(post_text)

    for row in rows:
        row_dan = dan_numbers(row["name"])
        if row_dan and post_dan and not (row_dan & post_dan):
            continue
        if len(row["norm"]) >= 4 and row["norm"] in post_norm:
            return row["name"]
        parts = [
            part for part in (norm_text(piece) for piece in re.split(r"[\s×x]+", row["name"]))
            if len(part) >= 2
        ]
        if not parts:
            continue
        if len(parts) >= 2 and any(len(part) >= 4 for part in parts):
            if all(part in post_norm for part in parts):
                return row["name"]
        if len(parts) >= 2 and (len(parts) >= 3 or row_dan):
            prefix = "".join(parts[:-1])
            if len(prefix) >= 4 and prefix in post_norm:
                return row["name"]
        if row_dan and len(parts) >= 2 and parts[0] in post_norm:
            hits = sum(1 for part in parts if part in post_norm)
            if hits >= len(parts) - 1:
                return row["name"]
    return None


# ---------------------------------------------------------------- 时间线抓取


def cache_age_hours(path):
    return (time.time() - path.stat().st_mtime) / 3600.0


def read_cache_meta(path):
    meta_path = path.with_suffix(".meta.json")
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def write_cache_meta(path, pages):
    path.with_suffix(".meta.json").write_text(
        json.dumps({"pages": pages, "fetched_at": dt.datetime.now().isoformat(timespec="seconds")}),
        encoding="utf-8",
    )


def read_posts(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, list) or not data:
        return None
    if not any(isinstance(post, dict) and post.get("text") for post in data):
        return None
    return data


def write_wrapper(runtime_dir, uid, pages):
    """ego-browser 不继承父进程 env，用包装脚本在 JS 内注入 WEIBO_* 再 import 原脚本。"""
    wrapper = runtime_dir / ("_sweep_job_%s.mjs" % uid)
    out_path = runtime_dir / ("weibo_%s.json" % uid)
    body = (
        "// generated by brand_sweep.py (ego-browser drops parent env)\n"
        "process.env.WEIBO_UID = %s;\n"
        "process.env.WEIBO_PAGES = %s;\n"
        "process.env.WEIBO_OUT = %s;\n"
        "await import(%s);\n"
        % (
            json.dumps(str(uid)),
            json.dumps(str(pages)),
            json.dumps(str(out_path)),
            json.dumps(TIMELINE_SCRIPT.resolve().as_uri()),
        )
    )
    wrapper.write_text(body, encoding="utf-8")
    return wrapper


def fetch_timeline(acc, runtime_dir, pages, max_age_hours, refresh, skip_fetch,
                   timeout, retries):
    """返回 (status, posts, age_hours, error)。status ∈ ok/cached/blocked。"""
    uid = acc["uid"]
    out_path = runtime_dir / ("weibo_%s.json" % uid)

    posts = read_posts(out_path) if out_path.exists() else None
    if posts is not None and not refresh:
        age = cache_age_hours(out_path)
        cached_pages = read_cache_meta(out_path).get("pages")
        covered = cached_pages is None or int(cached_pages) >= pages
        if age <= max_age_hours and covered:
            return "cached", posts, round(age, 2), ""
    if skip_fetch:
        if posts is not None:
            return "blocked", [], None, (
                "缓存只翻了 %s 页（本次请求 %s 页），且指定了 --skip-fetch"
                % (read_cache_meta(out_path).get("pages", "未知"), pages)
            )
        return "blocked", [], None, "无有效缓存，且指定了 --skip-fetch"

    if not TIMELINE_SCRIPT.exists():
        raise SweepConfigError("找不到时间线脚本：%s" % TIMELINE_SCRIPT)
    wrapper = write_wrapper(runtime_dir, uid, pages)

    attempts = 0
    last_error = ""
    while attempts <= retries:
        attempts += 1
        started = time.time()
        env = dict(os.environ)
        env.update({"WEIBO_UID": str(uid), "WEIBO_PAGES": str(pages),
                    "WEIBO_OUT": str(out_path)})
        cmd = ["ego-browser", "nodejs"]
        try:
            with open(wrapper, "rb") as handle:
                proc = subprocess.run(
                    cmd, stdin=handle, capture_output=True, text=True,
                    timeout=timeout, env=env,
                )
        except FileNotFoundError:
            raise SweepConfigError("ego-browser 不在 PATH 里，无法拉时间线")
        except subprocess.TimeoutExpired:
            last_error = "超时（%.0fs）" % timeout
            continue

        if proc.returncode != 0:
            last_error = "ego-browser 退出码 %s：%s" % (
                proc.returncode, (proc.stderr or proc.stdout).strip().splitlines()[-1][:200]
                if (proc.stderr or proc.stdout).strip() else "无输出"
            )
            continue

        fresh = out_path.exists() and out_path.stat().st_mtime >= started - 5
        posts = read_posts(out_path) if fresh else None
        if posts is None:
            detail = (proc.stderr or proc.stdout).strip().splitlines()
            last_error = "空结果或无效 JSON%s" % ("：" + detail[-1][:160] if detail else "")
            continue

        write_cache_meta(out_path, pages)
        wrapper.unlink(missing_ok=True)
        return "ok", posts, 0.0, ""

    wrapper.unlink(missing_ok=True)
    return "blocked", [], None, "%s（尝试 %d 次）" % (last_error or "未知原因", attempts)


# ---------------------------------------------------------------- 单帖判定


def classify_post(post, since, brand_tokens):
    """返回 (kind, payload)；kind ∈ sale / excluded / non_kuji / ignored / before_since。

    先降噪（剥 hashtag、剥品牌赏词），再找发售/预告口径；正文里没有任何赏盘结构信号
    （赏品/LAST/最终赏/A赏/兑换券/N抽/一抽）也不是品牌赏词用法时，归 non_kuji。
    """
    text = post.get("text") or ""
    if not text.strip():
        return "ignored", None
    created = parse_created(post.get("created"))
    if created is None:
        return "ignored", None

    body = strip_hashtags(text)
    denoised = strip_brand_tokens(body, brand_tokens)

    # 口径判定用「去标签后的正文」，位置可直接用于证据片段；结构信号才用降噪文本。
    sale_pos = first_term_pos(body, SALE_DEFINITE)
    exclude = first_exclude_hit(body)
    activity = first_term_pos(body, ACTIVITY_TERMS)
    soft_pos = first_term_pos(body, SALE_SOFT)

    if sale_pos is not None:
        kind = "sale"
        anchor = sale_pos
    elif exclude is not None:
        kind = "excluded"
        anchor = exclude[0]
    elif activity is not None:
        kind = "excluded"
        anchor = activity
    elif soft_pos is not None:
        kind = "sale"
        anchor = soft_pos
    else:
        return "ignored", None

    # 赏盘证据：降噪后的结构信号，或正文里出现的品牌赏词（「系列好物赏」这类命名）。
    has_structure = bool(STRUCT_RE.search(denoised))
    brand_in_body = any(token in body for token in brand_tokens)
    peripheral_headline = bool(PERIPHERAL_RE.search(body[:anchor]))
    is_kuji = has_structure or (brand_in_body and not peripheral_headline)
    # 只对「本来就带赏字样」的帖子做 non_kuji 判定；纯卡牌/周边帖直接忽略，避免汇总被灌满。
    has_kuang_token = ("赏" in text) or any(token in text for token in brand_tokens)

    post_date, date_source = resolve_date(body, created)
    if post_date < since:
        return "before_since", None

    title = extract_title(body)
    payload = {
        "date": post_date.isoformat(),
        "date_source": date_source,
        "title": title,
        "created": created.isoformat(),
        "mid": post.get("mid", ""),
        "url": "https://m.weibo.cn/detail/%s" % post.get("mid", ""),
        "evidence": evidence_at(body, anchor),
    }
    if kind == "excluded":
        if not is_kuji:
            return "ignored", None
        payload["reason"] = exclude[2] if exclude is not None else "活动/非盘"
        payload["status"] = "excluded"
        return kind, payload
    if not is_kuji:
        if not has_kuang_token:
            return "ignored", None
        payload["reason"] = "周边/盲盒，非赏盘"
        payload["status"] = "non_kuji"
        return "non_kuji", payload
    return "sale", payload


# ---------------------------------------------------------------- 主流程


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="全品牌赏盘巡检：扫完 brand-sources.md 登记的所有微博账号，列出本轮缺盘。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--since", help="只保留发售日期 >= 该日（YYYY-MM-DD，默认今天-30 天）")
    parser.add_argument("--pages", type=int, default=15, help="每个账号翻页数（默认 15）")
    parser.add_argument("--json", action="store_true", help="输出结构化 JSON 而不是表格")
    parser.add_argument("-o", "--out", help="把 JSON 写到该路径")
    parser.add_argument("--doc", help="追踪表 docid URL（默认从 brand-sources.md 读）")
    parser.add_argument("--sheet-id", default=SHEET_ID, help="赏盘子表 id（默认 tmNNY2）")
    parser.add_argument("--limit", type=int, default=1000, help="读表行数上限（默认 1000）")
    parser.add_argument("--pan-json", help="复用已导出的 records JSON，不调 wecom-cli")
    parser.add_argument("--brands", help="只跑这些账号（品牌名/账号名子串，逗号分隔）")
    parser.add_argument("--runtime-dir", default=str(WS / "runtime"),
                        help="时间线缓存目录（默认 <workspace>/runtime）")
    parser.add_argument("--max-age-hours", type=float, default=12,
                        help="缓存有效期，单位小时（默认 12）")
    parser.add_argument("--refresh", action="store_true", help="忽略缓存强制重拉")
    parser.add_argument("--skip-fetch", action="store_true", help="完全不联网，只用缓存")
    parser.add_argument("--fetch-timeout", type=int, default=180, help="单账号抓取超时秒数")
    parser.add_argument("--retries", type=int, default=1, help="单个账号失败后最多重试次数（默认 1）")
    args = parser.parse_args(argv)

    today = dt.date.today()
    if args.since:
        try:
            since = dt.date.fromisoformat(args.since)
        except ValueError:
            raise SweepConfigError("--since 不是合法日期：%s" % args.since)
    else:
        since = today - dt.timedelta(days=30)

    runtime_dir = Path(args.runtime_dir).expanduser().resolve()
    runtime_dir.mkdir(parents=True, exist_ok=True)

    accounts, doc, brand_tokens = load_brand_sources(BRAND_SOURCES)
    if args.doc:
        doc = args.doc

    brand_filters = [token.strip() for token in (args.brands or "").split(",") if token.strip()]
    if brand_filters:
        accounts = [
            acc for acc in accounts
            if any(token in acc["brand"] or token in acc["account"] for token in brand_filters)
        ]
        if not accounts:
            raise SweepConfigError("--brands 没有匹配到任何登记账号")

    if not TIMELINE_SCRIPT.exists():
        raise SweepConfigError("找不到时间线脚本：%s" % TIMELINE_SCRIPT)

    rows, sheet_total = load_sheet_rows(doc, args.sheet_id, args.limit, args.pan_json)

    items = []
    item_index = {}
    excluded = []
    brand_stats = {}
    account_reports = []
    blocked = []

    for acc in accounts:
        status, posts, age, error = fetch_timeline(
            acc, runtime_dir, args.pages, args.max_age_hours,
            args.refresh, args.skip_fetch, args.fetch_timeout, args.retries,
        )
        report = {
            "brand": acc["brand"],
            "account": acc["account"],
            "uid": acc["uid"],
            "scope": acc["scope"],
            "status": status,
            "posts": len(posts),
            "cache_age_hours": age,
            "error": error,
        }
        account_reports.append(report)
        stats = brand_stats.setdefault(
            acc["brand"], {"accounts": 0, "ok": 0, "blocked": 0,
                           "missing": 0, "in_sheet": 0, "excluded": 0, "non_kuji": 0}
        )
        stats["accounts"] += 1
        if status == "blocked":
            stats["blocked"] += 1
            blocked.append({
                "brand": acc["brand"], "account": acc["account"],
                "uid": acc["uid"], "reason": error,
            })
            continue
        stats["ok"] += 1

        for post in posts:
            kind, payload = classify_post(post, since, brand_tokens)
            if kind in ("ignored", "before_since"):
                continue
            title = payload["title"]
            post_norm = norm_text(post.get("text") or "")
            matched = match_sheet(post_norm, rows, post.get("text") or "")
            if kind in ("excluded", "non_kuji"):
                payload.update({
                    "brand": acc["brand"], "account": acc["account"], "uid": acc["uid"],
                    "matched_name": matched or "", "in_sheet": False,
                })
                excluded.append(payload)
                stats[kind] += 1
                continue

            status_name = "in_sheet" if matched else "missing"
            if matched:
                key = (acc["brand"], "sheet::" + matched)
            else:
                key = (acc["brand"], "new::" + key_norm(title))
            if key in item_index:
                existing = item_index[key]
                existing["sources"].append({"account": acc["account"], "uid": acc["uid"]})
                if matched and existing["status"] == "missing":
                    existing["status"] = "in_sheet"
                    existing["in_sheet"] = True
                    existing["matched_name"] = matched
                if existing["date_source"] != "text" and payload["date_source"] == "text":
                    existing["date"] = payload["date"]
                    existing["date_source"] = "text"
                    existing["evidence"] = payload["evidence"]
                continue
            item = {
                "brand": acc["brand"], "account": acc["account"], "uid": acc["uid"],
                "date": payload["date"], "date_source": payload["date_source"],
                "title": title, "status": status_name,
                "in_sheet": bool(matched),
                "matched_name": matched or "",
                "evidence": payload["evidence"], "created": payload["created"],
                "url": payload["url"], "mid": payload["mid"],
                "sources": [{"account": acc["account"], "uid": acc["uid"]}],
            }
            item_index[key] = item
            items.append(item)
            stats[status_name] += 1

    items.sort(key=lambda item: (item["brand"], item["date"], item["title"]))
    excluded.sort(key=lambda item: (item["brand"], item["date"], item["title"]))

    summary = {
        "missing": sum(1 for item in items if item["status"] == "missing"),
        "in_sheet": sum(1 for item in items if item["status"] == "in_sheet"),
        "excluded": sum(1 for item in excluded if item.get("status") == "excluded"),
        "non_kuji": sum(1 for item in excluded if item.get("status") == "non_kuji"),
        "blocked": len(blocked),
        "accounts": len(accounts),
        "accounts_ok": sum(1 for acc in account_reports if acc["status"] != "blocked"),
        "sheet_rows": sheet_total,
    }
    result = {
        "generated_at": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
        "since": since.isoformat(),
        "today": today.isoformat(),
        "doc": doc,
        "sheet_id": args.sheet_id,
        "runtime_dir": str(runtime_dir),
        "accounts": account_reports,
        "items": items,
        "excluded": excluded,
        "blocked": blocked,
        "brands": brand_stats,
        "summary": summary,
    }

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(result, since)

    return 0


def print_report(result, since):
    summary = result["summary"]
    header = ["品牌", "账号", "日期", "盘名", "状态", "证据片段"]
    rows = []
    for item in result["items"]:
        rows.append([
            item["brand"], item["account"], item["date"], item["title"],
            "缺" if item["status"] == "missing" else "已在表", item["evidence"],
        ])
    for item in result["excluded"]:
        rows.append([
            item["brand"], item["account"], item["date"], item["title"],
            "周边排除" if item.get("status") == "non_kuji" else "预告排除",
            item["reason"] + "｜" + item["evidence"],
        ])

    widths = [display_width(text) for text in header]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], min(display_width(cell), 46))

    print("巡检窗口：%s 起 → %s；追踪表 %s；账号 %d 个" % (
        result["since"], result["today"], result["sheet_id"], summary["accounts"]))
    print("")
    print(" | ".join(pad(head, widths[index]) for index, head in enumerate(header)))
    print("-+-".join("-" * widths[index] for index in range(len(header))))
    for row in rows:
        cells = [
            truncate(row[0], widths[0]), truncate(row[1], widths[1]),
            row[2], truncate(row[3], widths[3]), truncate(row[4], widths[4]),
            truncate(row[5], widths[5]),
        ]
        print(" | ".join(pad(cell, widths[index]) for index, cell in enumerate(cells)))

    if result["blocked"]:
        print("")
        print("blocked 账号：")
        for entry in result["blocked"]:
            print("  - %s / %s（%s）：%s" % (
                entry["brand"], entry["account"], entry["uid"], entry["reason"]))

    print("")
    print("品牌结论：")
    for brand, stats in result["brands"].items():
        conclusion = "缺 %d / 已在表 %d / 预告排除 %d / 周边排除 %d" % (
            stats["missing"], stats["in_sheet"], stats["excluded"], stats["non_kuji"])
        if stats["blocked"]:
            conclusion += " / blocked 账号 %d（原因见上）" % stats["blocked"]
        print("  - %s：%s" % (brand, conclusion))

    print("")
    print("本轮缺盘 %d 个 / 已在表 %d 个 / 预告排除 %d 个 / 周边排除 %d 个 / blocked 账号 %d 个" % (
        summary["missing"], summary["in_sheet"], summary["excluded"],
        summary["non_kuji"], summary["blocked"]))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SweepConfigError as error:
        eprint("配置错误：%s" % error)
        sys.exit(2)
    except SweepSheetError as error:
        eprint("表格读取失败：%s" % error)
        sys.exit(3)
    except KeyboardInterrupt:
        eprint("已中断")
        sys.exit(130)
    except Exception:
        traceback.print_exc()
        sys.exit(4)
