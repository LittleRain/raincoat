"""游戏虚拟商品离线测试：不联网、不写表、不派 Agent。

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

from acg import vg_accept, vg_channels, vg_store, vg_table  # noqa: E402

PAGE = (
    "<html><body><h1>创世结晶 充值</h1>"
    "<p>创世结晶 60 6元；创世结晶 300 30元；创世结晶 6480 648元</p>"
    "<p>空月祝福 30元，有效期 30 天；纪行 68元/128元</p>"
    "<p>首充双倍，每账号1次</p></body></html>"
)

GAME = {
    "id": "game-genshin",
    "game": "原神",
    "publisher": "米哈游",
    "status": "active",
    "priority": "P0",
    "currency": "创世结晶",
    "skuHints": ["空月祝福", "纪行"],
    "channelIds": ["mihoyo-site"],
}

CHANNELS = [
    {
        "id": "mihoyo-site",
        "publisher": "米哈游",
        "channel": "米哈游官网",
        "type": "official-site",
        "tier": "A",
        "url": "https://www.mihoyo.com/",
        "gameScope": ["原神"],
        "canAnswer": ["name", "price", "denom"],
        "status": "confirmed",
        "lastVerified": "2026-11-17",
        "note": "",
    },
    {
        "id": "appstore-cn",
        "publisher": "应用商店",
        "channel": "App Store 中国区应用页",
        "type": "appstore",
        "tier": "C",
        "url": "https://apps.apple.com/cn/",
        "gameScope": [],
        "canAnswer": ["name", "price", "denom"],
        "status": "confirmed",
        "lastVerified": "2026-11-17",
        "note": "",
    },
]


def candidate(**overrides) -> dict:
    base = {
        "game": "原神",
        "type": "充值代币",
        "name": "创世结晶",
        "denom": "60",
        "price": 6,
        "duration": "",
        "limit": "",
        "quote": "创世结晶 60 6元",
        "source": "https://www.mihoyo.com/recharge",
        "lane": "workbuddy",
    }
    base.update(overrides)
    return base


def normalize(**overrides) -> dict:
    return vg_accept.normalize_candidate(candidate(**overrides), GAME, str(overrides.get("lane") or "workbuddy"))


class TestNormalize(unittest.TestCase):
    def test_type_mapping(self):
        self.assertEqual(normalize(type="充值代币")["type"], "token")
        self.assertEqual(normalize(type="月卡")["type"], "monthly")
        self.assertEqual(normalize(type="通行证")["type"], "pass")
        self.assertEqual(normalize(type="战令")["type"], "pass")
        self.assertEqual(normalize(type="看不懂")["type"], "other")

    def test_denom_falls_back_to_duration(self):
        row = normalize(denom="", duration="30天", name="空月祝福", type="月卡")
        self.assertEqual(row["denom"], "30天")

    def test_price_parsing(self):
        self.assertEqual(normalize(price="6元")["price"], 6.0)
        self.assertIsNone(normalize(price="")["price"])
        self.assertIsNone(normalize(price=0)["price"])


class TestVerify(unittest.TestCase):
    def setUp(self):
        self._page = vg_accept._page
        self._contains = vg_accept._contains
        vg_accept._page = lambda cache, url: (True, PAGE, "")
        vg_accept._contains = lambda cache, url, quote: (True, "")

    def tearDown(self):
        vg_accept._page = self._page
        vg_accept._contains = self._contains

    def test_official_page_accepted(self):
        record = vg_accept.verify(normalize(), GAME, CHANNELS, {})
        self.assertEqual(record["status"], "accepted", record["reasons"])
        self.assertEqual(record["confidence"], 0.95)
        self.assertIn("1 元=10 币", record["note"])

    def test_missing_price_pending(self):
        record = vg_accept.verify(normalize(price=None, quote="创世结晶 60"), GAME, CHANNELS, {})
        self.assertEqual(record["status"], "pending_review")
        self.assertIn("price_missing", record["reasons"])

    def test_name_mismatch_pending(self):
        record = vg_accept.verify(normalize(name="原石礼包", denom="60", quote="创世结晶 60 6元"), GAME, CHANNELS, {})
        self.assertEqual(record["status"], "pending_review")
        self.assertIn("name_mismatch", record["reasons"])

    def test_secondhand_rejected(self):
        record = vg_accept.verify(
            normalize(source="https://www.xianyu.com/item/1", quote="创世结晶 60 6元"), GAME, CHANNELS, {}
        )
        self.assertEqual(record["status"], "rejected")
        self.assertIn("secondhand_forbidden", record["reasons"])

    def test_unknown_host_pending(self):
        record = vg_accept.verify(
            normalize(source="https://example.com/recharge", quote="创世结晶 60 6元"), GAME, CHANNELS, {}
        )
        self.assertEqual(record["status"], "pending_review")
        self.assertIn("channel_unverified", record["reasons"])

    def test_deepseek_non_official_rejected(self):
        record = vg_accept.verify(
            normalize(source="https://www.9game.cn/yiren/1.html", lane="deepseek"),
            GAME,
            CHANNELS,
            {},
        )
        self.assertEqual(record["status"], "rejected")
        self.assertIn("deepseek_non_official", record["reasons"])

    def test_workbuddy_non_official_pending(self):
        record = vg_accept.verify(
            normalize(source="https://www.9game.cn/yiren/1.html", lane="workbuddy"),
            GAME,
            CHANNELS,
            {},
        )
        self.assertEqual(record["status"], "pending_review")
        self.assertIn("channel_unverified", record["reasons"])

    def test_appstore_single_lane_pending(self):
        record = vg_accept.verify(
            normalize(source="https://apps.apple.com/cn/app/id123", lane="workbuddy"), GAME, CHANNELS, {}
        )
        self.assertEqual(record["status"], "pending_review")
        self.assertIn("c_tier_single_lane", record["reasons"])
        both = vg_accept.verify(
            normalize(source="https://apps.apple.com/cn/app/id123", lane="both"), GAME, CHANNELS, {}
        )
        self.assertEqual(both["status"], "accepted", both["reasons"])

    def test_ratio_conflict_pending(self):
        record = vg_accept.verify(normalize(denom="6", price=60, quote="创世结晶 6 60元"), GAME, CHANNELS, {})
        self.assertEqual(record["status"], "pending_review")
        self.assertIn("ratio_conflict", record["reasons"])

    def test_quote_without_denom_pending(self):
        record = vg_accept.verify(
            normalize(denom="980", price=98, quote="创世结晶 98元 限时"), GAME, CHANNELS, {}
        )
        self.assertEqual(record["status"], "pending_review")
        self.assertIn("denom_missing", record["reasons"])


class TestStoreParse(unittest.TestCase):
    STORE_PAGE = (
        "<html><body><p>App内购买 是 祝福礼包 ¥30.00 6480创世结晶 ¥648.00 珍珠纪行 ¥68.00 "
        "60创世结晶 ¥6.00 300创世结晶 ¥30.00 进一步了解 提供者 上海米哈游影铁科技有限公司</p></body></html>"
    )

    def test_parse_tokens_and_skus(self):
        game = {"game": "原神", "currency": "创世结晶"}
        items = vg_store.parse_items(game, "https://apps.apple.com/cn/app/id1", self.STORE_PAGE)
        by_name = {(row["name"], row["denom"]): row for row in items}
        self.assertIn(("创世结晶", "60"), by_name)
        self.assertEqual(by_name[("创世结晶", "60")]["price"], 6.0)
        self.assertEqual(by_name[("创世结晶", "60")]["type"], "token")
        self.assertEqual(by_name[("祝福礼包", "")]["type"], "monthly")
        self.assertEqual(by_name[("珍珠纪行", "")]["type"], "pass")
        self.assertTrue(all(row["lane"] == "store" for row in items))

    def test_currency_without_config_is_normalized(self):
        page = "<html>App内购买 是 1980枚龙晶 ¥198.00 980枚龙晶 ¥98.00 进一步了解</html>"
        items = vg_store.parse_items({"game": "斗罗大陆", "currency": ""}, "https://apps.apple.com/cn/app/id2", page)
        by_name = {(row["name"], row["denom"]): row for row in items}
        self.assertIn(("龙晶", "1980"), by_name)
        self.assertEqual(by_name[("龙晶", "1980")]["type"], "token")
        self.assertEqual(by_name[("龙晶", "1980")]["price"], 198.0)

    def test_no_marker_returns_empty(self):
        self.assertEqual(vg_store.parse_items({"game": "x", "currency": "y"}, "https://a", "<html>no</html>"), [])

    def test_pack_name_without_denom_is_bundle(self):
        page = "<html>App内购买 是 开采一箱源石 ¥648.00 进一步了解</html>"
        items = vg_store.parse_items({"game": "明日方舟", "currency": "源石"}, "https://apps.apple.com/cn/app/id2", page)
        self.assertEqual(items[0]["type"], "bundle")
        self.assertEqual(items[0]["denom"], "")


class TestResolveAppStore(unittest.TestCase):
    def _patch(self, payload):
        original = vg_store.fetch_text
        vg_store.fetch_text = lambda url, timeout=15, retries=2: (True, json.dumps(payload), "")
        self.addCleanup(lambda: setattr(vg_store, "fetch_text", original))

    def test_exact_match_only(self):
        self._patch(
            {
                "results": [
                    {"trackId": 1, "trackName": "SpireSage: 杀戮尖塔2", "sellerName": "someone"},
                    {"trackId": 2, "trackName": "杀戮尖塔", "sellerName": "Humble"},
                ]
            }
        )
        self.assertEqual(vg_store.resolve_app_store("杀戮尖塔"), "https://apps.apple.com/cn/app/id2")

    def test_rejects_guide_apps_and_cloud(self):
        self._patch(
            {
                "results": [
                    {"trackId": 3, "trackName": "原神图鉴", "sellerName": "fan"},
                    {"trackId": 4, "trackName": "云·原神", "sellerName": "mihoyo"},
                ]
            }
        )
        self.assertEqual(vg_store.resolve_app_store("原神"), "")

    def test_no_results(self):
        self._patch({"results": []})
        self.assertEqual(vg_store.resolve_app_store("塞尔达传说系列"), "")


class TestOpenPolicy(unittest.TestCase):
    """不卡渠道的口径：渠道不认识也采信，但价格仍必须在来源页上。"""

    def setUp(self):
        self._page = vg_accept._page
        self._contains = vg_accept._contains

    def tearDown(self):
        vg_accept._page = self._page
        vg_accept._contains = self._contains

    def test_unknown_channel_accepted_when_quote_hits(self):
        vg_accept._page = lambda cache, url: (True, PAGE, "")
        vg_accept._contains = lambda cache, url, quote: (True, "")
        record = vg_accept.verify(normalize(source="https://www.158card.com/x"), GAME, CHANNELS, {}, policy="open")
        self.assertEqual(record["status"], "accepted", record["reasons"])
        self.assertEqual(record["sourceTier"], "third_party")

    def test_strict_policy_still_pends(self):
        vg_accept._page = lambda cache, url: (True, PAGE, "")
        vg_accept._contains = lambda cache, url, quote: (True, "")
        record = vg_accept.verify(normalize(source="https://www.158card.com/x"), GAME, CHANNELS, {})
        self.assertEqual(record["status"], "pending_review")
        self.assertIn("channel_unverified", record["reasons"])

    def test_snippet_quote_falls_back_to_page_evidence(self):
        # quote 是搜索摘要、页面里没有原句；但页面同时有商品名和价格 → 采信并留痕
        vg_accept._page = lambda cache, url: (True, "创世结晶 充值档位 60 档 6 元 648 档 648 元", "")
        vg_accept._contains = lambda cache, url, quote: (False, "mismatch")
        record = vg_accept.verify(
            normalize(source="https://www.9game.cn/x", quote="创世结晶60档只要6元"), GAME, CHANNELS, {}, policy="open"
        )
        self.assertEqual(record["status"], "accepted", record["reasons"])
        self.assertEqual(record["evidence"], "page_name_price")

    def test_page_without_price_still_pends(self):
        vg_accept._page = lambda cache, url: (True, "创世结晶 充值档位 请前往游戏内查看", "")
        vg_accept._contains = lambda cache, url, quote: (False, "mismatch")
        record = vg_accept.verify(
            normalize(source="https://www.9game.cn/x", quote="创世结晶60档只要6元"), GAME, CHANNELS, {}, policy="open"
        )
        self.assertEqual(record["status"], "pending_review")
        self.assertIn("quote_unverified", record["reasons"])


class TestWorkbuddyBatches(unittest.TestCase):
    """批间并行 + 超时后二次读终态：批量派发不能丢已经跑出来的结果。"""

    def setUp(self):
        from acg import vg_discover
        from acg.common import Run

        self.vg_discover = vg_discover
        self.run = Run("vg-discover-test", trigger="test", dry_run=True)
        self.addCleanup(lambda: self.run.dir.exists() and __import__("shutil").rmtree(self.run.dir, ignore_errors=True))

    def _patch(self, texts, status="succeeded"):
        calls = []

        def fake_submit(prompt, title, workdir):
            calls.append(title)
            return {"jobId": f"job{len(calls)}", "resultPath": f"/tmp/{len(calls)}", "model": "m"}

        def fake_wait(path, timeout=600, interval=5, on_tick=None):
            if timeout <= 1:  # 超时后的二次读
                return {"status": status, "text": texts.get(int(str(path).split("/")[-1]), "")}
            return {"status": "timeout", "text": ""}

        original_submit, original_wait = self.vg_discover.vg_dispatch.submit, self.vg_discover.dispatch.wait_job
        self.vg_discover.vg_dispatch.submit = fake_submit
        self.vg_discover.dispatch.wait_job = fake_wait
        self.addCleanup(lambda: (setattr(self.vg_discover.vg_dispatch, "submit", original_submit),
                                 setattr(self.vg_discover.dispatch, "wait_job", original_wait)))
        return calls

    def test_parallel_batches_collect_every_batch(self):
        payload = '[{"game":"A","type":"月卡","name":"x","price":1,"quote":"q","source":"https://a.com"}]'
        calls = self._patch({1: payload, 2: payload, 3: payload})
        games = [{"game": f"G{i}"} for i in range(7)]
        batches = [games[0:3], games[3:5], games[5:7]]
        candidates, errors = self.vg_discover._workbuddy_batches(
            self.run, batches, [], "2026-09-01", "2026-10-01", timeout=60, parallel=3
        )
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(errors, [])
        self.assertTrue(all(row["lane"] == "workbuddy" for row in candidates))

    def test_timeout_keeps_late_text(self):
        payload = '[{"game":"A","type":"月卡","name":"x","price":1,"quote":"q","source":"https://a.com"}]'
        self._patch({1: payload})
        candidates, errors = self.vg_discover._workbuddy_batches(
            self.run, [[{"game": "G0"}]], [], "2026-09-01", "2026-10-01", timeout=60, parallel=1
        )
        self.assertEqual(len(candidates), 1)


class TestProductGranularity(unittest.TestCase):
    """一个币种一行：不同档位只是面额不同，商品名里不许留面额。"""

    def test_denom_stripped_from_name(self):
        self.assertEqual(vg_table.canonical_product("980创世结晶"), ("创世结晶", "980"))
        self.assertEqual(vg_table.canonical_product("6480创世结晶"), ("创世结晶", "6480"))

    def test_thousand_separator_and_multi_suffix(self):
        self.assertEqual(vg_table.canonical_product("3,150元宝"), ("元宝", "3150"))
        self.assertEqual(vg_table.canonical_product("63,500元宝"), ("元宝", "63500"))
        self.assertEqual(vg_table.canonical_product("点券x60"), ("点券", "60"))

    def test_gift_parenthetical_is_not_denom(self):
        self.assertEqual(vg_table.canonical_product("6800NZ点（赠送288NZ点）"), ("NZ点", "6800"))

    def test_unit_marked_currency_without_hint_char(self):
        self.assertEqual(vg_table.canonical_product("980枚古老梦华"), ("古老梦华", "980"))

    def test_bundles_keep_their_names(self):
        for name in ("3星必得招募礼包", "10包经典卡牌包和1张经典传说卡牌", "2026烽火赛事补给①"):
            self.assertEqual(vg_table.canonical_product(name), (name, ""), name)

    def test_price_in_name_is_not_denom(self):
        self.assertEqual(vg_table.canonical_product("30元月卡"), ("月卡", ""))
        self.assertEqual(vg_table.canonical_product("18元日礼包"), ("日礼包", ""))


class TestMerge(unittest.TestCase):
    def test_both_lanes_merge(self):
        wb = vg_accept.normalize_candidate(candidate(lane="workbuddy"), GAME, "workbuddy")
        ds = vg_accept.normalize_candidate(candidate(lane="deepseek"), GAME, "deepseek")
        merged = vg_accept.merge([wb, ds])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["lane"], "both")

    def test_different_denom_kept_apart(self):
        wb = vg_accept.normalize_candidate(candidate(denom="60", price=6), GAME, "workbuddy")
        ds = vg_accept.normalize_candidate(candidate(denom="300", price=30), GAME, "deepseek")
        self.assertEqual(len(vg_accept.merge([wb, ds])), 2)

    def test_key_normalizes(self):
        a = vg_accept.normalize_candidate(candidate(game="原神 "), GAME, "workbuddy")
        b = vg_accept.normalize_candidate(candidate(game="原神"), GAME, "deepseek")
        self.assertEqual(vg_accept.key_of(a), vg_accept.key_of(b))


class TestNewGameFilter(unittest.TestCase):
    THRESHOLDS = {"maxNewPerRun": 2, "minReservation": 100000, "chartTop": 50, "publishers": ["米哈游"]}

    def test_known_game_still_reported(self):
        kept, _ = vg_accept.filter_new_games(
            [
                {"game": "原神", "publisher": "米哈游", "status": "已上线", "monetization": "代币", "source": "https://www.mihoyo.com/"},
            ],
            ["原神"],
            self.THRESHOLDS,
        )
        self.assertEqual(len(kept), 1)

    def test_threshold_gate(self):
        kept, dropped = vg_accept.filter_new_games(
            [
                {
                    "game": "某小厂新游",
                    "publisher": "某小厂",
                    "status": "已上线",
                    "monetization": "月卡",
                    "source": "https://example.com/game",
                }
            ],
            [],
            self.THRESHOLDS,
        )
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0]["reason"], "threshold_missed")

    def test_heat_hits(self):
        rows = [
            {
                "game": "榜单新游",
                "publisher": "小厂",
                "status": "预约",
                "monetization": "代币",
                "chart": "畅销榜第 12 名",
                "source": "https://example.com/a",
            },
            {
                "game": "预约新游",
                "publisher": "小厂",
                "status": "预约",
                "monetization": "月卡",
                "reservation": 250000,
                "source": "https://example.com/c",
            },
        ]
        kept, dropped = vg_accept.filter_new_games(rows, [], {**self.THRESHOLDS, "maxNewPerRun": 10})
        self.assertEqual(dropped, [])
        heat = {row["game"]: row["heat"] for row in kept}
        self.assertIn("榜单第 12", heat["榜单新游"])
        self.assertIn("预约 250000", heat["预约新游"])

    def test_app_store_page_is_not_heat(self):
        kept, dropped = vg_accept.filter_new_games(
            [
                {
                    "game": "小制作新游",
                    "publisher": "小厂",
                    "status": "已上线",
                    "monetization": "月卡",
                    "appStore": "https://apps.apple.com/cn/app/id1234567890",
                    "source": "https://example.com/b",
                }
            ],
            [],
            self.THRESHOLDS,
        )
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0]["reason"], "threshold_missed")

    def test_app_store_normalized(self):
        row = {"game": "链新游", "source": "https://apps.apple.com/cn/app/xing-tie/id1523037824?see=all"}
        self.assertEqual(vg_accept.app_store_url(row), "https://apps.apple.com/cn/app/id1523037824")

    def test_license_alone_is_not_heat(self):
        kept, dropped = vg_accept.filter_new_games(
            [
                {
                    "game": "有版号新游",
                    "publisher": "小厂",
                    "status": "预约",
                    "monetization": "通行证",
                    "license": "国新出审〔2026〕123 号",
                    "source": "https://www.nppa.gov.cn/x",
                }
            ],
            [],
            self.THRESHOLDS,
        )
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0]["reason"], "threshold_missed")

    def test_publisher_alias_matches_legal_name(self):
        kept, dropped = vg_accept.filter_new_games(
            [
                {
                    "game": "明日方舟：终末地",
                    "publisher": "上海鹰角开拓者网络科技有限公司",
                    "status": "已上线",
                    "monetization": "代币+月卡",
                    "source": "https://endfield.hypergryph.com/news/2675",
                }
            ],
            [],
            {**self.THRESHOLDS, "publishers": ["鹰角"]},
        )
        self.assertEqual(dropped, [])
        self.assertEqual(kept[0]["heat"], ["发行商名单"])

    def test_empty_publisher_is_not_heat(self):
        kept, dropped = vg_accept.filter_new_games(
            [
                {
                    "game": "倚天2：觉醒",
                    "publisher": "",
                    "status": "已上线",
                    "monetization": "充值",
                    "source": "https://news.17173.com/x",
                }
            ],
            [],
            self.THRESHOLDS,
        )
        self.assertEqual(kept, [])
        self.assertEqual(dropped[0]["reason"], "threshold_missed")

    def test_publisher_gate_and_cap(self):
        rows = [
            {"game": f"米哈游新游{i}", "publisher": "米哈游", "status": "已上线", "monetization": "代币+月卡", "source": f"https://www.mihoyo.com/g{i}"}
            for i in range(3)
        ]
        kept, dropped = vg_accept.filter_new_games(rows, [], self.THRESHOLDS)
        self.assertEqual(len(kept), 2)
        self.assertEqual(kept[0]["priority"], "P0")
        self.assertEqual([row["reason"] for row in dropped].count("over_limit"), 1)


class TestChannels(unittest.TestCase):
    def test_usable(self):
        self.assertTrue(vg_channels.usable({"status": "confirmed", "tier": "A"}))
        self.assertTrue(vg_channels.usable({"status": "confirmed", "tier": "C"}))
        self.assertFalse(vg_channels.usable({"status": "confirmed", "tier": "D"}))
        self.assertFalse(vg_channels.usable({"status": "pending", "tier": "A"}))

    def test_upsert_validates(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "vg-sources.json"
            row = vg_channels.upsert(
                {"id": "site-a", "publisher": "甲", "channel": "官网", "type": "official-site", "tier": "A", "url": "https://a.example.com/", "status": "confirmed"},
                path,
            )
            self.assertEqual(row["tier"], "A")
            with self.assertRaises(ValueError):
                vg_channels.upsert({"id": "bad", "publisher": "甲", "channel": "x", "tier": "Z"}, path)


class TestCanonicalProduct(unittest.TestCase):
    def test_currency_names(self):
        self.assertEqual(vg_table.canonical_product("充值1980枚龙晶"), ("龙晶", "1980"))
        self.assertEqual(vg_table.canonical_product("980枚古老梦华"), ("古老梦华", "980"))
        self.assertEqual(vg_table.canonical_product("充值60点券"), ("点券", "60"))
        self.assertEqual(vg_table.canonical_product("6480创世结晶"), ("创世结晶", "6480"))

    def test_non_currency_kept(self):
        self.assertEqual(vg_table.canonical_product("空月祝福"), ("空月祝福", ""))
        self.assertEqual(vg_table.canonical_product("充值馈礼豪华档"), ("充值馈礼豪华档", ""))
        self.assertEqual(vg_table.canonical_product("特惠礼包"), ("特惠礼包", ""))
        self.assertEqual(vg_table.canonical_product("珍珠纪行"), ("珍珠纪行", ""))

    def test_normalize_candidate_uses_canonical(self):
        cand = vg_accept.normalize_candidate(
            {"game": "斗罗大陆", "type": "礼包", "name": "充值1980枚龙晶", "price": 198,
             "quote": "充值1980枚龙晶 198元", "source": "https://apps.apple.com/cn/app/id1"},
            {"game": "斗罗大陆", "publisher": "", "currency": "", "skuHints": []},
            "store",
        )
        self.assertEqual(cand["name"], "龙晶")
        self.assertEqual(cand["denom"], "1980")
        self.assertEqual(cand["type"], "token")


class TestLedgerDerived(unittest.TestCase):
    ITEMS = [
        {"game": "原神", "type": "充值代币", "name": "创世结晶 60", "channel": "App Store", "capturedAt": "2026-11-17"},
        {"game": "原神", "type": "月卡", "name": "空月祝福", "channel": "App Store", "capturedAt": "2026-11-17"},
        {"game": "崩坏：星穹铁道", "type": "充值代币", "name": "古老梦华 60", "channel": "米哈游官网", "capturedAt": "2026-11-18"},
        {"game": "", "type": "其他", "name": "脏数据", "channel": "", "capturedAt": ""},
    ]

    def test_known_games_dedupes(self):
        self.assertEqual(vg_table.known_games(self.ITEMS), ["原神", "崩坏：星穹铁道"])

    def test_games_from_items(self):
        games = vg_table.games_from_items(self.ITEMS)
        self.assertEqual([row["game"] for row in games], ["原神", "崩坏：星穹铁道"])
        genshin = games[0]
        self.assertEqual(genshin["count"], 2)
        self.assertEqual(genshin["types"], {"充值代币": 1, "月卡": 1})
        self.assertEqual(genshin["capturedAt"], "2026-11-17")
        self.assertEqual(genshin["missing"], ["通行证"])
        self.assertEqual(genshin["channels"], ["App Store"])


class TestItemValues(unittest.TestCase):
    def test_price_goes_into_note(self):
        item = {
            "game": "原神",
            "type": "token",
            "name": "创世结晶",
            "denom": "60",
            "price": 6,
            "channel": "App Store 中国区（内购项目）",
            "source": "https://www.mihoyo.com/x",
            "quote": "创世结晶 60 6元",
            "status": "on_sale",
            "checkedAt": "2026-11-17T10:00:00+08:00",
            "note": "约 1 元=10 币",
        }
        values = vg_table.item_values(item)
        self.assertNotIn("官方价", values)
        note = json.loads(values["备注"])[0]["text"]
        self.assertIn("60 档 6 元（App Store）", note)
        self.assertIn("约 1 元=10 币", note)
        self.assertNotIn("档位", values)

    def test_note_with_price_keeps_channels(self):
        base = vg_table.note_with_price({"price": 6, "channel": "App Store"}, "")
        same = vg_table.note_with_price({"price": 6.0, "channel": "App Store"}, base)
        self.assertEqual(base, same)
        merged = vg_table.note_with_price({"price": 6.0, "channel": "米哈游官网"}, base)
        self.assertIn("6 元（App Store）", merged)
        self.assertIn("6 元（米哈游官网）", merged)
        other = vg_table.note_with_price({"price": 6.5, "channel": "米哈游官网"}, base)
        self.assertIn("6.5 元（米哈游官网）", other)

    def test_combine_products_merges_prices(self):
        base = {
            "game": "原神", "type": "token", "name": "创世结晶", "channel": "App Store",
            "status": "accepted", "reasons": [], "quote": "创世结晶 60 6元",
            "source": "https://apps.apple.com/cn/app/id1", "note": "约 1 元=10 币",
        }
        rows = [
            {**base, "denom": "60", "price": 6},
            {**base, "denom": "6480", "price": 648, "quote": "创世结晶 6480 648元"},
        ]
        merged = vg_accept.combine_products(rows)
        self.assertEqual(len(merged), 1)
        self.assertEqual(len(merged[0]["prices"]), 2)
        self.assertEqual(merged[0]["status"], "accepted")
        note = vg_table.note_with_price(merged[0], merged[0].get("note") or "")
        self.assertIn("60 档 6 元（App Store）", note)
        self.assertIn("6480 档 648 元（App Store）", note)

    def test_columns_have_no_price_field(self):
        titles = [column["title"] for column in vg_table.COLUMNS]
        self.assertNotIn("官方价", titles)
        self.assertNotIn("上次核验", titles)
        self.assertNotIn("档位", titles)
        self.assertIn("入库日期", titles)
        self.assertEqual(len(titles), 9)

    def test_maps_internal_codes_to_labels(self):
        values = vg_table.item_values(
            {
                "game": "原神",
                "type": "token",
                "name": "创世结晶",
                "denom": "60",
                "price": 6,
                "channel": "米哈游官网",
                "source": "https://www.mihoyo.com/x",
                "quote": "创世结晶 60 6元",
                "status": "on_sale",
                "checkedAt": "2026-11-17T10:00:00+08:00",
                "note": "首充双倍",
            }
        )
        self.assertEqual(json.loads(values["游戏"])[0]["text"], "原神")
        self.assertEqual(values["商品类型"][0]["text"], "充值代币")
        self.assertNotIn("官方价", values)
        self.assertNotIn("档位", values)
        self.assertEqual(values["入库日期"], "2026-11-17")


if __name__ == "__main__":
    unittest.main()
