#!/usr/bin/env python3
"""WeCom document archiver (accuracy-first).

Usage example:
  python3 tools/wecom_archive.py \
    --draft /tmp/wecom_doc_decoded_draft.md \
    --structured /tmp/wecom_doc_structured_tables.md \
    --out-dir /tmp
"""

from __future__ import annotations

import argparse
import html
import re
import urllib.request
from pathlib import Path
from typing import Iterable


STANDARD_TEXT = """# 企微文档归档标准（准确性优先）

## 双轨存档
1. RAW轨（不可变）
- 目的: 保留原始证据，任何信息可回溯。
- 规则: 只做字节级保存，不做语义修改。

2. AI轨（可处理）
- 目的: 给模型输入，降低噪声，保留事实。
- 规则: 仅允许“确定性清理”，禁止改写事实。

## AI轨允许操作
- 删除: 图片占位、渲染注释、确定的系统噪声。
- 规范: 统一换行与空白；表格行改为管道文本（不做视觉还原）。
- 保留: 指标、时间、结论、TODO、埋点事件名、条件阈值。

## AI轨禁止操作
- 禁止润色改写（同义替换、总结性删减）。
- 禁止主观补全缺失字段。
- 禁止基于图片内容臆断文本。

## 质量门槛
- 关键锚点必须可检索:
  - T3入口 / 魔力赏频道页
  - 商详->下单：10%->40%
  - 列表->详情：54%->60%
  - 合规性 / 赌博 / 风控
  - 方案① / 方案②
  - mall.* / maill.* 埋点事件
"""


ANCHORS = [
    "T3入口",
    "魔力赏频道页",
    "商详->下单：10%->40%",
    "列表->详情：54%->60%",
    "合规性",
    "赌博",
    "风控",
    "方案①",
    "方案②",
    "mall.",
]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text)


def extract_draft_content(raw: str) -> str:
    m = re.search(r"## Content \(cleaned draft\)\s*\n([\s\S]*)$", raw)
    if m:
        return m.group(1)
    return raw


