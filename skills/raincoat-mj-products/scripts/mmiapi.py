#!/usr/bin/env python3
"""Shared 魔镜 (mktindex) API helpers: cookie auth, typed errors, tolerant parsing.

The dashboard is an AngularJS shell; every table is served by same-origin
``/api/...`` endpoints authenticated with session cookies. Failures come back as
HTTP 200 with ``{"status": "error", "error_code": ...}``, so callers must never
look at the HTTP status alone.
"""
from __future__ import annotations

import json
import os
import random
import sys
import threading
import time
from pathlib import Path
from typing import Any

import requests

BASE = "https://market1.mktindex.com"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
DEFAULT_STATE = "~/.config/raincoat/mktindex/auth.json"

# 用户态一律放在包外：配置、数据、报告都不进 Skill 目录，导出包因此永远干净。
WORKSPACE_ENV = "RAINCOAT_MJ_HOME"

# error_code -> meaning. Anything not listed is reported verbatim.
ERRORS = {
    -400: "参数错误",
    -401: "未登录或登录态已失效",
    -403: "当前套餐无权查看该类目",
    -404: "该类目/商品尚未收录",
    -499: "账号需要短信验证",
    -429: "访问频率过快",
    -500: "平台服务端错误",
}


class MmiError(RuntimeError):
    """Base error for this skill."""


class AuthRequired(MmiError):
    """Session cookie missing or expired (error_code -401)."""


class Forbidden(MmiError):
    """Account plan has no access to this category (error_code -403)."""


class NotFound(MmiError):
    """Category or item not collected by the platform (error_code -404)."""


class PlatformUnsupported(MmiError):
    """Unknown platform id (error_code 3)."""


class RateLimited(MmiError):
    """Platform throttled us (error_code -429); back off, do not hammer."""


class SchemaChanged(MmiError):
    """Response shape or field names changed; refuse to emit empty results."""


def workspace_dir() -> Path:
    """Where this user's config/data/reports live; never inside the skill folder.

    Override with ``RAINCOAT_MJ_HOME`` (tests and CI use it).
    """
    override = os.environ.get(WORKSPACE_ENV)
    base = Path(os.path.expanduser(override)) if override else Path(
        os.path.expanduser("~/.config/raincoat/mj-products")
    )
    return base.resolve()


def default_config_path() -> Path:
    return workspace_dir() / "config.json"


def default_data_dir() -> Path:
    return workspace_dir() / "data"


def default_output_dir() -> Path:
    return workspace_dir() / "output"


def resolve_path(value: str | os.PathLike[str] | None, default: str | None = None) -> Path:
    """Expand ``~`` and relative paths from the current working directory."""
    raw = value if value not in (None, "") else default
    if raw is None:
        raise ValueError("path is required")
    return Path(os.path.expanduser(str(raw))).resolve()


