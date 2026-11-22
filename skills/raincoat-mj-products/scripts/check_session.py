#!/usr/bin/env python3
"""Verify the saved session actually works, then (optionally) touch one endpoint.

A stored storageState can look fine and still be expired. This checks /api/user
and, when given --plat/--cid, performs one real hot_items request so that an
expired or under-privileged account fails here instead of mid-run.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mmiapi import (  # noqa: E402
    AuthRequired,
    Forbidden,
    MmiError,
    Session,
    fetch_total,
    is_logged_in,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="校验魔镜登录态")
    parser.add_argument("--state", help="登录态路径")
    parser.add_argument("--plat", help="顺带探测该类目的接口权限")
    parser.add_argument("--cid", help="类目 id")
    parser.add_argument("--month", help="数据月份 YYYY-MM，默认当前月")
    parser.add_argument("--min-interval-ms", type=int, default=1200)
    args = parser.parse_args()

    try:
        with Session(args.state, min_interval_ms=args.min_interval_ms) as session:
            payload = session.get_json("/api/user")
            result = payload.get("result") or {}
            if not is_logged_in(result):
                raise AuthRequired(
                    "登录态是未登录状态（usertype=logged_out），Cookie 无效或已过期"
                )
            if isinstance(result, dict):
                keys = [k for k in ("username", "nick", "usertype", "deadline", "all_site")
                        if k in result]
                print("会话有效：" + ", ".join(f"{k}={result[k]}" for k in keys))
            else:
                print("会话有效。")

            if args.plat and args.cid:
                month = args.month or date.today().strftime("%Y-%m")
                total, got = fetch_total(session, plat=args.plat, cid=args.cid, month=month)
                print(
                    json.dumps(
                        {"plat": args.plat, "cid": args.cid, "month": month,
                         "total": total, "rows": got},
                        ensure_ascii=False,
                    )
                )
        return 0
    except AuthRequired as exc:
        print(f"需要登录：{exc}", file=sys.stderr)
        print("运行 `python scripts/login.py` 后重试。", file=sys.stderr)
        return 3
    except Forbidden as exc:
        print(f"套餐无权：{exc}", file=sys.stderr)
        return 4
    except MmiError as exc:
        print(f"校验失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
