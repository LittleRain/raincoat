#!/usr/bin/env python3
"""Preflight: tell the user exactly what is missing before a run fails mid-way.

Checks interpreter, dependencies, Playwright browser, network, login state and
local caches. Every failure prints the one command that fixes it.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

OK = "✓"
BAD = "✗"
WARN = "!"


def check_python() -> tuple[bool, str]:
    version = sys.version_info
    text = f"Python {version.major}.{version.minor}.{version.micro}"
    if version < (3, 10):
        return False, f"{text}（需要 3.10+；装一个新版或改用 python3.10）"
    return True, text


def check_deps() -> tuple[bool, str]:
    missing = []
    for name, hint in (("requests", "pip install requests"),
                       ("playwright", "pip install playwright"),
                       ("openpyxl", "pip install openpyxl")):
        try:
            __import__(name)
        except ImportError:
            missing.append(f"{name}（{hint}）")
    if missing:
        return False, "缺少：" + "、".join(missing)
    return True, "requests / playwright / openpyxl 就绪"


def check_browser() -> tuple[bool, str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False, "playwright 未安装：pip install playwright"
    try:
        with sync_playwright() as pw:
            path = pw.chromium.executable_path
    except Exception as exc:  # missing browser or broken install
        return False, f"Playwright 启动失败：{exc}"
    if not Path(path).exists():
        return False, "Chromium 未下载：playwright install chromium"
    return True, "Chromium 已就绪"


def check_network(timeout: float = 15.0) -> tuple[bool, str]:
    try:
        import requests
    except ImportError:
        return False, "requests 未安装"
    from mmiapi import BASE, UA

    try:
        resp = requests.get(
            f"{BASE}/api/latesttime", headers={"User-Agent": UA}, timeout=timeout
        )
        payload = resp.json()
    except Exception as exc:
        return False, f"连不上 {BASE}：{exc}"
    if payload.get("status") != "ok":
        return False, f"接口返回异常：{payload}"
    result = payload.get("result") or {}
    return True, f"可达，数据区间 {result.get('start')} ~ {result.get('end')}"


def check_login(state: Path) -> tuple[bool, str]:
    from mmiapi import AuthRequired, Session, is_logged_in

    if not state.is_file():
        return False, f"没有登录态 {state}；跑 `python scripts/login.py`"
    try:
        with Session(state) as session:
            result = (session.get_json("/api/user") or {}).get("result") or {}
    except AuthRequired as exc:
        return False, f"{exc}；重跑 `python scripts/login.py`"
    except Exception as exc:
        return False, f"校验失败：{exc}"
    if not is_logged_in(result):
        return False, "登录态无效（usertype=logged_out）；重跑 `python scripts/login.py`"
    name = result.get("username") or result.get("nick") or "已登录"
    plan = result.get("usertype") or "?"
    return True, f"{name}（{plan}）"


def check_cache(data_dir: Path) -> tuple[bool, str]:
    trees = sorted((data_dir / "categories").glob("*.json")) if data_dir.is_dir() else []
    if not trees:
        return True, "类目树未同步（首次运行会自动下载，淘宝约 14MB）"
    return True, "已同步：" + "、".join(f"{p.stem}({p.stat().st_size // 1024 // 1024}MB)" for p in trees)


def check_writable(data_dir: Path) -> tuple[bool, str]:
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        probe = data_dir / ".write_test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        return False, f"{data_dir} 不可写：{exc}"
    return True, str(data_dir)


def main() -> int:
    parser = argparse.ArgumentParser(description="运行环境自检")
    parser.add_argument("--state", help="登录态路径")
    parser.add_argument("--data-dir", help="默认是 skill 目录下的 data/，与 cwd 无关")
    parser.add_argument("--skip-login", action="store_true", help="不检查登录态")
    args = parser.parse_args()

    from mmiapi import DEFAULT_STATE, default_data_dir, resolve_path, setup_stdio

    setup_stdio()

    state = resolve_path(args.state, DEFAULT_STATE)
    data_dir = resolve_path(args.data_dir, str(default_data_dir()))

    checks = [
        ("解释器", check_python, False),
        ("依赖", check_deps, False),
        ("Playwright 浏览器", check_browser, False),
        ("网络", check_network, False),
        ("登录态", lambda: check_login(state), True),
        ("数据目录", lambda: check_writable(data_dir), False),
        ("类目树缓存", lambda: check_cache(data_dir), True),
    ]

    def pad(text: str, width: int = 20) -> str:
        shown = sum(2 if ord(ch) > 127 else 1 for ch in text)
        return text + " " * max(0, width - shown)

    blocking = 0
    for label, fn, soft in checks:
        if label == "登录态" and args.skip_login:
            print(f"{WARN} {pad(label)}已跳过")
            continue
        try:
            ok, detail = fn()
        except Exception as exc:  # never let the doctor itself explode
            ok, detail = False, f"检查本身出错：{type(exc).__name__}: {exc}"
        mark = OK if ok else (WARN if soft else BAD)
        if not ok and not soft:
            blocking += 1
        print(f"{mark} {pad(label)}{detail}")

    if blocking:
        print(f"\n{blocking} 项阻塞检查未通过，按上面的提示修完再跑。", file=sys.stderr)
        return 1
    print("\n环境可用。登录态无效只影响抓取，不影响 dry-run。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
