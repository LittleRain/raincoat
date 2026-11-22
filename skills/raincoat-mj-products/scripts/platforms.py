#!/usr/bin/env python3
"""Platform availability probe for market1.mktindex.com.

The dashboard accepts 20 ``plat`` ids, but each one has a different data window
and only some have a downloadable category tree. Running this before a fetch is
what stops the skill from producing "new products" out of 2020 Pinduoduo data.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mmiapi import BASE, UA, MmiError, resolve_path, run_cli  # noqa: E402

# plat id -> (中文名, 类目树来源 key)。顺序即报告里的默认顺序。
PLATFORMS: dict[str, dict[str, str]] = {
    "all": {"label": "淘宝+天猫", "tree": "taobao"},
    "cshop": {"label": "淘宝", "tree": "taobao"},
    "tmall": {"label": "天猫", "tree": "taobao"},
    "chaoshi": {"label": "天猫超市", "tree": "taobao"},
    "nochaoshi": {"label": "天猫非天猫超市", "tree": "taobao"},
    "tmqjd": {"label": "天猫旗舰店", "tree": "taobao"},
    "tmzyzmd": {"label": "天猫专营专卖店", "tree": "taobao"},
    "tmallhk": {"label": "天猫国际", "tree": "taobao"},
    "notmallhk": {"label": "天猫非天猫国际", "tree": "taobao"},
    "jd": {"label": "京东", "tree": "jd"},
    "jd_only_self": {"label": "京东自营", "tree": "jd"},
    "jd_exclude_self": {"label": "京东非自营", "tree": "jd"},
    "jd_hk": {"label": "京东全球购", "tree": "jd"},
    "sn": {"label": "苏宁", "tree": "sn"},
    "gome": {"label": "国美", "tree": "gome"},
    "wykl": {"label": "网易考拉", "tree": "wykl"},
    "pdd": {"label": "拼多多", "tree": ""},
    "jm": {"label": "聚美", "tree": ""},
    "dd": {"label": "当当", "tree": ""},
    "amazon": {"label": "亚马逊中国", "tree": ""},
    "global": {"label": "全球购", "tree": ""},
}

TREE_SOURCES = {
    "taobao": "https://staticjs.mktindex.com/prod/bigcats_taobao.js",
    "jd": "https://chance.mktindex.com/static/chance/json/bigcats_jd.js",
    "sn": "https://chance.mktindex.com/static/chance/json/bigcats_sn.js",
    "gome": "https://chance.mktindex.com/static/chance/json/bigcats_gome.js",
    "wykl": "https://chance.mktindex.com/static/chance/json/bigcats_wykl.js",
}

CACHE_TTL_HOURS = 24


def cache_file(data_dir: Path) -> Path:
    return data_dir / "cache" / "platforms.json"


def _probe_one(plat: str, timeout: float = 20.0) -> dict:
    url = f"{BASE}/api/latesttime"
    try:
        resp = requests.get(
            url, params={"plat": plat}, headers={"User-Agent": UA}, timeout=timeout
        )
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        return {"plat": plat, "ok": False, "error": f"请求失败：{exc}"}

    if payload.get("status") != "ok":
        return {
            "plat": plat,
            "ok": False,
            "error": str(payload.get("error_msg") or payload.get("error_code")),
        }
    result = payload.get("result") or {}
    return {"plat": plat, "ok": True, "start": result.get("start"), "end": result.get("end")}


def probe(data_dir: Path, *, refresh: bool = False, plats: list[str] | None = None) -> dict:
    """Return {plat: {label, ok, start, end, tree, stale}} with a 1-day cache."""
    path = cache_file(data_dir)
    cached: dict = {}
    if path.is_file() and not refresh:
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            cached = {}
        fetched = cached.get("fetched_at", "")
        try:
            age = datetime.now() - datetime.fromisoformat(fetched)
            if age.total_seconds() > CACHE_TTL_HOURS * 3600:
                cached = {}
        except ValueError:
            cached = {}

    wanted = plats or list(PLATFORMS)
    unknown = [p for p in wanted if p not in PLATFORMS]
    if unknown:
        raise MmiError(
            f"未知平台 id：{', '.join(unknown)}；可用：{', '.join(PLATFORMS)}"
        )

    results: dict[str, dict] = dict(cached.get("plats", {}))
    for plat in wanted:
        if plat in results and results[plat].get("ok"):
            continue
        entry = _probe_one(plat)
        entry["label"] = PLATFORMS[plat]["label"]
        entry["tree"] = PLATFORMS[plat]["tree"]
        results[plat] = entry

    payload = {
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "plats": {p: results[p] for p in PLATFORMS if p in results},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload["plats"]


def usable_since(entry: dict, month: str, *, min_months: int = 1) -> tuple[bool, str]:
    """Whether the platform has data reaching ``month`` (YYYY-MM)."""
    if not entry.get("ok"):
        return False, entry.get("error") or "平台不可用"
    end = entry.get("end") or ""
    start = entry.get("start") or ""
    if not end or end < month:
        return False, f"数据只到 {end or '未知'}，晚于它的月份抓不到"
    if start and month < start:
        return False, f"数据从 {start} 开始"
    if month == end:
        return True, ""
    # end 之后 tolerates one month of lag already handled above; extra guard for
    # platforms that stopped years ago (pdd ends 2020-05).
    return True, ""


def main() -> int:
    parser = argparse.ArgumentParser(description="探测各平台的数据区间与类目树可用性")
    parser.add_argument("--data-dir", default="./data", help="缓存目录，默认 ./data")
    parser.add_argument("--plat", action="append", help="只探测指定平台，可重复")
    parser.add_argument("--refresh", action="store_true", help="忽略 24 小时缓存")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    data_dir = resolve_path(args.data_dir)
    plats = probe(data_dir, refresh=args.refresh, plats=args.plat)
    today = date.today().strftime("%Y-%m")

    if args.json:
        print(json.dumps(plats, ensure_ascii=False, indent=2))
        return 0

    print(f"{'plat':<16}{'名称':<16}{'数据区间':<22}{'类目树':<8}本月")
    for plat, entry in plats.items():
        if not entry.get("ok"):
            span = "不可用"
            flag = "✗"
        else:
            span = f"{entry.get('start')} ~ {entry.get('end')}"
            flag = "✓" if entry.get("end", "") >= today else "✗ 停更"
        tree = "有" if entry.get("tree") else "无"
        print(f"{plat:<16}{entry.get('label', ''):<16}{span:<22}{tree:<8}{flag}")
    print("\n注：拼多多(pdd) 数据止于 2020-05；抖音不在该产品的 platform id 里。")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
