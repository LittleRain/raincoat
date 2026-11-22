#!/usr/bin/env python3
"""首次使用的引导：检查环境 → 选平台 → 挑类目 → 生成配置。

所有产物都写到包外的工作目录（默认 ``~/.config/raincoat/mj-products``），
Skill 目录里不会留下任何账号、类目选择或抓取数据。

    python scripts/onboard.py            # 交互式
    python scripts/onboard.py --yes      # 用示例配置直接生成，适合脚本/CI
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from categories import Resolver, tree_for_plat  # noqa: E402
from mmiapi import (  # noqa: E402
    DEFAULT_STATE,
    resolve_path,
    run_cli,
    setup_stdio,
    workspace_dir,
)
from platforms import PLATFORMS, probe  # noqa: E402

TEMPLATE = {
    "auth_state": DEFAULT_STATE,
    "platforms": [],
    "categories": [],
    "window": {"days": 7, "cadence": "daily"},
    "new_product": {"baseline_months": 3, "min_sold": 1},
    "fetch": {
        "max_items_per_category": 100,
        "page_size": 100,
        "min_interval_ms": 4000,
        "max_retries": 3,
        "per_request_ms": 4000,
        "order_by_slices": ["sale", "sold"],
        "max_categories": 50,
    },
    "budget": {"max_requests": 3000, "max_categories": 300},
}


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"{prompt}{suffix}: ").strip()
    except EOFError:
        answer = ""
    return answer or default


def pick_platforms(available: dict, interactive: bool) -> list[dict]:
    usable = [
        (plat, info)
        for plat, info in available.items()
        if info.get("ok") and info.get("end")
    ]
    if not usable:
        print("没有可用平台，检查网络后重跑", file=sys.stderr)
        return []

    print("\n可用平台（数据截止）：")
    for index, (plat, info) in enumerate(usable, 1):
        print(f"  {index}. {plat:<14}{info.get('label', ''):<12}{info.get('start')} ~ {info.get('end')}")

    if not interactive:
        chosen = [p for p in ("all", "tmall") if p in dict(usable)]
        chosen = chosen or [usable[0][0]]
    else:
        print("\n建议淘系选 all + tmall（两套不同的前 100，合起来覆盖几乎翻倍）。")
        raw = ask("输入编号或平台 id，逗号分隔", "1")
        chosen = []
        for token in raw.replace("，", ",").split(","):
            token = token.strip()
            if not token:
                continue
            if token.isdigit() and 1 <= int(token) <= len(usable):
                chosen.append(usable[int(token) - 1][0])
            elif token in available:
                chosen.append(token)
            else:
                print(f"  跳过未知平台：{token}")

    result = []
    for plat in dict.fromkeys(chosen):
        group = "taobao" if PLATFORMS.get(plat, {}).get("tree") == "taobao" else plat
        result.append({"plat": plat, "label": PLATFORMS.get(plat, {}).get("label", plat),
                       "group": group})
    return result


def pick_categories(platforms: list[dict], data_dir: Path, interactive: bool) -> list[dict]:
    if not interactive:
        return [
            {"path": "面部清洁/护理/面膜", "alias": "面膜"},
            {"cid": "202044801", "alias": "纸尿裤"},
        ]
    for plat in platforms:
        try:
            tree_for_plat(plat["plat"])
        except Exception:
            continue  # 该平台没有公开类目树，换下一个有树的平台选
        picked = _interactive_categories(plat, data_dir)
        if picked:
            return picked
    return []


def _interactive_categories(plat: dict, data_dir: Path) -> list[dict]:
    try:
        resolver = Resolver(tree_for_plat(plat["plat"]), data_dir)
    except Exception as exc:
        print(f"  类目树不可用（{exc}），跳过", file=sys.stderr)
        return []

    picked: list[dict] = []
    print(f"\n为 {plat['plat']} 选类目（直接回车结束）：")
    while True:
        keyword = ask("  类目关键字（如 面膜 / 猫粮）")
        if not keyword:
            break
        if keyword.isdigit() and keyword in resolver.nodes:
            hit = resolver.describe(keyword)
            alias = ask("  给它一个短名（用于报告）", hit["name"])
            picked.append({"cid": hit["cid"], "alias": alias})
            continue

        hits = resolver.search(keyword, limit=12)
        if not hits:
            print("  没找到：换个更具体的词，或直接输入数字 cid（如 50452018）")
            continue
        print("  提示：结果按「名称精确度 → 层级」排，不理想就直接输 cid")
        for index, hit in enumerate(hits, 1):
            print(f"    {index}. {hit['path']}  (cid={hit['cid']})")
        choice = ask("  选第几个（回车跳过）", "1")
        if not choice.isdigit() or not (1 <= int(choice) <= len(hits)):
            continue
        hit = hits[int(choice) - 1]
        alias = ask("  给它一个短名（用于报告）", hit["name"])
        picked.append({"path": hit["path"], "alias": alias, "paths": {plat["plat"]: hit["path"]}})
        print(f"  已加入：{alias}  ({hit['cid']})")
    return picked


def main() -> int:
    parser = argparse.ArgumentParser(description="首次使用引导，生成工作目录与配置")
    parser.add_argument("--yes", action="store_true", help="不交互，用示例值")
    parser.add_argument("--workspace", help="工作目录，默认 ~/.config/raincoat/mj-products")
    parser.add_argument("--force", action="store_true", help="覆盖已有配置")
    args = parser.parse_args()

    setup_stdio()
    workspace = resolve_path(args.workspace, str(workspace_dir()))
    config_path = workspace / "config.json"
    data_dir = workspace / "data"

    if config_path.is_file() and not args.force:
        print(f"配置已存在：{config_path}\n要重建请加 --force", file=sys.stderr)
        return 0

    print(f"工作目录：{workspace}")
    print("（配置、登录态、抓取数据都放在包外，Skill 目录保持干净）")

    available = probe(data_dir)
    platforms = pick_platforms(available, interactive=not args.yes)
    if not platforms:
        return 2

    categories = pick_categories(platforms, data_dir, interactive=not args.yes)
    if not categories:
        print("没有选任何类目，已退出（配置未写入）", file=sys.stderr)
        return 2

    window = 7
    if not args.yes:
        window = int(ask("新品窗口天数", "7") or 7)

    config = dict(TEMPLATE)
    config["platforms"] = platforms
    config["categories"] = categories
    config["window"] = {"days": window, "cadence": "daily"}

    workspace.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n配置已写入：{config_path}")
    print(f"类目：{', '.join(c.get('alias') or c.get('cid', '') for c in categories)}")

    state = resolve_path(config.get("auth_state"), DEFAULT_STATE)
    if state.is_file():
        print(f"登录态：{state}")
    else:
        print("\n还没有登录态，二选一：")
        print("  a) python scripts/login.py                     # 弹出浏览器登录")
        print("  b) python scripts/import_state.py --in x.json  # 导入已有浏览器 Cookie")

    print("\n下一步：")
    print(f"  python scripts/doctor.py")
    print(f"  python scripts/run.py --config {config_path} --dry-run")
    print(f"  python scripts/run.py --config {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
