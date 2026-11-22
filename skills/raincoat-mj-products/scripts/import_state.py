#!/usr/bin/env python3
"""Turn a CDP cookie dump into a Playwright ``storageState`` file.

Use when the browser login lives somewhere the skill cannot drive headlessly
(e.g. ego lite with an SMS-verified session). Export cookies once, convert, and
pass the result as ``--state``.

    python scripts/import_state.py --in cookies.json
    python scripts/import_state.py --in - < cookies.json    # stdin
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mmiapi import DEFAULT_STATE, resolve_path  # noqa: E402

KEEP_SUFFIX = "mktindex.com"


def to_state(payload, domain: str = KEEP_SUFFIX) -> dict:
    """Accept {cookies:[...]} (CDP Network.getAllCookies) or a bare list."""
    if isinstance(payload, dict):
        cookies = payload.get("cookies") or payload.get("data") or []
    elif isinstance(payload, list):
        cookies = payload
    else:
        raise ValueError("输入必须是 CDP 的 {cookies:[...]} 或 Cookie 数组")

    kept = []
    for cookie in cookies:
        if not isinstance(cookie, dict):
            continue
        name = cookie.get("name")
        value = cookie.get("value")
        host = cookie.get("domain") or ""
        if not name or value is None or domain not in host:
            continue
        same_site = cookie.get("sameSite")
        kept.append(
            {
                "name": name,
                "value": value,
                "domain": host,
                "path": cookie.get("path") or "/",
                "expires": cookie.get("expires") if isinstance(cookie.get("expires"), (int, float))
                and cookie.get("expires", 0) > 0 else -1,
                "httpOnly": bool(cookie.get("httpOnly")),
                "secure": bool(cookie.get("secure")),
                "sameSite": same_site if same_site in {"Strict", "Lax", "None"} else "Lax",
            }
        )
    if not kept:
        raise ValueError(f"没有匹配 *{domain} 的 Cookie")
    return {"cookies": kept, "origins": []}


def main() -> int:
    parser = argparse.ArgumentParser(description="把 CDP 导出的 Cookie 转成登录态文件")
    parser.add_argument("--in", dest="source", required=True, help="输入 JSON 路径，- 表示 stdin")
    parser.add_argument("--out", help="输出路径，默认 ~/.config/raincoat/mktindex/auth.json")
    parser.add_argument("--domain", default=KEEP_SUFFIX, help="只保留该域名下的 Cookie")
    parser.add_argument("--json", action="store_true", help="只打印统计，不写文件")
    args = parser.parse_args()

    raw = sys.stdin.read() if args.source == "-" else Path(args.source).expanduser().read_text("utf-8")
    try:
        state = to_state(json.loads(raw), args.domain)
    except ValueError as exc:
        print(f"转换失败：{exc}", file=sys.stderr)
        return 2

    summary = {
        "cookies": len(state["cookies"]),
        "domains": sorted({c["domain"] for c in state["cookies"]}),
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
        return 0

    target = resolve_path(args.out, DEFAULT_STATE)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass
    summary["out"] = str(target)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("用它验证：python scripts/check_session.py", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
