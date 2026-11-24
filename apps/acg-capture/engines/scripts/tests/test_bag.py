"""官方福袋离线测试：不联网、不写表、不派 Agent。

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

from acg import bag_accept, bag_channels, bag_leads, bag_table  # noqa: E402

class BagItemIdTest(unittest.TestCase):
    """候选 id 必须唯一：slug 是截断的，名字前缀相同的候选曾经撞成同一个 id。"""

    def test_ids_stay_unique_when_name_prefix_collides(self):
        first = bag_accept.bag_id("黑神话：悟空", "黑神话：悟空 全球音乐礼盒")
        second = bag_accept.bag_id("黑神话：悟空", "黑神话：悟空 官方设定集")
        self.assertNotEqual(first, second)

    def test_same_candidate_gets_a_stable_id(self):
        one = bag_accept.bag_id("绝区零", "双11福袋（游戏内礼包）")
        two = bag_accept.bag_id("绝区零", "双11福袋（游戏内礼包）")
        self.assertEqual(one, two)

    def test_id_keeps_the_readable_prefix(self):
        item = bag_accept.bag_id("绝区零", "双11福袋")
        self.assertTrue(item.startswith("bag-"))
        self.assertIn("绝区零", item)


CHANNEL = {
    "id": "official-mall",
    "publisher": "米哈游",
    "channel": "米游铺",
    "type": "official-mall",
    "tier": "A",
    "url": "https://shop.example.com/",
    "ipScope": ["原神"],
    "canAnswer": ["name", "price"],
    "status": "confirmed",
    "note": "",
}

LEAD = {
    "id": "lead-test",
    "ip": "原神",
    "ipType": "game",
    "publisher": "米哈游",
    "carriers": ["福袋", "神秘盒子"],
    "keywords": ["双11"],
    "channelIds": ["official-mall"],
    "scope": "cn",
    "priority": "P0",
    "status": "active",
    "windowHint": "",
    "lastRunId": "",
    "lastResult": "",
    "lastHitAt": "",
    "source": "manual",
    "note": "",
}

PAGE = (
    "<html><body><h1>原神 2026 双11心动福袋</h1>"
    "<p>原神 2026 双11心动福袋 368元/个，随机14-18件周边</p>"
    "<p>限购1件</p></body></html>"
)


def candidate(**overrides) -> dict:
    base = {
        "ip": "原神",
        "officialName": "原神 2026 双11心动福袋",
        "carrier": "福袋",
        "role": "official_release",
        "tiers": [
            {
                "price": 368,
                "items": "随机14-18件",
                "quote": "原神 2026 双11心动福袋 368元/个，随机14-18件周边",
                "source": "https://shop.example.com/goods/1",
            }
        ],
        "window": {"start": "2026-10-31", "end": "2026-11-06"},
        "channels": ["米游铺"],
        "limit": "限购1件",
        "aliases": ["心动福袋"],
        "source": "https://shop.example.com/goods/1",
        "quote": "原神 2026 双11心动福袋 368元/个",
        "confidence": 0.9,
    }
    base.update(overrides)
    return base


class VerifyTests(unittest.TestCase):
    def setUp(self):
        channels = {CHANNEL["id"]: CHANNEL}
        self.channels = channels
        self._fetch = bag_accept.fetch_text
        self._ds = bag_accept.bag_dispatch.ds_fetch
        bag_accept.fetch_text = lambda url, timeout=20: (True, PAGE, "")
        bag_accept.bag_dispatch.ds_fetch = lambda url: {"ok": False, "error": "skip", "content": ""}

    def tearDown(self):
        bag_accept.fetch_text = self._fetch
        bag_accept.bag_dispatch.ds_fetch = self._ds

    def run_verify(self, raw):
        normalized = bag_accept.normalize_candidate(raw, LEAD, "deepseek")
        return bag_accept.verify(normalized, LEAD, self.channels, {})

    def test_official_accepted(self):
        record = self.run_verify(candidate())
        self.assertEqual(record["status"], "accepted", record["reasons"])
        self.assertGreaterEqual(record["confidence"], 0.9)
        self.assertEqual(record["tiers"][0]["price"], 368)

    def test_price_mismatch_is_tier_conflict(self):
        raw = candidate()
        raw["tiers"][0]["price"] = 199
        record = self.run_verify(raw)
        self.assertEqual(record["status"], "rejected")
        self.assertIn("tier_conflict", record["reasons"])

    def test_missing_carrier_word(self):
        raw = candidate(quote="原神 2026 双11 周边 368元", officialName="原神 2026 双11 周边")
        raw["tiers"][0]["quote"] = "原神 2026 双11 周边 368元/个"
        record = self.run_verify(raw)
        self.assertEqual(record["status"], "rejected")
        self.assertIn("carrier_missing", record["reasons"])

    def test_unknown_domain_stays_pending(self):
        raw = candidate(source="https://www.other.com/goods/1")
        raw["tiers"][0]["source"] = "https://www.other.com/goods/1"
        record = self.run_verify(raw)
        self.assertEqual(record["status"], "pending_review")
        self.assertIn("channel_unverified", record["reasons"])

    def test_secondhand_rejected(self):
        raw = candidate(source="https://www.goofish.com/item/1")
        record = self.run_verify(raw)
        self.assertEqual(record["status"], "rejected")
        self.assertIn("secondhand_forbidden", record["reasons"])

    def test_unverifiable_quote_goes_pending(self):
        raw = candidate(quote="这句话页面里没有")
        record = self.run_verify(raw)
        self.assertEqual(record["status"], "pending_review")
        self.assertIn("quote_unverified", record["reasons"])

    def test_expired_window_rejected(self):
        raw = candidate(window={"start": "2021-09-03", "end": "2021-09-30"})
        normalized = bag_accept.normalize_candidate(raw, LEAD, "deepseek")
        record = bag_accept.verify(normalized, LEAD, self.channels, {}, ("2026-09-18", "2026-11-17"))
        self.assertEqual(record["status"], "rejected")
        self.assertIn("out_of_window", record["reasons"])

    def test_current_window_passes(self):
        normalized = bag_accept.normalize_candidate(candidate(), LEAD, "deepseek")
        record = bag_accept.verify(normalized, LEAD, self.channels, {}, ("2026-09-18", "2026-11-17"))
        self.assertEqual(record["status"], "accepted", record["reasons"])

    def test_merge_two_lanes(self):
        left = bag_accept.normalize_candidate(candidate(), LEAD, "workbuddy")
        right = bag_accept.normalize_candidate(candidate(tiers=[{"price": 89, "items": "随机7件", "quote": "89元", "source": "https://shop.example.com/goods/1"}]), LEAD, "deepseek")
        merged = bag_accept.merge([left, right])
        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["lane"], "both")
        self.assertEqual(len(merged[0]["tiers"]), 2)


class LeadTests(unittest.TestCase):
    def test_validation(self):
        bad = bag_leads.validate({**LEAD, "carriers": []}, {"official-mall"})
        self.assertTrue(any("carriers" in item for item in bad))
        bad = bag_leads.validate({**LEAD, "channelIds": ["nope"]}, {"official-mall"})
        self.assertTrue(any("渠道" in item for item in bad))
        bad = bag_leads.validate({**LEAD, "id": "genshin"}, {"official-mall"})
        self.assertTrue(any("id" in item for item in bad))

    def test_upsert_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "leads.json"
            bag_leads.upsert(LEAD, {"official-mall"}, path=path)
            data = bag_leads.load(path)
            self.assertEqual(len(data["leads"]), 1)
            self.assertEqual(data["leads"][0]["id"], "lead-test")
            bag_leads.remove("lead-test", path=path)
            self.assertEqual(bag_leads.load(path)["leads"], [])

    def test_stats(self):
        stats = bag_leads.stats([LEAD], [CHANNEL])
        self.assertEqual(stats["total"], 1)
        self.assertEqual(stats["active"], 1)
        self.assertEqual(stats["noChannel"], 0)


class ChannelTests(unittest.TestCase):
    def test_validation(self):
        bad = bag_channels.validate({**CHANNEL, "tier": "Z"})
        self.assertTrue(any("tier" in item for item in bad))
        bad = bag_channels.validate({**CHANNEL, "url": "ftp://x"})
        self.assertTrue(any("url" in item for item in bad))

    def test_usable(self):
        self.assertTrue(bag_channels.usable(CHANNEL))
        self.assertFalse(bag_channels.usable({**CHANNEL, "tier": "D"}))
        self.assertFalse(bag_channels.usable({**CHANNEL, "status": "pending"}))


def fake_fields():
    def select(title, options):
        return {
            "field_title": title,
            "field_type": "single_select",
            "property_single_select": {"options": [{"id": f"{title}-{i}", "text": text} for i, text in enumerate(options)]},
        }

    return [
        select("IP类型", ["游戏", "潮玩", "动漫", "其他"]),
        select("载体", ["福袋", "神秘盒子", "礼盒", "惊喜袋", "盲袋", "其他"]),
        select("载体性质", ["官方原称", "等价载体"]),
        select("状态", ["官方在售", "已结束", "存疑"]),
    ]


class TableTests(unittest.TestCase):
    def setUp(self):
        self._list_fields = bag_table.list_fields
        bag_table.list_fields = lambda refresh=False: fake_fields()

    def tearDown(self):
        bag_table.list_fields = self._list_fields

    def test_status_mapping(self):
        values = bag_table.bag_values(
            {
                "id": "bag-x",
                "ip": "原神",
                "ipType": "game",
                "publisher": "米哈游",
                "officialName": "原神 双11心动福袋",
                "carrier": "福袋",
                "role": "official_release",
                "tiers": [{"price": 368, "items": "随机14-18件"}],
                "status": "accepted",
                "confidence": 0.95,
                "evidence": [{"url": "https://x", "quote": "368元"}],
            }
        )
        self.assertEqual(values["状态"][0]["text"], "官方在售")
        self.assertEqual(values["最低官方价"], 368)
        self.assertEqual(values["载体"][0]["text"], "福袋")
        self.assertEqual(values["载体性质"][0]["text"], "官方原称")

    def test_equivalent_carrier(self):
        values = bag_table.bag_values(
            {
                "id": "bag-y",
                "ip": "英雄联盟",
                "ipType": "game",
                "publisher": "腾讯",
                "officialName": "全球总决赛神秘盒子",
                "carrier": "神秘盒子",
                "role": "equivalent_carrier",
                "tiers": [{"price": 199, "items": "随机"}],
                "status": "official",
                "confidence": 0.85,
                "evidence": [{"url": "https://x", "quote": "199元"}],
            }
        )
        self.assertEqual(values["载体"][0]["text"], "神秘盒子")
        self.assertEqual(values["载体性质"][0]["text"], "等价载体")


if __name__ == "__main__":
    unittest.main()
