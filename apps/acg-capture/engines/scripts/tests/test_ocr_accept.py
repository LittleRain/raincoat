"""验收层的 OCR 兜底与「验证页」判定的离线测试：不联网、不读图。

跑法：python3 -m unittest discover -s apps/acg-capture/engines/scripts/tests -v

盯的是 2026-11-23 的集换赏案例：价格和逐赏表都只印在公众号配图里，
文本校验必然判 quote_mismatch / name_unverified；另外微信反爬页本来就是「打不开」，
不该判成「原文对不上」。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from acg import accept  # noqa: E402

PAN_COUNT = {"panRecordId": "p1", "pan": "一番赏 测试盘", "alias": "", "brand": "一番赏", "gaps": ["count"]}
PAN_PRICE = {"panRecordId": "p2", "pan": "集换赏 测试盘", "alias": "", "brand": "集换赏", "gaps": ["price"]}
PAN_SUB = {"panRecordId": "p3", "pan": "集换赏 测试盘", "alias": "", "brand": "集换赏", "gaps": ["sub"]}

WECHAT = "http://mp.weixin.qq.com/s?__biz=test"

BLOCK_PAGE = (
    "<html><body><div>环境异常</div>"
    "<div>当前环境异常，完成验证后即可继续访问。</div><div>去验证</div></body></html>"
)
PLAIN_PAGE = "这是一篇正常文章。" * 60  # 超过 400 字，_page 不会再走渲染

OCR_SUB_TEXT = """
集换赏
A賞
全角色麻将收藏礼盒
全1种共2个，约26*20mm
B賞
透明开窗斜跨包
全1种共2个，约41*27cm
D賞
流沙牌尺
全彐种共习个，约26*彐cm
"""


def prize(kind: str, count, name: str = "", quote: str = "", source: str = WECHAT) -> dict:
    return {"kind": kind, "name_cn": name or kind, "alias": "", "count": count, "quote": quote, "source": source}


class BlockedPageTest(unittest.TestCase):
    def setUp(self):
        self.cache: dict = {}
        self._original = accept.fetch_text

    def tearDown(self):
        accept.fetch_text = self._original

    def test_verification_page_is_pending_not_rejected(self):
        """微信「环境异常」页 = 打不开，不是原文对不上。"""
        accept.fetch_text = lambda url: (True, BLOCK_PAGE, "")
        record = accept.verify_item(PAN_COUNT, {"prizes": [prize("A", 2)], "total": 2}, self.cache)

        self.assertEqual(record["status"], "pending_review")
        self.assertEqual(record["fields"]["count"], "pending")
        self.assertEqual(record["blocked"][0]["error"], "blocked_page")
        self.assertNotIn("quote_mismatch", record["reasons"])

    def test_ocr_rescues_verification_page(self):
        """验证页挡得住 urllib、挡不住真浏览器：OCR 拿到的原文照样算数。"""
        accept.fetch_text = lambda url: (True, BLOCK_PAGE, "")
        candidate = {"prizes": [prize("A", 2, quote="全1种共2个")], "total": 2}
        record = accept.verify_item(PAN_COUNT, candidate, self.cache, ocr=lambda url: "A賞 全1种共2个")

        self.assertEqual(record["status"], "accepted")
        self.assertEqual(record["fields"]["count"], "accepted")
        self.assertEqual(record["blocked"], [])

    def test_render_rescues_verification_page(self):
        """渲染能拿到真正文时照常验收，不因反爬页丢掉这一盘。"""
        accept.fetch_text = lambda url: (True, BLOCK_PAGE, "")
        page = "A賞 見出し 2個\nB賞 見出し 5個"
        candidate = {"prizes": [prize("A", 2, quote="A賞 見出し 2個"), prize("B", 5, quote="B賞 見出し 5個")], "total": 7}
        record = accept.verify_item(PAN_COUNT, candidate, self.cache, render=lambda url: page)

        self.assertEqual(record["status"], "accepted")
        self.assertEqual(record["fields"]["count"], "accepted")

    def test_without_ocr_image_only_evidence_is_not_accepted(self):
        """没开 OCR 时行为不变：正文里没有的原文，图里再多也不算核过。"""
        accept.fetch_text = lambda url: (True, PLAIN_PAGE, "")
        candidate = {"prizes": [prize("A", 2, quote="全1种共2个")], "total": 2}
        record = accept.verify_item(PAN_COUNT, candidate, self.cache)

        self.assertEqual(record["status"], "unavailable")
        self.assertNotEqual(record["fields"]["count"], "accepted")
        self.assertIn("value_unverifiable:A", record["reasons"])


class OcrFallbackTest(unittest.TestCase):
    def setUp(self):
        self.cache: dict = {}
        self._original = accept.fetch_text

    def tearDown(self):
        accept.fetch_text = self._original

    def test_price_verified_from_image_text(self):
        accept.fetch_text = lambda url: (True, PLAIN_PAGE, "")
        quote = "建议零售价 69元/次 2026年5月发售 共83抽"
        candidate = {
            "price": {"value": 69, "currency": "CNY", "quote": quote, "source": WECHAT},
            "prizes": [],
            "total": None,
        }
        record = accept.verify_item(PAN_PRICE, candidate, self.cache, ocr=lambda url: OCR_SUB_TEXT + quote)

        self.assertEqual(record["fields"]["price"], "accepted")
        self.assertEqual(record["price"]["value"], 69)
        self.assertIn("quote_ocr", record["warnings"])

    def test_sub_structure_verified_from_image_text(self):
        accept.fetch_text = lambda url: (True, PLAIN_PAGE, "")
        candidate = {
            "prizes": [
                prize("A", 2, name="全角色麻将收藏礼盒", quote="全1种共2个"),
                prize("B", 2, name="透明开窗斜跨包", quote="全1种共2个"),
            ],
            "total": 4,
        }
        record = accept.verify_item(PAN_SUB, candidate, self.cache, ocr=lambda url: OCR_SUB_TEXT)

        self.assertEqual(record["status"], "accepted")
        self.assertEqual(record["fields"]["sub"], "accepted")
        self.assertEqual([p["how"] for p in record["subs"]], ["ocr", "ocr"])
        self.assertEqual(record["total"], 4)

    def test_ocr_miss_keeps_original_verdict(self):
        """OCR 读了但没命中：判定必须和「没开 OCR」完全一致，不能因为试过就放宽。"""
        accept.fetch_text = lambda url: (True, PLAIN_PAGE, "")
        candidate = {"prizes": [prize("A", 2, quote="全1种共2个")], "total": 2}
        base = accept.verify_item(PAN_COUNT, candidate, {})
        record = accept.verify_item(PAN_COUNT, candidate, {}, ocr=lambda url: "完全无关的图注")

        self.assertEqual(
            (record["status"], record["reasons"], record["fields"]),
            (base["status"], base["reasons"], base["fields"]),
        )

    def test_ocr_numbers_never_hard_reject(self):
        """OCR 认错数字不构成判废：退回「未核实」，理由里不留 value_mismatch。

        2↔已、3↔习/彐、8↔日 是 Vision 在这类美术字上的固定误读，
        拿它判废会误杀本来结构完好的盘；数字留空交人工补即可。
        """
        accept.fetch_text = lambda url: (True, PLAIN_PAGE, "")
        candidate = {"prizes": [prize("A", 2, quote="全1种共3个")], "total": 3}
        record = accept.verify_item(PAN_COUNT, candidate, {}, ocr=lambda url: "全1种共3个")

        self.assertNotEqual(record["status"], "rejected")
        self.assertFalse([r for r in record["reasons"] if r.startswith("value_mismatch")])
        self.assertEqual(record["fields"]["count"], "unavailable")

    def test_ocr_unreadable_count_keeps_structure(self):
        """数量读不出来时，赏名结构仍然要留下（结构比数量值钱）。"""
        accept.fetch_text = lambda url: (True, PLAIN_PAGE, "")
        candidate = {
            "prizes": [
                prize("A", 2, name="全角色麻将收藏礼盒", quote="全1种共2个"),
                prize("D", 3, name="流沙牌尺", quote="全3种共3个"),
            ],
            "total": 5,
        }
        record = accept.verify_item(PAN_SUB, candidate, {}, ocr=lambda url: OCR_SUB_TEXT)

        self.assertEqual(record["fields"]["sub"], "accepted")
        self.assertEqual(record["status"], "accepted")
        self.assertIn("count_ocr_unreadable:D", record["warnings"])
        self.assertEqual([p["count"] for p in record["subs"]], [2, None])

    def test_uncited_count_keeps_structure(self):
        """名字在、数量那段原文不在：结构照建、数量留空，不判废（判废只认「原文命中且数字冲突」）。"""
        accept.fetch_text = lambda url: (True, "A賞 全角色麻将收藏礼盒 " + PLAIN_PAGE, "")
        candidate = {"prizes": [prize("A", 3, name="全角色麻将收藏礼盒", quote="全3种共3个")], "total": 3}
        record = accept.verify_item(PAN_SUB, candidate, self.cache)

        self.assertEqual(record["fields"]["sub"], "accepted")
        self.assertEqual(record["subs"][0]["count"], None)
        self.assertIn("count_unverifiable:A", record["warnings"])
        self.assertNotIn("value_mismatch:A", record["reasons"])

    def test_ocr_failure_is_swallowed(self):
        """OCR 抛异常时按「没有图」处理，不影响原有判定。"""
        accept.fetch_text = lambda url: (True, PLAIN_PAGE, "")

        def boom(url):
            raise RuntimeError("ocr crashed")

        candidate = {"prizes": [prize("A", 2, quote="全1种共2个")], "total": 2}
        base = accept.verify_item(PAN_COUNT, candidate, {})
        record = accept.verify_item(PAN_COUNT, candidate, {}, ocr=boom)
        self.assertEqual((record["status"], record["reasons"]), (base["status"], base["reasons"]))


if __name__ == "__main__":
    unittest.main()
