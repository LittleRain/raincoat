"""discover 链路的离线测试：不联网、不派 Agent、不写表。

跑法：python3 -m unittest discover -s apps/acg-capture/engines/scripts/tests -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from acg import accept, browser, discover_ds, feeds, products  # noqa: E402
from acg.common import last_success_date  # noqa: E402
import acg.common as common  # noqa: E402
import acg_run  # noqa: E402

POSTS = [
    {
        "mid": "5365849189518384",
        "created": "Mon Nov 16 12:00:02 +0800 2026",
        "text": "#崩坏：星穹铁道#《崩坏：星穹铁道》× 一番赏 第四弹企划公开！星神阿哈、千冶・刃、知更鸟・晴歌即将加入。",
        "url": "https://m.weibo.cn/detail/5365849189518384",
    },
    {
        "mid": "5364792216257273",
        "created": "Fri Nov 13 14:00:00 +0800 2026",
        "text": "罗小黑战记 第4弹 11月20日正式发售！",
        "url": "https://m.weibo.cn/detail/5364792216257273",
    },
]


class FeedTest(unittest.TestCase):
    def test_url_key_unifies_weibo_forms(self):
        keys = {
            feeds.url_key("https://m.weibo.cn/detail/5365849189518384"),
            feeds.url_key("https://weibo.com/7324393029/5365849189518384"),
            feeds.url_key("https://m.weibo.cn/status/5365849189518384?x=1"),
        }
        self.assertEqual(keys, {"weibo:5365849189518384"})

    def test_url_key_xhs(self):
        self.assertEqual(
            feeds.url_key("https://www.xiaohongshu.com/explore/6af58ac6000000002b0391d8?x=1"),
            "xhs:6af58ac6000000002b0391d8",
        )

    def test_weibo_items_filter_window(self):
        items = feeds.weibo_items("一番赏（大陆）", "微博 万代", POSTS, "2026-11-15", "2026-11-17")
        self.assertEqual([item["id"] for item in items], ["5365849189518384"])
        self.assertEqual(items[0]["date"], "2026-11-16")
        self.assertEqual(items[0]["url"], "https://m.weibo.cn/detail/5365849189518384")

    def test_xhs_items_caps_and_marks_undated(self):
        notes = [{"id": f"n{index}", "url": f"https://www.xiaohongshu.com/explore/{index:024x}", "text": "新品预告"} for index in range(40)]
        items = feeds.xhs_items("KAYOU赏", "小红书 卡游情报", notes, limit=5)
        self.assertEqual(len(items), 5)
        self.assertTrue(all(item["undated"] for item in items))


class VerifyDiscoverTest(unittest.TestCase):
    def setUp(self):
        self.items = feeds.weibo_items("一番赏（大陆）", "微博 万代", POSTS, "2026-11-15", "2026-11-17")
        self.snapshots = feeds.snapshot_index(self.items)
        self.candidate = {
            "brand": "一番赏（大陆）",
            "name": "崩坏：星穹铁道 一番赏 第四弹",
            "source": "https://m.weibo.cn/detail/5365849189518384",
            "quote": "《崩坏：星穹铁道》× 一番赏 第四弹企划公开！",
        }

    def test_accept_from_snapshot(self):
        verdict = accept.verify_discover(self.candidate, set(), {}, self.snapshots)
        self.assertEqual(verdict["status"], "accepted")
        self.assertEqual(verdict["evidence"], "snapshot")

    def test_account_name_source_is_rejected(self):
        verdict = accept.verify_discover({**self.candidate, "source": "微博 万代南梦宫潮玩 uid:7324393029"}, set(), {}, self.snapshots)
        self.assertEqual(verdict["status"], "rejected")
        self.assertEqual(verdict["reasons"], ["source_not_url"])

    def test_duplicate_is_rejected(self):
        verdict = accept.verify_discover(self.candidate, {accept.pan_key(self.candidate["name"], self.candidate["brand"])}, {}, self.snapshots)
        self.assertEqual(verdict["reasons"], ["duplicate"])

    def test_quote_mismatch_is_rejected(self):
        verdict = accept.verify_discover({**self.candidate, "quote": "这句原文里没有的句子超过十个字"}, set(), {}, self.snapshots)
        self.assertEqual(verdict["reasons"], ["quote_mismatch"])

    def test_duplicate_ignores_link_words(self):
        candidate = {**self.candidate, "name": "一番赏 × 忘川风华录 联动", "source": "https://m.weibo.cn/detail/5365866721185799",
                     "quote": "《崩坏：星穹铁道》× 一番赏 第四弹企划公开！"}
        verdict = accept.verify_discover(candidate, {accept.pan_key("一番赏 忘川风华录")}, {}, self.snapshots)
        self.assertEqual(verdict["reasons"], ["duplicate"])

    def test_different_volume_is_not_duplicate(self):
        candidate = {**self.candidate, "name": "一番赏 崩坏：星穹铁道 第四弹"}
        verdict = accept.verify_discover(candidate, {accept.pan_key("一番赏 崩坏：星穹铁道 Vol.3")}, {}, self.snapshots)
        self.assertEqual(verdict["status"], "accepted")

    def test_edition_markers_are_normalized(self):
        self.assertEqual(accept.pan_key("崩坏：星穹铁道 Vol.4", "一番赏"),
                         accept.pan_key("一番赏 崩坏：星穹铁道 第四弹", "一番赏"))
        self.assertNotEqual(accept.pan_key("一番赏 崩坏：星穹铁道 Vol.3", "一番赏"),
                            accept.pan_key("一番赏 崩坏：星穹铁道 第四弹", "一番赏"))

    def test_brand_comes_from_pan_name(self):
        self.assertEqual(accept.derive_brand("一番赏 忘川风华录", "万花赏"), "一番赏")
        self.assertEqual(accept.derive_brand("万花赏 初音未来", "一番赏"), "万花赏")
        self.assertEqual(accept.derive_brand("没写品牌的新盘", "乐淘赏"), "乐淘赏")

    def test_short_page_goes_pending_not_rejected(self):
        from unittest.mock import patch

        candidate = {
            "brand": "KAYOU赏",
            "name": "KAYOU赏 假面骑士 R30 第2弹",
            "source": "https://mp.weixin.qq.com/s/short",
            "quote": "产品名称:假面骑士KAYOU赏-R30-第2弹",
        }
        with patch.object(accept, "_page", return_value=(True, "卡游本周新品速递", "")):
            verdict = accept.verify_discover(candidate, set(), {}, {}, render=lambda url: "")
        self.assertEqual(verdict["status"], "pending_review")
        self.assertEqual(verdict["reasons"], ["render_failed"])

    def test_rendered_long_page_still_rejects_mismatch(self):
        from unittest.mock import patch

        candidate = {
            "brand": "一番赏", "name": "一番赏 某新盘",
            "source": "https://mp.weixin.qq.com/s/long",
            "quote": "这句话在渲染出来的长页面里也不存在至少要十五个字",
        }
        page = "正文" * 1000
        with patch.object(accept, "_page", return_value=(True, page, "")):
            verdict = accept.verify_discover(candidate, set(), {}, {}, render=lambda url: page)
        self.assertEqual(verdict["status"], "rejected")
        self.assertEqual(verdict["reasons"], ["quote_mismatch"])

    def test_wechat_url_skips_urllib(self):
        from unittest.mock import patch

        candidate = {
            "brand": "一番赏（大陆）",
            "name": "一番赏 宝可梦30周年纪念vol.2",
            "source": "https://mp.weixin.qq.com/s/abc",
            "quote": "一番赏 宝可梦30周年纪念vol.2\n\n9月30日0点开售",
        }
        page = "新品预告丨五大地区初始伙伴集结\n\n" + candidate["quote"] + "\n\n" + "正文" * 500
        with patch.object(accept, "_page") as page_mock:
            verdict = accept.verify_discover(candidate, set(), {}, {}, render=lambda url: page)
        page_mock.assert_not_called()
        self.assertEqual(verdict["status"], "accepted")
        self.assertEqual(verdict["evidence"], "rendered")

    def test_display_name_adds_brand_prefix(self):
        self.assertEqual(accept.display_name("崩坏：星穹铁道 Vol.4", "一番赏"), "一番赏 崩坏：星穹铁道 Vol.4")
        self.assertEqual(accept.display_name("一番赏 攻壳机动队", "一番赏"), "一番赏 攻壳机动队")
        self.assertEqual(accept.display_name("假面骑士 KAYOU赏 R30", "KAYOU赏"), "假面骑士 KAYOU赏 R30")

    def test_render_fallback_accepts_js_shell(self):
        from unittest.mock import patch

        candidate = {
            "brand": "一番赏（大陆）",
            "name": "一番赏 攻壳机动队",
            "source": "https://mp.weixin.qq.com/s/abc",
            "quote": "「一番赏 攻壳机动队」首次引进11月20日登陆开售",
        }
        with patch.object(accept, "_page", return_value=(True, "<html>JS 壳</html>", "")):
            verdict = accept.verify_discover(candidate, set(), {}, {}, render=lambda url: candidate["quote"])
        self.assertEqual(verdict["status"], "accepted")
        self.assertEqual(verdict["evidence"], "rendered")

    def test_short_quote_goes_pending(self):
        verdict = accept.verify_discover({**self.candidate, "quote": "一番赏"}, set(), {}, self.snapshots)
        self.assertEqual(verdict["status"], "pending_review")
        self.assertEqual(verdict["reasons"], ["quote_too_short"])


class AnchorTest(unittest.TestCase):
    """窗口锚点：超时空跑不能推进，Agent 真回答过才算。"""

    def _run(self, root: Path, name: str, payload: dict) -> None:
        directory = root / name
        directory.mkdir(parents=True)
        (directory / "run.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_timeout_run_does_not_advance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._run(root, "r-20261117-110926-discover", {
                "kind": "discover", "status": "done", "startedAt": "2026-11-17T11:09:26+08:00",
                "counts": {"accepted": 0},
            })
            original = common.RUNS_DIR
            common.RUNS_DIR = root
            try:
                self.assertIsNone(last_success_date("discover"))
            finally:
                common.RUNS_DIR = original

    def test_answered_run_advances(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._run(root, "r-20261118-090000-discover", {
                "kind": "discover", "status": "done", "startedAt": "2026-11-18T09:00:00+08:00",
                "counts": {"accepted": 0}, "answer": {"groups": 3, "answered": 3, "timeouts": 0},
            })
            original = common.RUNS_DIR
            common.RUNS_DIR = root
            try:
                self.assertEqual(last_success_date("discover"), "2026-11-18")
            finally:
                common.RUNS_DIR = original

    def test_partial_run_does_not_advance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._run(root, "r-20261118-090000-discover", {
                "kind": "discover", "status": "partial", "startedAt": "2026-11-18T09:00:00+08:00",
                "counts": {"accepted": 1}, "answer": {"groups": 3, "answered": 1, "timeouts": 2},
            })
            original = common.RUNS_DIR
            common.RUNS_DIR = root
            try:
                self.assertIsNone(last_success_date("discover"))
            finally:
                common.RUNS_DIR = original


class ProductTypeTest(unittest.TestCase):
    """2026-11-17 用户口径：卡游抽卡机的收藏卡 / 典藏包算赏盘；没确认过的类型停下来问人。"""

    def test_confirmed_card_products_pass(self):
        self.assertEqual(products.classify("英雄赏 欧欧TD收藏卡 Y2K系列"), "ok")
        self.assertEqual(products.classify("英雄赏 魔法少女小圆 圆理的序曲 典藏包 15周年纪念特辑"), "ok")

    def test_unknown_adjacent_type_needs_confirmation(self):
        self.assertEqual(products.classify("英雄赏 某IP 盲盒 第1弹"), "confirm")
        self.assertEqual(products.classify("某赏 X 手办 第一弹"), "confirm")

    def test_plain_pan_still_passes(self):
        self.assertEqual(products.classify("一番赏 咒术回战 第5弹", "一抽80元，全套70抽"), "ok")


class QuoteSpecificTest(unittest.TestCase):
    def test_generic_boilerplate_quote_goes_pending(self):
        page = "磁力赏 GON的旱獭\n本信息为发售前的店铺汇总信息。个别店铺发售情况有可能发生变更。"
        verdict = accept.verify_discover(
            {
                "brand": "磁力赏",
                "name": "磁力赏 GON的旱獭",
                "source": "https://mall.bilibili.com/act/aicms/x.html",
                "quote": "本信息为发售前的店铺汇总信息。个别店铺发售情况有可能发生变更。",
            },
            set(), {"https://mall.bilibili.com/act/aicms/x.html": (True, page, "")}, {},
        )
        self.assertEqual(verdict["status"], "pending_review")
        self.assertIn("quote_not_specific", verdict["reasons"])

    def test_name_in_quote_is_accepted(self):
        page = "好物赏 王者荣耀「峡影逐风」系列 11月20日开售"
        verdict = accept.verify_discover(
            {
                "brand": "好物赏",
                "name": "好物赏 王者荣耀「峡影逐风」系列",
                "source": "https://m.weibo.cn/detail/5367042045379649",
                "quote": "好物赏 王者荣耀「峡影逐风」系列 11月20日开售",
            },
            set(), {"https://m.weibo.cn/detail/5367042045379649": (True, page, "")}, {},
        )
        self.assertEqual(verdict["status"], "accepted")

    def test_jp_only_name_from_jp_site_goes_pending(self):
        page = "一番くじ To LOVEる 11月18日発売 1回980円"
        verdict = accept.verify_discover(
            {
                "brand": "一番赏",
                "name": "一番くじ To LOVEる-とらぶる-ダークネス",
                "source": "https://hobby.watch.impress.co.jp/docs/news/1.html",
                "quote": page,
            },
            set(), {"https://hobby.watch.impress.co.jp/docs/news/1.html": (True, page, "")}, {},
        )
        self.assertEqual(verdict["status"], "pending_review")
        self.assertIn("scope_jp", verdict["reasons"])


class BrandDeriveTest(unittest.TestCase):
    def test_trailing_brand_word_wins(self):
        self.assertEqual(accept.derive_brand("《王者荣耀》峡影逐风系列好物赏"), "好物赏")
        self.assertEqual(accept.derive_brand("一番赏 崩坏：星穹铁道 Vol.4"), "一番赏")


class WeiboUidTest(unittest.TestCase):
    def test_uid_from_account_url(self):
        self.assertEqual(acg_run._weibo_uid("https://m.weibo.cn/u/7324393029"), "7324393029")
        self.assertEqual(acg_run._weibo_uid("uid:7801772899"), "7801772899")

    def test_uid_from_post_url(self):
        self.assertEqual(acg_run._weibo_uid("https://m.weibo.cn/detail/5367042045379649"), "5367042045379649")

    def test_uid_missing(self):
        self.assertEqual(acg_run._weibo_uid("https://m.weibo.cn/"), "")


class DsCandidateTest(unittest.TestCase):
    def test_parse_items_drops_secondhand_and_short_quote(self):
        text = json.dumps([
            {"brand": "一番赏", "name": "一番赏 攻壳机动队", "source": "https://m.weibo.cn/detail/1", "quote": "一番赏 攻壳机动队 11月20日正式发售"},
            {"brand": "一番赏", "name": "一番赏 闲鱼盘", "source": "https://www.goofish.com/item/1", "quote": "一番赏 攻壳机动队 11月20日正式发售"},
            {"brand": "一番赏", "name": "一番赏 太短", "source": "https://m.weibo.cn/detail/2", "quote": "太短"},
        ])
        items = discover_ds.parse_items(text)
        self.assertEqual([row["name"] for row in items], ["一番赏 攻壳机动队"])
        self.assertEqual(items[0]["lane"], "deepseek")

    def test_parse_items_tolerates_fence(self):
        text = "```json\n[{\"name\":\"一番赏 X\",\"source\":\"https://a.com/1\",\"quote\":\"一番赏 X 本月上新公告\"}]\n```"
        items = discover_ds.parse_items(text)
        self.assertEqual(len(items), 1)


class BrowserGateTest(unittest.TestCase):
    def test_missing_ego_is_reported_not_raised(self):
        original = browser.EGO
        browser.EGO = None
        try:
            self.assertFalse(browser.available())
        finally:
            browser.EGO = original


if __name__ == "__main__":
    unittest.main()
