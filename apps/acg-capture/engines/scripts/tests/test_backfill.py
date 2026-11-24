"""补齐（backfill）验收与人工裁决的离线测试：不联网、不写表。

跑法：python3 -m unittest discover -s apps/acg-capture/engines/scripts/tests -v

盯的是 2026-11-17 那次复盘里的两个坑：
1. 「来源未公布数量」被判成「待确认」，人打开面板只看到「数量未找到」，不知道要确认什么；
2. 待确认条目点「采信并写入」时退回去写别的字段，条目变「已采信」而缺的数仍是空 —— 假成功。
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import acg.common as common  # noqa: E402
from acg import accept, gaps, table  # noqa: E402
import acg_run  # noqa: E402

PAN = {
    "panRecordId": "p1",
    "pan": "一番赏 GLAY（日版·一番赏ONLINE）",
    "alias": "一番くじ GLAY",
    "brand": "一番赏",
    "gaps": ["count"],
    "rows": [
        {"recordId": "r-a", "kind": "A", "name": "烫金视觉板"},
        {"recordId": "r-b", "kind": "B", "name": "围巾"},
    ],
}

PAGE = """
A賞 箔押し複製サイン入りビジュアルボード ■全1種 2個
B賞 ストール ■全2種（選べる） 5個
"""


def prize(kind: str, count, source: str = "https://1kuji.com/products/glay", quote: str | None = None) -> dict:
    return {
        "kind": kind,
        "name_cn": kind,
        "count": count,
        "quote": quote if quote is not None else f"{kind}賞 見出し {count}個",
        "source": source,
    }


class VerifyItemTest(unittest.TestCase):
    def setUp(self):
        self.cache: dict = {}
        self._original = accept.fetch_text

    def tearDown(self):
        accept.fetch_text = self._original

    def unreachable(self, url: str):
        return False, "", "ConnectionResetError"

    def page(self, url: str):
        return True, PAGE, ""

    def test_counts_not_published_goes_unavailable_not_pending(self):
        """候选里全是没有数量的赏别（预告页只写款式数）→ 来源未公布，不是待确认。"""
        accept.fetch_text = self.unreachable  # 这时候根本不该去抓页面
        candidate = {"prizes": [prize("A", None), prize("B", None)], "total": None}
        record = accept.verify_item(PAN, candidate, self.cache)

        self.assertEqual(record["status"], "unavailable")
        self.assertEqual(record["fields"], {"count": "unavailable"})
        self.assertIn("count_not_published", record["reasons"])
        self.assertIn("没有这个数", record["ask"])
        self.assertEqual(record["blocked"], [])

    def test_unreachable_source_stays_pending_and_says_which_host(self):
        """有值但页面打不开 → 待确认，并且要说清是哪个域名打不开。"""
        accept.fetch_text = self.unreachable
        candidate = {"prizes": [prize("A", 2), prize("B", 5)], "total": 7}
        record = accept.verify_item(PAN, candidate, self.cache)

        self.assertEqual(record["status"], "pending_review")
        self.assertEqual(record["fields"], {"count": "pending"})
        self.assertEqual(len(record["blocked"]), 2)
        self.assertIn("1kuji.com", record["ask"])
        self.assertIn("打不开", record["ask"])
        self.assertIsNone(record["counts"])

    def test_verified_counts_with_matching_total_are_accepted(self):
        accept.fetch_text = self.page
        candidate = {
            "prizes": [prize("A", 2, quote="A賞 箔押し複製サイン入りビジュアルボード ■全1種 2個"),
                       prize("B", 5, quote="B賞 ストール ■全2種（選べる） 5個")],
            "total": 7,
        }
        record = accept.verify_item(PAN, candidate, self.cache)

        self.assertEqual(record["status"], "accepted")
        self.assertEqual(record["total"], 7)
        self.assertEqual([p["kind"] for p in record["counts"]], ["A", "B"])
        self.assertEqual(record["ask"], "")

    def test_verified_counts_without_total_are_accepted_with_warning(self):
        """来源没写整套抽数：逐条核过的数量仍然成立，只记 warning，不拦。"""
        accept.fetch_text = self.page
        candidate = {
            "prizes": [prize("A", 2, quote="A賞 箔押し複製サイン入りビジュアルボード ■全1種 2個"),
                       prize("B", 5, quote="B賞 ストール ■全2種（選べる） 5個")],
            "total": None,
        }
        record = accept.verify_item(PAN, candidate, self.cache)

        self.assertEqual(record["status"], "accepted")
        self.assertIn("total_not_published", record["warnings"])
        self.assertIn("Σ", record["ask"])

    def test_sum_mismatch_is_rejected(self):
        accept.fetch_text = self.page
        candidate = {
            "prizes": [prize("A", 2, quote="A賞 箔押し複製サイン入りビジュアルボード ■全1種 2個"),
                       prize("B", 5, quote="B賞 ストール ■全2種（選べる） 5個")],
            "total": 70,
        }
        record = accept.verify_item(PAN, candidate, self.cache)

        self.assertEqual(record["status"], "rejected")
        self.assertIsNone(record["counts"])
        self.assertIn("已判废", record["ask"])

    def test_partial_unreachable_is_not_judged_as_sum_mismatch(self):
        """一条赏别打不开：整条不成立，但不能拿「Σ 不平」判废 —— 那是数据错的判法。"""
        def fetch(url: str):
            if "lite" in url:
                return False, "", "ConnectionResetError"
            return True, PAGE, ""

        accept.fetch_text = fetch
        candidate = {
            "prizes": [
                prize("A", 2, quote="A賞 箔押し複製サイン入りビジュアルボード ■全1種 2個"),
                prize("B", 5, source="https://lite.1kuji.com/b", quote="B賞 ストール 5個"),
            ],
            "total": 7,
        }
        record = accept.verify_item(PAN, candidate, self.cache)

        self.assertEqual(record["status"], "pending_review")
        self.assertEqual(record["fields"], {"count": "pending"})
        self.assertIsNone(record["counts"])
        self.assertNotIn("sum_mismatch", " ".join(record["reasons"]))

    def test_no_candidate_is_unavailable(self):
        record = accept.verify_item(PAN, None, self.cache)
        self.assertEqual(record["status"], "unavailable")
        self.assertEqual(record["fields"], {"count": "unavailable"})
        self.assertIn("no_candidate", record["reasons"])


# 一番赏台湾代理页的真实页面（2026-11-17 用渲染器从 oneone.com.tw 抓下来的 innerText）：
# 「獎項」一列是「A賞 名称」，右边一列是「剩餘/總數」，合計行是 56/70。
# 留成夹具是为了以后改验收规则时能离线复现（页面本身经常限流、连不上）。
FIXTURES = Path(__file__).resolve().parent / "fixtures"
TAIWAN_PAGE = (FIXTURES / "oneone-43701.txt").read_text(encoding="utf-8")
# 同一页另一次渲染：顶部多了「恭喜來賓…抽中…A賞…」的中奖跑马灯，A賞/B賞 因此出现多次
TAIWAN_TICKER = (FIXTURES / "oneone-43701-ticker.txt").read_text(encoding="utf-8")
TAIWAN_ROWS = """
圖片	獎項	剩餘/總數
	A賞 流星閃耀絨毛毯收納抱枕 約40公分★	2/2
	B賞 麻每吉立式鏡 約25公分★	1/1
	F賞 12星座金屬吊飾(全12款隨機)	17/19
	H賞 塔麻裝飾12星座貼紙(全4款隨機)	14/18