def load_state(path: Path) -> dict:
    if not path.is_file():
        raise AuthRequired(
            f"未找到登录态 {path}；先运行 `python scripts/login.py` 完成一次登录"
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise AuthRequired(f"登录态文件不是合法 JSON: {path}") from exc


def cookies_from_state(state: dict) -> requests.cookies.RequestsCookieJar:
    """Turn a Playwright storageState document into a requests cookie jar."""
    jar = requests.cookies.RequestsCookieJar()
    for cookie in state.get("cookies", []):
        name = cookie.get("name")
        value = cookie.get("value")
        if not name or value is None:
            continue
        domain = cookie.get("domain") or "market1.mktindex.com"
        jar.set(
            name,
            value,
            domain=domain,
            path=cookie.get("path") or "/",
            secure=bool(cookie.get("secure")),
        )
    if not len(jar):
        raise AuthRequired("登录态里没有 Cookie；重新运行 `python scripts/login.py`")
    return jar


def _error_message(payload: dict) -> str:
    raw = payload.get("error_msg")
    if isinstance(raw, dict):
        raw = raw.get("msg") or raw.get("msg_en")
    return str(raw or payload.get("msg") or "未知错误")


def error_to_exception(payload: dict) -> MmiError:
    code = payload.get("error_code")
    message = _error_message(payload)
    try:
        code_int = int(code)
    except (TypeError, ValueError):
        code_int = None
    if code_int == -401:
        return AuthRequired(f"登录态失效：{message}")
    if code_int == -403:
        return Forbidden(f"无权查看：{message}")
    if code_int == -404:
        return NotFound(f"尚未收录：{message}")
    if code_int == 3:
        return PlatformUnsupported(f"平台 id 不被接受：{message}")
    if code_int == -429:
        return RateLimited(f"被限流：{message}")
    label = ERRORS.get(code_int, "平台返回错误")
    return MmiError(f"{label}（error_code={code}）：{message}")


LIST_KEYS = ("data", "items", "list", "rows", "aaData", "records", "result")
TOTAL_KEYS = ("total", "iTotalRecords", "count", "num", "totalCount", "total_count")


def _walk(node: Any, depth: int = 0):
    """Yield candidate list/dict nodes breadth-first, bounded depth."""
    if depth > 3:
        return
    yield node
    if isinstance(node, dict):
        for key in LIST_KEYS:
            if key in node and isinstance(node[key], (list, dict)):
                yield from _walk(node[key], depth + 1)
    elif isinstance(node, list):
        return


def extract_rows(payload: Any) -> tuple[list[dict], int | None]:
    """Find the row list and total count in a response of unknown exact shape."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)], None

    rows: list[dict] | None = None
    empty_list: list | None = None
    total: int | None = None
    for node in _walk(payload):
        if isinstance(node, list) and node and all(isinstance(r, dict) for r in node):
            rows = node
            break
        if isinstance(node, list) and not node:
            empty_list = node
        if isinstance(node, dict):
            if total is None:
                for key in TOTAL_KEYS:
                    value = node.get(key)
                    if isinstance(value, (int, float)) and not isinstance(value, bool):
                        total = int(value)
                        break
            for key in LIST_KEYS:
                value = node.get(key)
                if isinstance(value, list) and value and all(
                    isinstance(r, dict) for r in value
                ):
                    rows = value
                    break
        if rows is not None:
            break

    if rows is None and empty_list is not None:
        return [], total

    if rows is None:
        sample = sorted(payload.keys())[:12] if isinstance(payload, dict) else type(payload).__name__
        raise SchemaChanged(f"返回结构里找不到商品列表，实际顶层字段：{sample}")
    return rows, total


class RateLimiter:
    """Process-wide minimum interval between requests, safe across threads."""

    def __init__(self, min_interval_ms: int = 1200) -> None:
        self.min_interval = max(0.0, min_interval_ms / 1000.0)
        self._last_call = 0.0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        if not self.min_interval:
            return
        with self._lock:
            elapsed = time.monotonic() - self._last_call
            wait = self.min_interval - elapsed
            if wait > 0:
                time.sleep(wait + random.uniform(0, 0.25))
            self._last_call = time.monotonic()


class Session:
    """Throttled, retrying JSON client bound to one account's cookies."""

    def __init__(
        self,
        state: Path | str | None = None,
        *,
        min_interval_ms: int = 1200,
        timeout: float = 30.0,
        retries: int = 3,
        base: str = BASE,
        limiter: RateLimiter | None = None,
        cooldown_s: float = 60.0,
    ) -> None:
        self.base = base.rstrip("/")
        self.timeout = timeout
        self.retries = max(0, int(retries))
        self.cooldown = max(10.0, float(cooldown_s))
        self.limiter = limiter or RateLimiter(min_interval_ms)
        self.min_interval = self.limiter.min_interval
        self.requests_made = 0

        path = resolve_path(state, DEFAULT_STATE)
        self.state_file = path
        jar = cookies_from_state(load_state(path))

        http = requests.Session()
        http.cookies = jar
        http.headers.update(
            {
                "User-Agent": UA,
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "Referer": f"{self.base}/dashboard",
                "X-Requested-With": "XMLHttpRequest",
            }
        )
        self.http = http

    # -- throttling -----------------------------------------------------
    def _throttle(self) -> None:
        self.limiter.acquire()

    def _backoff(self, attempt: int) -> None:
        time.sleep(min(2 ** attempt, 8) + random.uniform(0, 0.5))

    # -- requests -------------------------------------------------------
    def get_json(self, path: str, params: dict | None = None) -> Any:
        url = self.base + (path if path.startswith("/") else "/" + path)
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            self._throttle()
            try:
                response = self.http.get(url, params=params, timeout=self.timeout)
                self.requests_made += 1
            except requests.RequestException as exc:
                last_error = exc
                if attempt >= self.retries:
                    raise MmiError(f"网络请求失败（{url}）：{exc}") from exc
                self._backoff(attempt)
                continue

            if response.status_code in (401, 403):
                raise AuthRequired(
                    f"HTTP {response.status_code}，登录态被拒绝；重新运行 `python scripts/login.py`"
                )
            if response.status_code == 429 or response.status_code >= 500:
                last_error = MmiError(f"HTTP {response.status_code}")
                if attempt >= self.retries:
                    raise MmiError(f"平台持续返回 HTTP {response.status_code}（{url}）")
                retry_after = response.headers.get("Retry-After")
                if retry_after and retry_after.isdigit():
                    time.sleep(min(int(retry_after), 30))
                else:
                    self._backoff(attempt)
                continue
            if response.status_code != 200:
                raise MmiError(f"HTTP {response.status_code}（{url}）")

            try:
                payload = response.json()
            except ValueError as exc:
                head = response.text[:120].replace("\n", " ")
                raise SchemaChanged(
                    f"返回不是 JSON，可能被登录页或风控拦截：{head!r}"
                ) from exc

            if isinstance(payload, dict) and str(payload.get("status")) == "error":
                exc = error_to_exception(payload)
                code = payload.get("error_code")
                if isinstance(exc, RateLimited) and attempt < self.retries:
                    wait = self.cooldown * (attempt + 1)
                    print(
                        f"[限流] 平台返回 -429，等待 {wait:.0f}s 后重试（{attempt + 1}/{self.retries}）",
                        file=sys.stderr,
                    )
                    time.sleep(wait)
                    continue
                retryable = code in (-500, " -500") or str(code) == "-500"
                if retryable and attempt < self.retries:
                    last_error = exc
                    self._backoff(attempt)
                    continue
                raise exc

            return payload

        raise MmiError(f"请求失败：{last_error}")

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "Session":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()


def latest_month(session: "Session", plat: str) -> tuple[str | None, str | None]:
    """(start, end) of the data window for a platform; public endpoint."""
    payload = session.get_json("/api/latesttime", {"plat": plat})
    result = payload.get("result") or {}
    return result.get("start"), result.get("end")


def is_logged_in(result: dict | None) -> bool:
    """``/api/user`` answers 200 + status ok for guests too; usertype is the tell."""
    if not isinstance(result, dict):
        return False
    if str(result.get("usertype") or "").strip().lower() in {"logged_out", "loggedout", "guest"}:
        return False
    return bool(result.get("username") or result.get("nick") or result.get("email"))


def fetch_total(
    session: Session,
    *,
    plat: str,
    cid: str,
    month: str,
    page_size: int = 10,
) -> tuple[int | None, int]:
    """One cheap request: the row count the server reports for the month.

    page_size=1 is rejected with HTTP 400, so the probe uses 10.
    """
    params = {
        "start": month,
        "end": month,
        "page": 1,
        "page_size": page_size,
        "order_by": "sale",
        "desc": "true",
        "lang": "zh",
    }
    payload = session.get_json(f"/api/platform/{plat}/cats/{cid}/brands/all/hot_items", params)
    rows, total = extract_rows(payload)
    return total, len(rows)


def setup_stdio() -> None:
    """Force UTF-8 output.

    Windows consoles/pipes default to cp936, where characters like ✓ raise
    UnicodeEncodeError and kill an otherwise fine run.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass


def run_cli(main) -> int:
    """Run a script's main() and turn typed errors into one-line messages.

    Keeps every entry point readable on a fresh machine: no stack trace for the
    two things that actually happen there (no login state, no network).
    """
    setup_stdio()
    try:
        return main()
    except AuthRequired as exc:
        print(f"需要登录：{exc}", file=sys.stderr)
        print("先运行 `python scripts/login.py`，或用 import_state.py 导入已有登录态。",
              file=sys.stderr)
        return 3
    except PlatformUnsupported as exc:
        print(f"平台不支持：{exc}", file=sys.stderr)
        return 4
    except Forbidden as exc:
        print(f"套餐无权：{exc}", file=sys.stderr)
        return 4
    except NotFound as exc:
        print(f"未收录：{exc}", file=sys.stderr)
        return 4
    except SchemaChanged as exc:
        print(f"返回结构变化：{exc}", file=sys.stderr)
        return 5
    except MmiError as exc:
        print(f"失败：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return 130
