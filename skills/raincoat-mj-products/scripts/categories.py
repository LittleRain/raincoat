#!/usr/bin/env python3
"""Category tree for market1: resolve a 类目路径 to a category id, per platform.

The platform ships its trees as static JS (``var cache_cat_taobao = {...}``).
Taobao/Tmall share one tree of ~58k nodes; JD has its own id space, so a path is
resolved per platform and never translated across platforms.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mmiapi import UA, MmiError, resolve_path, run_cli  # noqa: E402
from platforms import PLATFORMS, TREE_SOURCES  # noqa: E402


def tree_file(data_dir: Path, tree: str) -> Path:
    return data_dir / "categories" / f"{tree}.json"


def tree_for_plat(plat: str) -> str:
    if plat not in PLATFORMS:
        raise MmiError(f"未知平台 id：{plat}")
    tree = PLATFORMS[plat].get("tree") or ""
    if not tree:
        raise MmiError(f"平台 {plat} 没有公开类目树；请在配置里直接写 cid")
    return tree


def parse_tree(text: str) -> dict[str, dict]:
    """Parse ``var cache_cat_x = {...}`` into {cid: {name, parent, level}}."""
    start = text.find("{")
    if start < 0:
        raise MmiError("类目树文件里找不到 JSON 对象")
    try:
        payload, _ = json.JSONDecoder().raw_decode(text[start:])
    except ValueError as exc:
        raise MmiError(f"类目树解析失败：{exc}") from exc

    result = payload.get("result") or payload
    if isinstance(result, dict) and isinstance(result.get("childrenList"), dict):
        nodes = result["childrenList"]
    else:
        nodes = result
    if not isinstance(nodes, dict):
        raise MmiError("类目树结构变化：找不到 childrenList")

    cleaned: dict[str, dict] = {}
    for cid, node in nodes.items():
        if not isinstance(node, dict):
            continue
        cleaned[str(node.get("category_id") or cid)] = {
            # taobao uses "name", jd uses "category_name"
            "name": node.get("name") or node.get("category_name") or node.get("cat_name") or "",
            "parent": str(node.get("parent_id") or "") or None,
            "level": int(node.get("level") or 0),
            "children": [str(c) for c in (node.get("chd") or [])],
        }
    if not cleaned:
        raise MmiError("类目树为空，可能接口结构已变")
    return cleaned


def sync(tree: str, data_dir: Path, *, force: bool = False) -> dict:
    target = tree_file(data_dir, tree)
    if target.is_file() and not force:
        cached = json.loads(target.read_text(encoding="utf-8"))
        if cached.get("nodes"):
            return cached

    url = TREE_SOURCES.get(tree)
    if not url:
        raise MmiError(f"没有 {tree} 的类目树来源")
    try:
        resp = requests.get(url, headers={"User-Agent": UA}, timeout=180)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise MmiError(
            f"类目树下载失败（{url}）：{exc}；检查网络后重试，或直接用 --cid 跳过类目解析"
        ) from exc
    nodes = parse_tree(resp.text)
    payload = {"tree": tree, "source": url, "count": len(nodes), "nodes": nodes}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return payload


def load(tree: str, data_dir: Path, *, auto_sync: bool = True) -> dict:
    target = tree_file(data_dir, tree)
    if target.is_file():
        return json.loads(target.read_text(encoding="utf-8"))
    if not auto_sync:
        raise MmiError(f"类目树未同步：{target}")
    return sync(tree, data_dir)


def build_paths(nodes: dict[str, dict]) -> dict[str, str]:
    """cid -> "一级/二级/三级" full path."""
    paths: dict[str, str] = {}

    def walk(cid: str, seen: set[str]) -> str:
        if cid in paths:
            return paths[cid]
        node = nodes.get(cid)
        if node is None or cid in seen:
            return node["name"] if node else ""
        seen.add(cid)
        parent = node.get("parent")
        name = node.get("name") or cid
        path = f"{walk(parent, seen)}/{name}" if parent and parent in nodes else name
        # The platform tree roots everything under a synthetic "全部" node.
        if path.startswith("全部/"):
            path = path[len("全部/"):]
        paths[cid] = path
        return path

    for cid in nodes:
        walk(cid, set())
    return paths


class Resolver:
    def __init__(self, tree: str, data_dir: Path) -> None:
        payload = load(tree, data_dir)
        self.tree = tree
        self.nodes: dict[str, dict] = payload["nodes"]
        self.paths = build_paths(self.nodes)
        self.by_path: dict[str, str] = {}
        self.by_name: dict[str, list[str]] = {}
        for cid, path in self.paths.items():
            self.by_path.setdefault(path, cid)
            name = path.rsplit("/", 1)[-1]
            self.by_name.setdefault(name, []).append(cid)

    def candidates(self, cids: list[str], limit: int = 8) -> str:
        lines = []
        for cid in cids[:limit]:
            lines.append(f"  {cid}  {self.paths.get(cid, '')}")
        if len(cids) > limit:
            lines.append(f"  ...（共 {len(cids)} 个）")
        return "\n".join(lines)

    def resolve(self, path: str) -> dict:
        wanted = "/".join(part.strip() for part in path.replace("／", "/").split("/") if part.strip())
        if not wanted:
            raise MmiError("类目路径为空")

        if wanted in self.by_path:
            cid = self.by_path[wanted]
            return self._describe(cid)

        if "/" in wanted:
            suffix = "/" + wanted
            matches = [cid for full, cid in self.by_path.items() if full.endswith(suffix)]
            # 淘系树在「全部」「淘小铺」「旅行购物」三个入口下挂了同名子类目，
            # 取最短路径即主站（全部）那一支，其余分支需要写更长的路径或直接给 cid。
            if len(matches) > 1:
                shortest = min(len(self.paths[cid].split("/")) for cid in matches)
                top = [cid for cid in matches if len(self.paths[cid].split("/")) == shortest]
                if len(top) == 1:
                    return self._describe(top[0])
        else:
            matches = self.by_name.get(wanted, [])

        if len(matches) == 1:
            return self._describe(matches[0])
        if not matches:
            raise MmiError(f"[{self.tree}] 找不到类目：{wanted}")
        raise MmiError(
            f"[{self.tree}] 类目名不唯一，请写全路径：{wanted}\n{self.candidates(matches)}"
        )

    def describe(self, cid: str) -> dict:
        return self._describe(str(cid))

    def _describe(self, cid: str) -> dict:
        node = self.nodes[cid]
        return {
            "cid": cid,
            "name": node["name"],
            "path": self.paths.get(cid, node["name"]),
            "level": node["level"],
            "tree": self.tree,
        }

    def search(self, keyword: str, limit: int = 20) -> list[dict]:
        """Relevance first: exact name, then prefix, then substring; shallow first."""
        needle = keyword.strip().lower()
        scored = []
        for cid, path in self.paths.items():
            name = path.rsplit("/", 1)[-1]
            lowered = name.lower()
            if needle not in path.lower():
                continue
            if lowered == needle:
                rank = 0
            elif lowered.startswith(needle):
                rank = 1
            elif needle in lowered:
                rank = 2
            else:
                rank = 3
            scored.append((rank, path.count("/"), path, cid))
        scored.sort()
        return [self._describe(cid) for _rank, _depth, _path, cid in scored[:limit]]


def main() -> int:
    parser = argparse.ArgumentParser(description="同步/解析魔镜类目树")
    parser.add_argument("action", choices=["sync", "resolve", "search", "children"])
    parser.add_argument("--data-dir", default="./data")
    parser.add_argument("--plat", default="all", help="平台 id，默认 all（淘宝+天猫）")
    parser.add_argument("--tree", help="直接指定类目树 taobao/jd/sn/gome/wykl")
    parser.add_argument("--path", help="类目路径，如 面部清洁/护理/面膜")
    parser.add_argument("--cid", help="类目 id")
    parser.add_argument("--keyword", help="搜索关键字")
    parser.add_argument("--force", action="store_true", help="强制重新下载类目树")
    args = parser.parse_args()

    data_dir = resolve_path(args.data_dir)
    tree = args.tree or tree_for_plat(args.plat)

    if args.action == "sync":
        payload = sync(tree, data_dir, force=args.force)
        print(f"{tree}: {payload['count']} 个类目节点 → {tree_file(data_dir, tree)}")
        return 0

    resolver = Resolver(tree, data_dir)

    if args.action == "resolve":
        if not args.path:
            parser.error("resolve 需要 --path")
        info = resolver.resolve(args.path)
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0

    if args.action == "search":
        keyword = args.keyword or args.path
        if not keyword:
            parser.error("search 需要 --keyword")
        for hit in resolver.search(keyword):
            print(f"{hit['cid']:<12}L{hit['level']}  {hit['path']}")
        return 0

    if args.action == "children":
        if not args.cid:
            parser.error("children 需要 --cid")
        node = resolver.nodes.get(args.cid)
        if node is None:
            raise MmiError(f"找不到类目 {args.cid}")
        print(resolver.paths.get(args.cid, node["name"]))
        for child in node["children"]:
            print(f"  {child:<12}{resolver.paths.get(child, '')}")
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
