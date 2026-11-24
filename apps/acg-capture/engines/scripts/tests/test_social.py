"""社媒通道（微博 / 小红书）的离线测试：不联网、不开浏览器、不调模型。

跑法：python3 -m unittest discover -s apps/acg-capture/engines/scripts/tests -v

盯的是三件事：
1. 风控优先：命中验证码/登录墙/频率限制就立刻停，并写冷却，冷却期内一个请求都不发；
2. 预算与串行：单轮盘数有上限，命中风控后不再继续后面的盘；
3. 通道定位：social 是补充通道，它挂了不能把整轮拖成 partial，但台账必须留痕。
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import acg.common as common  # noqa: E402
import acg_run  # noqa: E402
from acg import social  # noqa: E402


def make_pan(index: int, gaps=("sub",)) -> dict:
    """表里的行（gaps 要 rid/name）和社媒输入（要 pan/gaps）合成一份。"""
    return {
        "rid": f"p{index}",
        "panRecordId": f"p{index}",
        "name": f"一番赏 测试盘 {index}",
        "pan": f"一番赏 测试盘 {index}",
        "alias": "",
        "brand": "一番赏",
        "price": "未公布",
        "release": "",
        "gaps": list(gaps),
    }


class BlockDetectTest(unittest.TestCase):
    def test_verification_and_login_words_are_blocked(self):
        for text in ("请输入验证码", "登录后查看", "操作太频繁，请稍后再试", "账号异常"):
            self.assertTrue(social.blocked(f"……{text}……"), text)

    def test_normal_copy_is_not_blocked(self):
        self.assertEqual(social.blocked("一番赏 蓝色监狱 全5种 共20个 69元/次"), "")


class CooldownTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "cooldown.json"
        self._original = social.COOLDOWN_FILE
        social.COOLDOWN_FILE = self.path

    def tearDown(self):
        social.COOLDOWN_FILE = self._original
        self.tmp.cleanup()

    def test_set_then_read(self):
        self.assertEqual(social.cooldown(), {})
        social.set_cooldown("xhs:blocked:安全验证", hours=2)
        state = social.cooldown()
        self.assertTrue(state.get("until"))
        self.assertIn("安全验证", state.get("reason", ""))

    def test_expired_cooldown_is_ignored(self):
        self.path.write_text(
            json.dumps({"until": "2000-01-01T00:00:00+08:00", "reason": "old"}), encoding="utf-8"
        )
        self.assertEqual(social.cooldown(), {})


class CollectTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workdir = Path(self.tmp.name)
        self._original = social.COOLDOWN_FILE
        social.COOLDOWN_FILE = self.workdir / "cooldown.json"

    def tearDown(self):
        social.COOLDOWN_FILE = self._original
        self.tmp.cleanup()

    def test_cooldown_blocks_every_request(self):
        social.set_cooldown("xhs:blocked", hours=4)
        with mock.patch.object(social, "search_weibo") as weibo, mock.patch.object(social, "search_xhs") as xhs:
            result = social.collect(make_pan(1), self.workdir)
        self.assertFalse(result["ok"])
        self.assertIn("cooldown_until", result["error"])
        weibo.assert_not_called()
        xhs.assert_not_called()

    def test_xhs_block_stops_the_whole_round(self):
        """小红书一命中风控：不再搜第二个词、不再开详情，并写冷却。"""
        with mock.patch.object(social, "search_weibo", return_value=(True, [], "")) as weibo, mock.patch.object(
            social, "search_xhs", return_value=(False, [], "blocked:安全验证")
        ) as xhs:
            result = social.collect(make_pan(1), self.workdir)
        self.assertFalse(result["ok"])
        self.assertTrue(result["error"].startswith("blocked"))
        self.assertEqual(weibo.call_count, 1)
        self.assertEqual(xhs.call_count, 1)
        self.assertTrue(social.cooldown(), "命中风控必须写冷却")

    def test_login_wall_keeps_weibo_and_skips_cooldown(self):
        """小红书登录墙不是风控：微博照跑、不写冷却，但要把 login_wall 记进错误。"""
        posts = [{"url": "https://m/1", "text": "一番赏 测试盘 全1种共2个"}]
        with mock.patch.object(social, "search_weibo", return_value=(True, posts, "")), mock.patch.object(
            social, "search_xhs", return_value=(False, [], "login_wall")
        ), mock.patch.object(social, "_pause"):
            result = social.collect(make_pan(1), self.workdir)
        self.assertTrue(result["ok"])
        self.assertIn("login_wall", result["error"])
        self.assertEqual(social.cooldown(), {}, "登录墙不该写风控冷却")
        self.assertTrue(any(m["platform"] == "weibo" for m in result["materials"]))

    def test_materials_carry_platform_and_ocr(self):
        notes = [{"url": "https://x/1", "text": "小红书正文", "ocr": "A賞 全1种共2个"}]
        with mock.patch.object(social, "search_weibo", return_value=(True, [], "")), mock.patch.object(
            social, "search_xhs", return_value=(True, notes, "")
        ), mock.patch.object(social, "_pause"):
            result = social.collect(make_pan(1), self.workdir)
        self.assertTrue(result["ok"])
        self.assertEqual(result["materials"][0]["platform"], "xhs")
        self.assertIn("全1种共2个", result["materials"][0]["ocr"])


class SocialPanTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workdir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_candidates_are_tagged_social(self):
        collected = {
            "ok": True,
            "error": "",
            "materials": [{"platform": "weibo", "url": "https://m/1", "title": "t", "text": "一番赏 测试盘 全1种共2个"}],
            "elapsed": 1.0,
        }
        extracted = {
            "ok": True,
            "error": "",
            "items": [{"pan": "一番赏 测试盘 1", "prizes": [], "price": {"value": None}}],
            "text": "",
        }
        with mock.patch.object(social, "collect", return_value=collected), mock.patch(
            "acg.backfill_ds._extract", return_value=extracted
        ):
            result = social.social_pan(make_pan(1), self.workdir)
        self.assertTrue(result["ok"])
        self.assertEqual(result["items"][0]["lane"], "social")
        self.assertEqual(result["sources"], 1)

    def test_no_material_is_not_ok(self):
        with mock.patch.object(social, "collect", return_value={"ok": True, "error": "", "materials": []}):
            result = social.social_pan(make_pan(1), self.workdir)
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "no_results")


class SocialLaneTest(unittest.TestCase):
    """接进补齐流程：它是可选通道，挂了不能把整轮变 partial。"""

    def setUp(self):
        self._runs_dir = common.RUNS_DIR
        self.tmp = tempfile.TemporaryDirectory()
        common.RUNS_DIR = Path(self.tmp.name)
        self.runs_dir = Path(self.tmp.name)

    def tearDown(self):
        common.RUNS_DIR = self._runs_dir
        self.tmp.cleanup()

    def _run_backfill(self, pans: int, *, social_pan_result, cooldown=None, available=True):
        pans_payload = [make_pan(i) for i in range(1, pans + 1)]
        subs_payload = [
            {"rid": f"r{i}", "pan_rid": f"p{i}", "kind": "A", "name": "A赏", "qty": None}
            for i in range(1, pans + 1)
        ]
        ds_result = {"items": [], "perPan": {}, "errors": [], "elapsed": 0.0, "sources": 0}
        social_result = {"items": [], "errors": ["x"], "pans": 0, "blocked": "blocked:安全验证", "elapsed": 1.0}
        patches = [
            mock.patch.object(acg_run, "page_renderer", return_value=lambda url: ""),
            mock.patch.object(acg_run.dispatch, "preflight_workbuddy", return_value={"ok": False, "error": "skip", "detail": {}}),
            mock.patch.object(acg_run.dispatch, "preflight_deepseek", return_value={"ok": True, "error": "", "detail": {}}),
            mock.patch("acg.backfill_ds.run_pans", return_value=ds_result),
            mock.patch.object(acg_run, "_run_social_lane", return_value=social_result),
            mock.patch("acg.social.available", return_value=available),
            mock.patch("acg.social.cooldown", return_value=cooldown or {}),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        with mock.patch.object(acg_run.table, "load_pans", return_value=pans_payload), mock.patch.object(
            acg_run.table, "load_subs", return_value=subs_payload
        ):
            run = common.Run("backfill", trigger="test", dry_run=True)
            acg_run.backfill(run, 999, True, False, wait=5, lanes=["deepseek", "social"])
        return run

    def test_social_block_does_not_make_the_run_partial(self):
        run = self._run_backfill(2, social_pan_result=None)
        self.assertEqual(run.state["status"], "done")
        self.assertFalse(run.state["lanes"]["social"]["ok"])
        self.assertTrue(run.state["lanes"]["social"]["optional"])
        self.assertTrue(any("optional_lane_down" in w for w in run.state.get("warnings") or []))

    def test_social_cooldown_is_recorded_and_skipped(self):
        run = self._run_backfill(2, social_pan_result=None, cooldown={"until": "2099-01-01T00:00:00+08:00"})
        self.assertEqual(run.state["status"], "done")
        self.assertIn("cooldown_until", run.state["lanes"]["social"]["error"])


if __name__ == "__main__":
    unittest.main()
