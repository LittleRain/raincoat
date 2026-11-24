"""官方赏补齐双通道（workbuddy + DeepSeek）的离线测试：不联网、不写表、不派 Agent。

跑法：python3 -m unittest discover -s apps/acg-capture/engines/scripts/tests -v

盯的是 2026-11-18 用户提出的口径：补齐不能只靠 workbuddy 翻官方页面，
DeepSeek 搜索结果也要进同一条流水线，且合并后仍过同一套验收。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from acg import accept, backfill_ds  # noqa: E402

JP_PAN = {
    "panRecordId": "p1",
    "pan": "一番赏 GLAY（日版·一番赏ONLINE）",
    "alias": "一番くじ GLAY",
    "gaps": ["count"],
}

CN_PAN = {
    "panRecordId": "p2",
    "pan": "一番赏 时光代理人",
    "alias": "",
    "gaps": ["sub", "price"],
}


class QueryTests(unittest.TestCase):
    def test_jp_pan_queries_start_with_alias(self):
        queries = backfill_ds.pan_queries(JP_PAN)
        self.assertTrue(queries[0].startswith("一番くじ GLAY"))
        self.assertTrue(any("oneone" in query for query in queries))
        # 渠道后缀不进检索词，否则搜不到日文页
        self.assertFalse(any("日版·一番赏ONLINE" in query for query in queries))

    def test_cn_pan_queries_use_name(self):
        queries = backfill_ds.pan_queries(CN_PAN)
        self.assertTrue(any(query.startswith("一番赏 时光代理人") for query in queries))
        self.assertTrue(any("抽数" in query or "多少抽" in query for query in queries))


class ParseTests(unittest.TestCase):
    def test_parse_items_strips_markdown_fence(self):
        text = '```json\n[{"pan":"一番赏 GLAY","prizes":[]}]\n```'
        items = backfill_ds.parse_items(text)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["lane"], "deepseek")

    def test_parse_items_rejects_garbage(self):
        self.assertEqual(backfill_ds.parse_items("材料里没有这个盘"), [])
        self.assertEqual(backfill_ds.parse_items('[{"a":1}'), [])


def wb_candidate() -> dict:
    return {
        "pan": "一番赏 GLAY",
        "price": {"value": None, "currency": "JPY", "quote": "", "source": ""},
        "total": 40,
        "prizes": [
            {"kind": "A", "name_cn": "视觉板", "count": 1, "quote": "A賞 1個", "source": "https://1kuji.com/p/glay"},
            {"kind": "B", "name_cn": "围巾", "count": 5, "quote": "B賞 5個", "source": "https://1kuji.com/p/glay"},
        ],
        "lane": "workbuddy",
    }


def ds_candidate() -> dict:
    return {
        "pan": "一番賞 GLAY",
        "price": {"value": 880, "currency": "JPY", "quote": "1回880円(税込)", "source": "https://1kuji.com/p/glay"},
        "total": None,
        "prizes": [
            {"kind": "A", "name_cn": "視覺板", "count": None, "quote": "", "source": ""},
            {"kind": "C", "name_cn": "PUNY BEANS 公仔", "count": 4, "quote": "C賞 4個", "source": "https://1kuji.com/p/glay"},
        ],
        "lane": "deepseek",
    }


class MergeTests(unittest.TestCase):
    def test_match_all_returns_both_lanes(self):
        matched = accept.match_all(JP_PAN, [wb_candidate(), ds_candidate()])
        self.assertEqual(len(matched), 2)

    def test_match_all_ignores_unrelated_pan(self):
        other = {"pan": "一番赏 咒术回战", "prizes": []}
        self.assertEqual(accept.match_all(JP_PAN, [other]), [])

    def test_merge_candidates_fills_price_and_keeps_counts(self):
        merged = accept.merge_candidates(accept.match_all(JP_PAN, [wb_candidate(), ds_candidate()]))
        self.assertIsNotNone(merged)
        # 价格只有 DeepSeek 通道拿到
        self.assertEqual(merged["price"]["value"], 880)
        by_kind = {prize["kind"]: prize for prize in merged["prizes"]}
        # 同一赏别：保留带 count 的那条（workbuddy）
        self.assertEqual(by_kind["A"]["count"], 1)
        self.assertEqual(by_kind["B"]["count"], 5)
        # 另一通道独有的赏别要补进来
        self.assertEqual(by_kind["C"]["count"], 4)
        # 两边的 total 取有值的那份
        self.assertEqual(merged["total"], 40)
        self.assertEqual(merged["lanes"], ["deepseek", "workbuddy"])

    def test_merge_does_not_overwrite_existing_price(self):
        first = wb_candidate()
        first["price"] = {"value": 780, "currency": "JPY", "quote": "1回780円", "source": "https://1kuji.com/p/glay"}
        merged = accept.merge_candidates([first, ds_candidate()])
        self.assertEqual(merged["price"]["value"], 780)

    def test_merge_single_candidate_passthrough(self):
        merged = accept.merge_candidates([wb_candidate()])
        self.assertEqual(merged["pan"], "一番赏 GLAY")

    def test_merge_empty_returns_none(self):
        self.assertIsNone(accept.merge_candidates([]))


class LegacyMatchTests(unittest.TestCase):
    def test_match_candidate_still_returns_first_hit(self):
        # 老路径（--reaccept / 单通道）不能被 match_all 的引入改变行为
        hit = accept.match_candidate(JP_PAN, [wb_candidate(), ds_candidate()])
        self.assertEqual(hit["lane"], "workbuddy")


if __name__ == "__main__":
    unittest.main()