合計	56/70
"""


class SnapCountTest(unittest.TestCase):
    """模型的 quote 被自己加了注（★、剩餘/總數）时，改成拿值去页面上找它自己那一行。"""

    def test_snaps_total_from_remaining_over_total(self):
        ok, evidence, reason = accept.snap_count(TAIWAN_ROWS, "F", 19)
        self.assertTrue(ok)
        self.assertEqual(reason, "")
        self.assertIn("17/19", evidence)
        self.assertIn("12星座金屬吊飾", evidence)

    def test_partially_sold_pan_uses_total_not_remaining(self):
        """14/18 这种「已经抽掉几抽」的行，单套数量要取总数 18，不是剩余 14。"""
        self.assertTrue(accept.snap_count(TAIWAN_ROWS, "H", 18)[0])
        ok, evidence, reason = accept.snap_count(TAIWAN_ROWS, "H", 14)
        self.assertFalse(ok)
        self.assertEqual(reason, "value_mismatch")
        self.assertIn("14/18", evidence)

    def test_missing_kind_is_unverifiable_not_mismatch(self):
        ok, _, reason = accept.snap_count(TAIWAN_ROWS, "C", 2)
        self.assertFalse(ok)
        self.assertEqual(reason, "value_unverifiable")


    def test_ticker_elsewhere_on_page_does_not_hijack_the_row(self):
        """页面顶部的「恭喜來賓…A賞…」跑马灯里也有 A賞，不能拿它当这一行的证据。"""
        ok, evidence, reason = accept.snap_count(TAIWAN_TICKER, "A", 2)
        self.assertTrue(ok, reason)
        self.assertIn("流星閃耀絨毛毯收納抱枕", evidence)
        self.assertTrue(accept.snap_count(TAIWAN_TICKER, "B", 1)[0])

    def test_two_different_numbers_is_ambiguous_not_mismatch(self):
        """同一赏别在两处给出不同的总数时不下结论（不判错，也不写）。"""
        page = "A賞 某物 2/2\nA賞 另一物 3/5\n"
        ok, evidence, reason = accept.snap_count(page, "A", 2)
        self.assertFalse(ok)
        self.assertEqual(reason, "value_ambiguous")


class QuoteNumberTest(unittest.TestCase):
    """引用逐字命中还不够：引用里的数要和候选一致（3/5 的单套数量是 5，不是 3）。"""

    def test_remaining_over_total_in_quote_must_match_total(self):
        self.assertTrue(accept._quote_count_ok("A賞 某物★ 3/5", 5))
        self.assertFalse(accept._quote_count_ok("A賞 某物★ 3/5", 3))

    def test_plain_number_in_quote(self):
        self.assertTrue(accept._quote_count_ok("A賞 某物 數量 2", 2))
        self.assertFalse(accept._quote_count_ok("A賞 某物 數量 2", 3))


class SnapInVerifyTest(unittest.TestCase):
    def setUp(self):
        self.cache: dict = {}
        self._original = accept.fetch_text

    def tearDown(self):
        accept.fetch_text = self._original

    def test_embellished_quote_still_accepted_with_page_evidence(self):
        """模型把 17/19 写成「★ 17/19（剩餘/總數）」→ 旧逻辑判「原文对不上」，现在按页面那一行核过。"""
        accept.fetch_text = lambda url: (True, TAIWAN_PAGE, "")
        candidate = {
            "prizes": [
                prize("F", 19, quote="F賞 12星座金屬吊飾(全12款隨機)★ 17/19（剩餘/總數）"),
                prize("H", 18, quote="H賞 塔麻裝飾12星座貼紙(全4款隨機)★ 14/18（剩餘/總數）"),
            ],
            "total": 37,
        }
        record = accept.verify_item(PAN, candidate, self.cache)

        self.assertEqual(record["status"], "accepted")
        self.assertEqual(record["total"], 37)
        self.assertEqual([p["count"] for p in record["counts"]], [19, 18])
        self.assertTrue(all(p.get("how") == "snapped" for p in record["counts"]))

    def test_render_retry_when_fetched_page_is_a_long_shell(self):
        """页面能打开、正文很长，但没有奖表（JS 壳）→ 核不上时再渲染一次，而不是判「来源没有」。"""
        shell = "<html><body>" + "會員中心 購買代幣 最新消息 客服中心 " * 80 + "</body></html>"
        accept.fetch_text = lambda url: (True, shell, "")
        candidate = {"prizes": [prize("F", 19, quote="F賞 …★ 17/19（剩餘/總數）")], "total": 19}
        calls = []

        def render(url: str) -> str:
            calls.append(url)
            return TAIWAN_PAGE

        record = accept.verify_item(PAN, candidate, self.cache, render)
        self.assertEqual(record["status"], "accepted")
        self.assertEqual(record["counts"][0]["how"], "rendered")
        self.assertEqual(len(calls), 1)

    def test_page_contradicts_candidate_value(self):
        accept.fetch_text = lambda url: (True, TAIWAN_PAGE, "")
        candidate = {"prizes": [prize("F", 20, quote="随便一段不在页面上的引用超过十个字")], "total": 20}
        record = accept.verify_item(PAN, candidate, self.cache)

        self.assertEqual(record["status"], "rejected")
        self.assertIn("value_mismatch", " ".join(record["reasons"]))

    def test_last_prize_is_ignored_not_blocking(self):
        """LAST 固定 1 个、页面也不写数量：不能因为它拉低「全部核实」的判断。"""
        accept.fetch_text = lambda url: (True, TAIWAN_PAGE, "")
        candidate = {
            "prizes": [
                prize("F", 19, quote="F賞 12星座金屬吊飾(全12款隨機) 17/19"),
                prize("Last", 1, quote="最後賞 與星星在一起麻每吉絨毛玩偶（最後一抽附贈）"),
            ],
            "total": 19,
        }
        record = accept.verify_item(PAN, candidate, self.cache)

        self.assertEqual(record["status"], "accepted")
        self.assertEqual([p["kind"] for p in record["counts"]], ["F"])

    def test_render_fallback_when_urllib_gets_js_shell(self):
        """代理页是 JS 壳：urllib 只拿到导航栏，渲染兜底拿到正文后照常核过。"""
        accept.fetch_text = lambda url: (True, "<html><body>會員中心 購買代幣</body></html>", "")
        candidate = {"prizes": [prize("F", 19, quote="F賞 …★ 17/19（剩餘/總數）")], "total": 19}
        calls = []

        def render(url: str) -> str:
            calls.append(url)
            return TAIWAN_PAGE

        record = accept.verify_item(PAN, candidate, self.cache, render)
        self.assertEqual(record["status"], "accepted")
        self.assertEqual(len(calls), 1, "渲染只该发生一次（按 URL 缓存）")


class PlanManualWriteTest(unittest.TestCase):
    def test_only_the_gap_field_is_written(self):
        """缺数量时不要去写价格：价格本来就有，写了会盖住「数量没写进去」。"""
        item = {
            "panRecordId": "p1",
            "gaps": ["count"],
            "candidate": {
                "price": {"value": 880, "currency": "JPY", "quote": "880円", "source": "https://1kuji.com/x"},
                "prizes": [prize("A", 2), prize("B", 5)],
            },
        }
        plan = accept.plan_manual_write(item, PAN, item["candidate"])

        self.assertIsNone(plan["price"])
        self.assertEqual([row["record_id"] for row in plan["counts"]], ["r-a", "r-b"])
        self.assertEqual(plan["missing"], [])

    def test_nothing_writable_reports_missing(self):
        """候选里没有数量 → 计划为空，缺失项要说清是哪个缺口。"""
        item = {"panRecordId": "p1", "gaps": ["count"], "candidate": {"prizes": [prize("A", None)]}}
        plan = accept.plan_manual_write(item, PAN, {"prizes": [prize("A", None)]})

        self.assertIsNone(plan["price"])
        self.assertEqual(plan["counts"], [])
        self.assertEqual(plan["missing"], ["count"])


class DecideTest(unittest.TestCase):
    """人工裁决：写不进任何东西时必须报错，不能把条目改成「已采信」。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._runs_dir = common.RUNS_DIR
        common.RUNS_DIR = Path(self.tmp.name)
        self.run_id = "r-20261117-120000-backfill"
        self.run_dir = common.RUNS_DIR / self.run_id
        self.run_dir.mkdir(parents=True)

    def tearDown(self):
        common.RUNS_DIR = self._runs_dir
        self.tmp.cleanup()

    def write_run(self, item: dict) -> None:
        state = {
            "id": self.run_id,
            "kind": "backfill",
            "dryRun": False,
            "status": "done",
            "counts": {"dispatched": 1, "done": 1, "accepted": 0, "rejected": 0,
                       "pending": 1, "unavailable": 0, "written": 0},
            "batch": [PAN],
            "items": [item],
        }
        (self.run_dir / "run.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def read_item(self) -> dict:
        state = json.loads((self.run_dir / "run.json").read_text(encoding="utf-8"))
        return state["items"][0]

    def run_decide(self, decision: str) -> tuple[int, dict]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = acg_run.decide(self.run_id, "i-p1", decision, "人看的", "", True)
        return code, json.loads(out.getvalue() or "{}")

    def test_accept_without_writable_counts_fails_and_keeps_status(self):
        item = {
            "id": "i-p1",
            "pan": PAN["pan"],
            "panRecordId": "p1",
            "gap": "count",
            "status": "unavailable",
            "reasons": ["count_not_published"],
            "candidate": {"prizes": [prize("A", None)], "price": {"value": 880, "currency": "JPY", "quote": "880円"}},
        }
        self.write_run(item)

        code, payload = self.run_decide("accept")

        self.assertEqual(code, 1)
        self.assertIn("采信写不进任何东西", payload["error"])
        self.assertEqual(self.read_item()["status"], "unavailable")

    def test_accept_writes_only_gap_fields(self):
        item = {
            "id": "i-p1",
            "pan": PAN["pan"],
            "panRecordId": "p1",
            "gap": "count",
            "status": "pending_review",
            "reasons": [],
            "candidate": {"prizes": [prize("A", 2), prize("B", 5)], "price": {"value": 880, "currency": "JPY", "quote": "880円"}},
        }
        self.write_run(item)

        code, payload = self.run_decide("accept")

        self.assertEqual(code, 0)
        self.assertEqual(payload["planned"], {"price": 0, "counts": 2, "subs": 0})
        self.assertEqual(self.read_item()["status"], "accepted")
        self.assertEqual(self.read_item()["wroteFields"], ["count"])

    def test_reject_moves_bucket(self):
        item = {
            "id": "i-p1",
            "pan": PAN["pan"],
            "panRecordId": "p1",
            "gap": "count",
            "status": "pending_review",
            "reasons": [],
            "candidate": {},
        }
        self.write_run(item)

        code, _ = self.run_decide("reject")
        state = json.loads((self.run_dir / "run.json").read_text(encoding="utf-8"))

        self.assertEqual(code, 0)
        self.assertEqual(state["counts"]["pending"], 0)
        self.assertEqual(state["counts"]["rejected"], 1)


class DiscoverDecideTest(unittest.TestCase):
    """抓新品的待确认：采信 = 建一行新盘，不碰价格/数量列。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._runs_dir = common.RUNS_DIR
        common.RUNS_DIR = Path(self.tmp.name)
        self.run_id = "r-20261117-110926-discover"
        self.run_dir = common.RUNS_DIR / self.run_id
        self.run_dir.mkdir(parents=True)
        state = {
            "id": self.run_id,
            "kind": "discover",
            "dryRun": True,
            "status": "done",
            "counts": {"accepted": 0, "rejected": 0, "pending": 1, "unavailable": 0, "written": 0},
            "items": [{
                "id": "d-1",
                "pan": "一番赏 崩坏：星穹铁道 第四弹",
                "brand": "一番赏",
                "gap": "new",
                "status": "pending_review",
                "reasons": ["render_incomplete"],
                "candidate": {"name": "一番赏 崩坏：星穹铁道 第四弹", "brand": "一番赏"},
            }],
        }
        (self.run_dir / "run.json").write_text(json.dumps(state, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        common.RUNS_DIR = self._runs_dir
        self.tmp.cleanup()

    def test_accept_creates_new_pan_row(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = acg_run.decide(self.run_id, "d-1", "accept", "人工核对过", "", True)
        payload = json.loads(out.getvalue() or "{}")

        self.assertEqual(code, 0)
        self.assertEqual(payload["planned"], {"price": 0, "counts": 0, "pans": 1, "subs": 0})
        state = json.loads((self.run_dir / "run.json").read_text(encoding="utf-8"))
        self.assertEqual(state["items"][0]["status"], "accepted")
        self.assertEqual(state["counts"]["pending"], 0)


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------- 无子品（sub）


SUB_PAN = {
    "panRecordId": "p9",
    "pan": "一番赏 CANDY TUNE（日版·一番赏ONLINE）",
    "alias": "一番くじ CANDY TUNE",
    "brand": "一番赏",
    "price": "700円/抽（日版）",
    "release": "预告：2027-03-13",
    "gaps": ["sub"],
    "rows": [],
    "rowCount": 0,
}

SUB_PAGE = """
A賞 流星閃耀絨毛毯收納抱枕 ■全1種 2個
B賞 麻每吉立式鏡 ■全1種 1個
LAST賞 與星星在一起麻每吉絨毛玩偶（最後一抽附贈）
"""


def sub_prize(kind: str, name: str, count=None, alias: str = "") -> dict:
    quote = name if count is None else f"{kind}賞 {name} ■全1種 {count}個"
    return {
        "kind": kind,
        "name_cn": name,
        "alias": alias,
        "count": count,
        "quote": quote,
        "source": "https://1kuji.com/products/candytune",
    }


class SubGapQueueTest(unittest.TestCase):
    """2026-11-18 口径：无子品的盘（sub）必须进本轮派单队列，且排在最前面。"""

    def pan(self, rid: str, name: str, price: str = "700円/抽（日版）") -> dict:
        return {"rid": rid, "name": name, "alias": "", "brand": "一番赏", "ip": "",
                "price": price, "release": "", "released": "", "channel": "",
                "updateTime": "", "createTime": ""}

    def sub(self, rid: str, pan_rid: str, kind: str, qty) -> dict:
        return {"rid": rid, "pan_rid": pan_rid, "pan_name": "", "kind": kind,
                "name": kind, "alias": "", "qty": qty, "type": "", "updateTime": ""}

    def test_empty_pan_is_queued_as_sub_gap(self):
        pans = [self.pan("p1", "一番赏 有结构的盘"), self.pan("p2", "一番赏 无子品的盘")]
        subs = [self.sub("s1", "p1", "A", None)]
        result = gaps.compute(pans, subs)

        self.assertIn("p2", result["byPan"])
        self.assertEqual(result["byPan"]["p2"]["gaps"], ["sub"])
        self.assertEqual(result["stats"]["subPans"], 1)
        self.assertEqual(result["stats"]["queuePans"], 2)

    def test_sub_pans_rank_before_count_pans(self):
        pans = [self.pan("p1", "一番赏 缺数量的盘"), self.pan("p2", "一番赏 无子品的盘")]
        subs = [self.sub(f"s{i}", "p1", kind, None) for i, kind in enumerate("ABCD")]
        batch = gaps.pick_batch(gaps.compute(pans, subs)["byPan"], 999)

        self.assertEqual([item["panRecordId"] for item in batch], ["p2", "p1"])

    def test_price_and_sub_are_both_listed(self):
        pans = [self.pan("p1", "一番赏 又没有子品又没价", price="未公布")]
        result = gaps.compute(pans, [])
        self.assertEqual(result["byPan"]["p1"]["gaps"], ["sub", "price"])

    def test_default_batch_covers_every_queue_item(self):
        """默认批次不再截断：表里有几个缺口盘就派几个。"""
        pans = [self.pan(f"p{i}", f"一番赏 盘{i}") for i in range(12)]
        subs = [self.sub("s0", "p0", "A", None)]
        batch = gaps.pick_batch(gaps.compute(pans, subs)["byPan"])
        self.assertEqual(len(batch), 12)


class VerifySubTest(unittest.TestCase):
    def setUp(self):
        self.cache: dict = {}
        self._original = accept.fetch_text

    def tearDown(self):
        accept.fetch_text = self._original

    def test_names_and_counts_verified_builds_structure(self):
        accept.fetch_text = lambda url: (True, SUB_PAGE, "")
        candidate = {
            "prizes": [
                sub_prize("A", "流星閃耀絨毛毯收納抱枕", 2),
                sub_prize("B", "麻每吉立式鏡", 1),
                sub_prize("LAST", "與星星在一起麻每吉絨毛玩偶"),
            ],
            "total": 3,
        }
        record = accept.verify_item(SUB_PAN, candidate, self.cache)

        self.assertEqual(record["status"], "accepted")
        self.assertEqual(record["fields"], {"sub": "accepted"})
        self.assertEqual([p["kind"] for p in record["subs"]], ["A", "B", "LAST"])
        self.assertIsNone(record["subs"][-1]["count"], "LAST 不写单套数量")
        self.assertEqual(record["total"], 3)

    def test_names_without_counts_still_build_rows(self):
        """预告页只给赏名、不给逐赏个数：结构照样建，数量留空是正确状态。"""
        accept.fetch_text = lambda url: (True, SUB_PAGE, "")
        candidate = {
            "prizes": [sub_prize("A", "流星閃耀絨毛毯收納抱枕"),
                       sub_prize("B", "麻每吉立式鏡")],
            "total": None,
        }
        record = accept.verify_item(SUB_PAN, candidate, self.cache)

        self.assertEqual(record["status"], "accepted")
        self.assertEqual(len(record["subs"]), 2)
        self.assertTrue(all(p["count"] is None for p in record["subs"]))
        self.assertIn("count_not_published", record["warnings"])
        self.assertIn("留空", record["ask"])

    def test_unreachable_source_is_pending_not_written(self):
        accept.fetch_text = lambda url: (False, "", "ConnectionResetError")
        candidate = {"prizes": [sub_prize("A", "流星閃耀絨毛毯收納抱枕", 2)], "total": 2}
        record = accept.verify_item(SUB_PAN, candidate, self.cache)

        self.assertEqual(record["status"], "pending_review")
        self.assertEqual(record["fields"], {"sub": "pending"})
        self.assertIsNone(record["subs"])
        self.assertIn("1kuji.com", record["ask"])

    def test_name_not_on_page_is_not_written(self):
        """赏名编的/对不上：不建行（下一轮再补），但也不判废。"""
        accept.fetch_text = lambda url: (True, SUB_PAGE, "")
        candidate = {"prizes": [sub_prize("A", "页面上没有的赏名"), sub_prize("B", "麻每吉立式鏡")],
                     "total": None}
        record = accept.verify_item(SUB_PAN, candidate, self.cache)

        self.assertEqual(record["status"], "unavailable")
        self.assertIsNone(record["subs"])
        self.assertIn("name_unverified:A", record["reasons"])

    def test_sum_mismatch_is_rejected(self):
        accept.fetch_text = lambda url: (True, SUB_PAGE, "")
        candidate = {"prizes": [sub_prize("A", "流星閃耀絨毛毯收納抱枕", 2),
                                sub_prize("B", "麻每吉立式鏡", 1)],
                     "total": 70}
        record = accept.verify_item(SUB_PAN, candidate, self.cache)

        self.assertEqual(record["status"], "rejected")
        self.assertIsNone(record["subs"])

    def test_secondhand_source_is_rejected(self):
        candidate = {
            "prizes": [{**sub_prize("A", "流星閃耀絨毛毯收納抱枕", 2),
                        "source": "https://www.xianyu.com/item/1"}],
            "total": 2,
        }
        record = accept.verify_item(SUB_PAN, candidate, self.cache)
        self.assertEqual(record["status"], "rejected")
        self.assertIn("secondhand_forbidden", record["reasons"])


class SubWritePlanTest(unittest.TestCase):
    def test_manual_plan_carries_rows_to_create(self):
        item = {"panRecordId": "p9", "pan": SUB_PAN["pan"], "gaps": ["sub"],
                "subs": [{"kind": "A", "name": "流星閃耀絨毛毯收納抱枕", "alias": "", "count": 2}]}
        plan = accept.plan_manual_write(item, SUB_PAN, {})

        self.assertEqual(len(plan["subs"]), 1)
        self.assertEqual(plan["subs"][0]["pan_record_id"], "p9")
        self.assertEqual(plan["subs"][0]["count"], 2)
        self.assertEqual(plan["missing"], [])

    def test_write_plan_builds_add_records_linked_to_pan(self):
        record = {"status": "accepted", "panRecordId": "p9", "pan": SUB_PAN["pan"],
                  "subs": [{"kind": "A", "name": "流星閃耀絨毛毯收納抱枕", "alias": "ぬいぐるみ",
                            "count": 2},
                           {"kind": "LAST", "name": "與星星在一起麻每吉絨毛玩偶", "alias": "", "count": None}]}
        plan = acg_run.build_write_plan([record], [SUB_PAN])

        self.assertEqual(len(plan["subs"]), 2)
        values = plan["subs"][0]["values"]
        self.assertEqual(values["关联"], [{"record_id": "p9"}])
        self.assertEqual(json.loads(values["赏别"])[0]["text"], "A")
        self.assertEqual(json.loads(values["子品名称"])[0]["text"], "流星閃耀絨毛毯收納抱枕")
        self.assertEqual(values["单套数量"], 2)
        self.assertEqual(json.loads(values["别名"])[0]["text"], "ぬいぐるみ")
        self.assertNotIn("单套数量", plan["subs"][1]["values"], "LAST 不写数量")