def fetch_url_html(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    return data.decode("utf-8", errors="ignore")


def html_to_text(html_content: str) -> str:
    # Remove script/style/no-script blocks first.
    s = re.sub(r"<script[\\s\\S]*?</script>", " ", html_content, flags=re.I)
    s = re.sub(r"<style[\\s\\S]*?</style>", " ", s, flags=re.I)
    s = re.sub(r"<noscript[\\s\\S]*?</noscript>", " ", s, flags=re.I)
    # Convert line break-ish tags to newlines.
    s = re.sub(r"<\\s*br\\s*/?>", "\\n", s, flags=re.I)
    s = re.sub(r"</\\s*(p|div|li|tr|h[1-6])\\s*>", "\\n", s, flags=re.I)
    # Strip remaining tags.
    s = re.sub(r"<[^>]+>", " ", s)
    s = html.unescape(s)
    s = s.replace("\\r", "\\n")
    s = re.sub(r"\\n{3,}", "\\n\\n", s)
    s = re.sub(r"[ \\t]{2,}", " ", s)
    return s.strip()


def seems_shell_page(text: str) -> bool:
    t = (text or "").strip()
    if len(t) < 200:
        return True
    cjk = sum(1 for ch in t if "\u4e00" <= ch <= "\u9fff")
    return cjk < 20


def strip_known_draft_noise(text: str) -> str:
    text = text.replace("\r", "\n").replace("\\r", "\n")
    patterns = [
        r"HYPERLINK\s+https://doc\.weixin\.qq\.com/flowchart-addon[\s\S]{0,600}?https://doc\.weixin\.qq\.com/flowchart-addon",
        r"\bdw\s+\d+\s+dh\s+\d+\s+dlt\s+preview\b[\s\S]{0,500}?https://doc\.weixin\.qq\.com/flowchart-addon",
        r"\baddonHina\b",
        r"%7B%22id%22%3A%22[\w%]+",
        r"@fJ\s*I",
        r"@eJ\s*IP",
    ]
    for p in patterns:
        text = re.sub(p, " ", text)
    return text


def _is_image_placeholder(line: str) -> bool:
    return bool(re.match(r"^\[IMAGE_PLACEHOLDER[^\]]*\]\([^)]*\)\s*$", line.strip()))


def _is_comment_noise(line: str) -> bool:
    return bool(re.match(r"^<!--\s*C端方案-相关图片\s*-->$", line.strip()))


def _table_sep_line(line: str) -> bool:
    s = line.strip()
    return s.startswith("|") and bool(
        re.fullmatch(r"\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?", s)
    )


def normalize_symbol_noise(s: str) -> str:
    s = s.replace("““", "“").replace("””", "”")
    s = s.replace("（（", "（").replace("））", "）")
    s = s.replace("→→", "→")
    s = s.replace("//", "/")
    return s


def classify_line_kind(s: str) -> str:
    t = s.strip()
    if not t:
        return "blank"
    if re.match(r"^([\-*•●○]|[0-9]+[\.、])\s*", t):
        return "list"
    if re.match(r'^(?:\{|\}|\[|\]|".*":|@Schema|@Data|public class|private\s+\w+)', t):
        return "code"
    if re.match(r"^[\u4e00-\u9fffA-Za-z0-9_\-（）()]{2,24}$", t) and not re.search(r"[：:]", t):
        return "heading"
    if (
        len(t) <= 16
        and re.match(r"^[\u4e00-\u9fffA-Za-z0-9_#\-\./]+$", t)
        and not re.search(r"[：:]", t)
    ):
        return "cell"
    return "text"


def should_insert_group_break(prev_kind: str, cur_kind: str) -> bool:
    if prev_kind == "blank" or cur_kind == "blank":
        return False
    if cur_kind == "heading" and prev_kind != "heading":
        return True
    if prev_kind == "heading" and cur_kind not in {"heading", "list", "cell"}:
        return True
    if (prev_kind == "list") != (cur_kind == "list"):
        return True
    if (prev_kind == "code") != (cur_kind == "code"):
        return True
    if (prev_kind == "cell") != (cur_kind == "cell"):
        return True
    return False


def is_garbled_line(s: str) -> bool:
    t = s.strip()
    if not t:
        return True
    if "�" in t:
        return True
    if re.search(r"-apple-system|PingFang SC|Monaco", t):
        return True
    if re.match(r"^:[^\u4e00-\u9fffA-Za-z0-9]{1,8}$", t):
        return True
    visible = [ch for ch in t if not ch.isspace()]
    if not visible:
        return True
    normal = 0
    for ch in visible:
        if "\u4e00" <= ch <= "\u9fff" or ch.isalnum() or ch in "._:/#-+%()[]{}<>*\"'，。：；、（）【】":
            normal += 1
    return (normal / max(1, len(visible))) < 0.55


def clean_from_structured(structured: str) -> str:
    lines = structured.splitlines()
    out: list[str] = []

    for raw in lines:
        s = raw.strip()
        if not s:
            if out and out[-1] != "":
                out.append("")
            continue
        if _is_image_placeholder(s) or _is_comment_noise(s):
            continue
        if s.startswith("- source_pdf:"):
            continue
        if re.match(r"^## 第\d+页\s*$", s):
            continue
        if _table_sep_line(s):
            continue
        if re.match(r"^###\s+[\u4e00-\u9fffA-Za-z0-9]$", s):
            # broken one-char heading
            continue

        s = normalize_symbol_noise(s)

        if s.startswith("|"):
            # Keep row semantics, not visual table.
            s = re.sub(r"^\|\s*", "", s)
            s = re.sub(r"\s*\|\s*$", "", s)
            s = re.sub(r"\s*\|\s*", " | ", s)
        s = s.replace("<br/>", "；")
        s = re.sub(r"\s{2,}", " ", s).strip()
        if s:
            out.append(s)

    text = "\n".join(out)
    text = collapse_blank_lines(text)
    return text.strip() + "\n"


def clean_from_draft(draft_raw: str) -> str:
    body = extract_draft_content(draft_raw)
    body = strip_known_draft_noise(body)

    lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
    kept: list[str] = []
    prev_kind = "blank"
    suspicious_script = re.compile(r"[\u0600-\u06FF\u0750-\u077F\u0780-\u07BF\u08A0-\u08FF\u0590-\u05FF]")

    for ln in lines:
        if is_garbled_line(ln):
            continue
        if suspicious_script.search(ln):
            continue
        if re.search(r"(?i)\b(table grid|normal table|default paragraph font|heading \d)\*?$", ln):
            continue
        if re.match(r"(?i)^melo-[a-z0-9._-]+\*?$", ln):
            continue
        if re.match(r"(?i)^[a-z0-9]{5,}\*\d*$", ln):
            continue
        if re.match(r"(?i)^[a-z0-9]{5,}@$", ln):
            continue
        if re.match(r"^\d+\*$", ln):
            continue
        if re.match(r"^[*#:@\-\._]+$", ln):
            continue
        if re.match(r"^[A-Za-z]@[:A-Za-z0-9]{1,4}$", ln):
            continue
        if re.match(r"^\*?[A-Z]\*?$", ln):
            continue
        if re.match(r'^[\'"`][A-Za-z]$', ln):
            continue
        if re.search(r"wdcdn\.qpic\.cn|https?://", ln):
            continue
        if re.match(r"^@[A-Za-z0-9]{2,6}$", ln):
            continue
        if re.match(r"^[a-z0-9]{5,}\*$", ln.lower()):
            continue
        if re.search(r"wingdings", ln, flags=re.I):
            continue
        if re.search(r"\b177\d{8,}\b", ln):
            continue
        if re.search(r"@fJ|@eJ|c_[a-z0-9]{5,}", ln):
            continue
        if _is_image_placeholder(ln):
            continue

        ln = normalize_symbol_noise(ln)
        ln = re.sub(r"\s{2,}", " ", ln).strip()
        if ln:
            cur_kind = classify_line_kind(ln)
            if kept and kept[-1] != "" and should_insert_group_break(prev_kind, cur_kind):
                kept.append("")
            kept.append(ln)
            prev_kind = cur_kind

    text = "\n".join(kept)
    text = collapse_blank_lines(text)
    return text.strip() + "\n"


def build_accuracy_doc(content: str, source_primary: Path, source_raw: Path) -> str:
    header = [
        "# PRD - 市集购买链路优化（AI准确版）",
        "",
        "- strategy: accuracy-first",
        f"- source_primary: {source_primary}",
        f"- source_raw_backup: {source_raw}",
        "- note: 保留事实文本，移除图片占位与视觉噪声",
        "",
    ]
    text = "\n".join(header) + content
    text = collapse_blank_lines(text)
    return text.strip() + "\n"


def anchor_report(text: str, anchors: Iterable[str]) -> str:
    lines = ["# Anchor Check", "", "| Anchor | Present |", "| --- | --- |"]
    lowered = text
    for a in anchors:
        lines.append(f"| {a} | {'yes' if a in lowered else 'no'} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Archive WeCom doc into RAW + AI accuracy outputs.")
    parser.add_argument("--draft", help="Path to decoded draft markdown.")
    parser.add_argument("--url", help="WeCom doc URL. If provided, script fetches HTML and builds a draft snapshot.")
    parser.add_argument(
        "--structured",
        help="Optional path to structured markdown. If provided, AI output is based on this file.",
    )
    parser.add_argument("--out-dir", default="/tmp", help="Output directory.")
    parser.add_argument("--prefix", default="wecom_doc", help="Output filename prefix.")
    args = parser.parse_args()

    if not args.draft and not args.url:
        raise SystemExit("Either --draft or --url is required.")

    draft_path = Path(args.draft).expanduser().resolve() if args.draft else None
    structured_path = Path(args.structured).expanduser().resolve() if args.structured else None
    out_dir = Path(args.out_dir).expanduser().resolve()

    if draft_path and not draft_path.exists():
        raise SystemExit(f"draft not found: {draft_path}")
    if structured_path and not structured_path.exists():
        raise SystemExit(f"structured not found: {structured_path}")

    raw_out = out_dir / f"{args.prefix}_raw_snapshot.md"
    std_out = out_dir / "wecom_archive_standard.md"
    ai_out = out_dir / f"{args.prefix}_ai_accuracy.md"
    check_out = out_dir / f"{args.prefix}_anchor_check.md"

    if args.url:
        html_content = fetch_url_html(args.url)
        text_content = html_to_text(html_content)
        if seems_shell_page(text_content):
            raise SystemExit(
                "URL mode fetched only shell page (no readable正文). "
                "Use --draft from logged-in capture/export, or pass --structured."
            )
        raw_text = (
            "# WeCom Doc Raw Snapshot (URL)\n\n"
            f"- source_url: {args.url}\n\n"
            "## Content (raw html text)\n\n"
            f"{text_content}\n"
        )
    else:
        assert draft_path is not None
        raw_text = read_text(draft_path)

    write_text(raw_out, raw_text)
    write_text(std_out, STANDARD_TEXT)

    if structured_path:
        base_text = clean_from_structured(read_text(structured_path))
        source_primary = structured_path
    else:
        base_text = clean_from_draft(raw_text)
        source_primary = draft_path if draft_path else raw_out

    ai_text = build_accuracy_doc(base_text, source_primary=source_primary, source_raw=raw_out)
    write_text(ai_out, ai_text)
    write_text(check_out, anchor_report(ai_text, ANCHORS))

    print(f"WROTE {raw_out}")
    print(f"WROTE {ai_out}")
    print(f"WROTE {std_out}")
    print(f"WROTE {check_out}")


if __name__ == "__main__":
    main()
