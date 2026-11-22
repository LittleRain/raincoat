"""Category resolution: paths, duplicate names, and tree parsing."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import categories  # noqa: E402
from mmiapi import MmiError  # noqa: E402

NODES = {
    "1": {"name": "美容护肤", "parent": None, "level": 1, "children": ["2"]},
    "2": {"name": "面部护理", "parent": "1", "level": 2, "children": ["3", "4"]},
    "3": {"name": "面膜", "parent": "2", "level": 3, "children": []},
    "4": {"name": "精华", "parent": "2", "level": 4, "children": []},
    "8": {"name": "洗护", "parent": None, "level": 1, "children": ["5"]},
    "5": {"name": "面膜", "parent": "8", "level": 3, "children": []},
    "6": {"name": "宠物", "parent": None, "level": 1, "children": ["7"]},
    "7": {"name": "猫主粮", "parent": "6", "level": 2, "children": []},
}


def make_tree(data_dir: Path) -> None:
    target = data_dir / "categories" / "taobao.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps({"tree": "taobao", "count": len(NODES), "nodes": NODES}, ensure_ascii=False),
        encoding="utf-8",
    )


class PathTests(unittest.TestCase):
    def test_build_full_paths(self):
        paths = categories.build_paths(NODES)
        self.assertEqual(paths["3"], "美容护肤/面部护理/面膜")
        self.assertEqual(paths["7"], "宠物/猫主粮")

    def test_orphan_parent_stops_at_itself(self):
        nodes = {"9": {"name": "孤立", "parent": "404", "level": 2, "children": []}}
        self.assertEqual(categories.build_paths(nodes)["9"], "孤立")


class ResolveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        make_tree(self.data)
        self.resolver = categories.Resolver("taobao", self.data)

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_path(self):
        info = self.resolver.resolve("美容护肤/面部护理/面膜")
        self.assertEqual(info["cid"], "3")
        self.assertEqual(info["level"], 3)

    def test_path_with_spaces_and_fullwidth_slash(self):
        info = self.resolver.resolve(" 美容护肤 ／ 面部护理 ／ 面膜 ")
        self.assertEqual(info["cid"], "3")

    def test_unique_short_name(self):
        info = self.resolver.resolve("猫主粮")
        self.assertEqual(info["cid"], "7")

    def test_duplicate_name_requires_full_path(self):
        with self.assertRaises(MmiError) as ctx:
            self.resolver.resolve("面膜")
        message = str(ctx.exception)
        self.assertIn("不唯一", message)
        self.assertIn("美容护肤/面部护理/面膜", message)

    def test_suffix_match(self):
        info = self.resolver.resolve("面部护理/面膜")
        self.assertEqual(info["cid"], "3")

    def test_unknown(self):
        with self.assertRaises(MmiError):
            self.resolver.resolve("不存在的/类目")

    def test_search_returns_level_and_path(self):
        hits = self.resolver.search("面膜")
        self.assertEqual({hit["cid"] for hit in hits}, {"3", "5"})


class BranchTests(unittest.TestCase):
    """淘系在「全部」「淘小铺」下挂了同名子类目，只应命中主站那一支。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)
        nodes = {
            "0": {"name": "全部", "parent": None, "level": 1, "children": ["100"]},
            "100": {"name": "洗护", "parent": "0", "level": 2, "children": ["101"]},
            "101": {"name": "面膜", "parent": "100", "level": 3, "children": []},
            "900": {"name": "淘小铺", "parent": "0", "level": 1, "children": ["901"]},
            "901": {"name": "洗护", "parent": "900", "level": 2, "children": ["902"]},
            "902": {"name": "面膜", "parent": "901", "level": 3, "children": []},
        }
        target = self.data / "categories" / "taobao.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"nodes": nodes}, ensure_ascii=False), encoding="utf-8")
        self.resolver = categories.Resolver("taobao", self.data)

    def tearDown(self):
        self.tmp.cleanup()

    def test_synthetic_root_is_stripped(self):
        self.assertEqual(self.resolver.paths["101"], "洗护/面膜")

    def test_shortest_branch_wins(self):
        self.assertEqual(self.resolver.resolve("洗护/面膜")["cid"], "101")

    def test_full_path_of_secondary_branch_still_resolves(self):
        self.assertEqual(self.resolver.resolve("淘小铺/洗护/面膜")["cid"], "902")


class ParseTests(unittest.TestCase):
    def test_parse_static_js(self):
        text = (
            'var cache_cat_taobao = {"status": "ok", "result": {"childrenList": {'
            '"10": {"category_id": "10", "name": "\\u9762\\u819c", "parent_id": "1",'
            ' "level": 3, "chd": [], "is_parent": false}}}},'
            ' other = 1;'
        )
        nodes = categories.parse_tree(text)
        self.assertEqual(nodes["10"]["name"], "面膜")
        self.assertEqual(nodes["10"]["parent"], "1")
        self.assertEqual(nodes["10"]["level"], 3)

    def test_empty_tree_raises(self):
        with self.assertRaises(MmiError):
            categories.parse_tree('var cache_cat_x = {"result": {"childrenList": {}}};')

    def test_jd_uses_category_name(self):
        text = (
            'var cache_cat_jd = {"result": {"childrenList": {'
            '"1392": {"category_id": "1392", "category_name": "\u9762\u819c",'
            ' "parent_id": "1", "level": 3, "chd": []}}}};'
        )
        nodes = categories.parse_tree(text)
        self.assertEqual(nodes["1392"]["name"], "面膜")

    def test_no_json_raises(self):
        with self.assertRaises(MmiError):
            categories.parse_tree("not a tree")


if __name__ == "__main__":
    unittest.main()
