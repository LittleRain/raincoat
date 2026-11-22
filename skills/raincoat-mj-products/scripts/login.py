#!/usr/bin/env python3
"""One-time interactive login, saved as a Playwright storageState file.

This is the only headed step in the skill: the human signs in, the script waits
for the session to become valid, then stores cookies for headless reuse. It never
sees or stores the password.
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mmiapi import BASE, DEFAULT_STATE, resolve_path  # noqa: E402

LOGIN_URL = f"{BASE}/dashboard"
PROBE = (
    "fetch('/api/user', {headers: {'X-Requested-With': 'XMLHttpRequest'}, "
    "credentials: 'include'}).then(r => r.json()).then(j => "
    "({status: j.status, code: j.error_code, user: (j.result && (j.result.email || "
    "j.result.name || j.result.username)) || null}))"
)


def save_state(context, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    context.storage_state(path=str(path))
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def wait_for_login(page, timeout: int, interval: float = 2.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            info = page.evaluate(PROBE)
        except Exception:  # page navigating or dialog open
            info = {}
        if (isinstance(info, dict) and info.get("status") == "ok"
                and str(info.get("usertype") or "").lower() != "logged_out"
                and info.get("user")):
            user = info.get("user")
            print(f"\n登录成功{f'（{user}）' if user else ''}")
            return True
        time.sleep(interval)
    return False


def main() -> int:
    parser = argparse.ArgumentParser(description="登录魔镜并保存登录态")
    parser.add_argument("--state", default=DEFAULT_STATE, help="登录态保存路径")
    parser.add_argument("--cdp", help="连接已开调试端口的 Chrome，如 http://localhost:9222")
    parser.add_argument("--timeout", type=int, default=300, help="等待登录的秒数")
    args, extra = parser.parse_known_args()
    if extra:
        print(
            "忽略无法识别的参数：" + " ".join(extra) +
            "\n（常见原因：把行尾的 # 注释一起粘贴进来了）",
            file=sys.stderr,
        )

    state = resolve_path(args.state)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("需要 Playwright：pip install playwright && playwright install chromium", file=sys.stderr)
        return 2

    with sync_playwright() as pw:
        try:
            return _run(pw, args, state)
        except Exception as exc:  # missing browser / cdp refused
            message = str(exc)
            print(f"启动浏览器失败：{message}", file=sys.stderr)
            if "Executable doesn't exist" in message or "playwright install" in message:
                print("先执行：playwright install chromium", file=sys.stderr)
            elif args.cdp:
                print(f"确认 Chrome 已用 --remote-debugging-port 启动：{args.cdp}", file=sys.stderr)
            return 2


def _run(pw, args, state) -> int:
    if args.cdp:
        browser = pw.chromium.connect_over_cdp(args.cdp)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()
        if "mktindex.com" not in page.url:
            page.goto(LOGIN_URL)
        print(f"已连接 {args.cdp}，请在该浏览器的窗口里完成登录…")
    else:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(locale="zh-CN")
        page = context.new_page()
        page.goto(LOGIN_URL)
        print("已打开魔镜登录页，请在窗口里完成登录（含短信验证）。")
        print("登录成功后会自动保存，无需回到这里操作。")

    try:
        ok = wait_for_login(page, args.timeout)
        if not ok:
            print("等待登录超时，未保存登录态。", file=sys.stderr)
            return 1
        save_state(context, state)
        print(f"登录态已保存：{state}")
        return 0
    finally:
        try:
            if not args.cdp:
                browser.close()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
