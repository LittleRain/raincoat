"""官方福袋分桶的离线测试：不联网、不派 Agent、不写表。

跑法：python3 -m unittest discover -s apps/acg-capture/engines/scripts/tests -v

盯的是 2026-11-18 那次改动：原来按发行方轮转分桶，网易/东映那组只有 2 条线索却拖满
1200 秒上限，整轮时长被最慢的一组决定。改成「先按线索数拆单元，再塞进最空的桶」。
"""

from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from acg import bag_accept, bag_channels, bag_discover, dispatch  # noqa: E402


def _leads(count: int, prefix: str = "lead") -> list[dict]:
    return [{"id": f"{prefix}-{index}", "ip": f"IP{index}"} for index in range(count)]


class ChunkTest(unittest.TestCase):
    """任务不再按发行方分组，只按顺序切块：一个 job 里可以有不同发行方。"""

    def test_chunks_keep_order_and_every_lead(self) -> None:
        leads = _leads(23)

        chunks = bag_discover._chunks(leads, 10)

        self.assertEqual([len(chunk) for chunk in chunks], [10, 10, 3])
        flat = [lead["id"] for chunk in chunks for lead in chunk]
        self.assertEqual(flat, [lead["id"] for lead in leads], "顺序不能乱，也不能漏")

    def test_chunks_ignore_publisher(self) -> None:
        leads = [
            {"id": "lead-a", "ip": "三角洲行动", "publisher": "腾讯"},
            {"id": "lead-b", "ip": "绝区零", "publisher": "米哈游"},
            {"id": "lead-c", "ip": "第五人格", "publisher": "网易"},
        ]

        chunks = bag_discover._chunks(leads, 10)

        self.assertEqual(len(chunks), 1, "2 条跨 3 个发行方也只切一块")
        self.assertEqual({lead["publisher"] for lead in chunks[0]}, {"腾讯", "米哈游", "网易"})

    def test_chunk_label(self) -> None:
        self.assertEqual(bag_discover._chunk_label(_leads(2)), "IP0、IP1")
        self.assertEqual(bag_discover._chunk_label(_leads(5)), "IP0、IP1 等 5 个")

    def test_empty_input(self) -> None:
        self.assertEqual(bag_discover._chunks([], 10), [])

    def test_size_zero_is_safe(self) -> None:
        self.assertEqual(len(bag_discover._chunks(_leads(3), 0)), 3)


class PlanJobsTest(unittest.TestCase):
    """2026-11-18 改口径：不再「没渠道就跳过」。

    之前的规则是整组没有 confirmed 渠道就不派 job（怕空搜到超时），结果是 68 条线索里只有
    几条能跑。现在改成两套任务：
      - sweep：所有线索都派，全网扫，已知渠道只当优先入口；
      - channel：只有绑了可用渠道的线索才额外派一组只翻官方渠道的定向任务。
    """

    CHANNELS = [
        {"id": "mihoyo-miyoushe", "channel": "米游社", "tier": "A", "status": "confirmed", "url": "https://www.miyoushe.com/"},
        {"id": "netease-dashen", "channel": "网易大神", "tier": "C", "status": "pending", "url": ""},
    ]
    SINCE, UNTIL = "2026-09-18", "2026-11-18"

    def plan(self, leads: list[dict], modes: set[str] | None = None):
        channels = {row["id"]: row for row in self.CHANNELS}
        usable_ids = {row["id"] for row in self.CHANNELS if bag_channels.usable(row)}
        return bag_discover._plan_jobs(leads, channels, usable_ids, self.SINCE, self.UNTIL, modes)

    def test_lead_without_channel_still_gets_a_sweep_job(self) -> None:
        leads = [{"id": "lead-id5", "ip": "第五人格", "publisher": "网易", "carriers": ["福袋"], "channelIds": []}]

        sweep, channel = self.plan(leads)

        self.assertEqual(len(sweep), 1)
        self.assertEqual(sweep[0]["mode"], "sweep")
        self.assertIn("第五人格", sweep[0]["prompt"])
        self.assertIn("时间窗口", sweep[0]["prompt"])
        self.assertEqual(channel, [], "没有可用渠道就不该开定向任务")

    def test_pending_channel_does_not_trigger_targeted_job(self) -> None:
        leads = [
            {"id": "lead-id5", "ip": "第五人格", "publisher": "网易", "carriers": ["福袋"], "channelIds": ["netease-dashen"]},
        ]

        sweep, channel = self.plan(leads)

        self.assertEqual(len(sweep), 1)
        self.assertEqual(channel, [])

    def test_channel_lead_gets_both_jobs(self) -> None:
        leads = [
            {"id": "lead-zzz", "ip": "绝区零", "publisher": "米哈游", "carriers": ["福袋"], "channelIds": ["mihoyo-miyoushe"]},
        ]

        sweep, channel = self.plan(leads)

        self.assertEqual(len(sweep), 1, "sweep 也要覆盖它，不能因为它有渠道就少一路")
        self.assertEqual(len(channel), 1)
        self.assertEqual(channel[0]["mode"], "channel")
        self.assertEqual(channel[0]["channelIds"], ["mihoyo-miyoushe"])
        self.assertIn("官方渠道（只认这些来源）", channel[0]["prompt"])
        # sweep 是轻量全网搜：不列渠道、不要求逐页核对
        self.assertIn("尽量以公开的官方信息和电商平台信息为准", sweep[0]["prompt"])
        self.assertNotIn("只认这些来源", sweep[0]["prompt"])

    def test_every_lead_covers_sweep_exactly_once(self) -> None:
        groups = {
            "腾讯": _leads(7, "tencent"),
            "网易": _leads(5, "netease"),
            "米哈游": _leads(4, "mihoyo"),
        }
        for publisher, rows in groups.items():
            for lead in rows:
                lead["publisher"] = publisher
                lead["channelIds"] = []
        leads = [lead for rows in groups.values() for lead in rows]

        sweep, _ = self.plan(leads)
        covered = [lead["id"] for job in sweep for lead in job["leads"]]

        self.assertEqual(len(covered), len(leads), "sweep 必须一条不漏")
        self.assertEqual(len(covered), len(set(covered)), "同一条线索不能重复派")

    def test_sweep_job_size_is_capped(self) -> None:
        leads = [
            {"id": f"lead-{index}", "ip": f"IP{index}", "publisher": f"发行方{index}", "channelIds": []}
            for index in range(68)
        ]

        sweep, _ = self.plan(leads)

        self.assertEqual(len(sweep), math.ceil(68 / bag_discover.SWEEP_LEADS_PER_JOB))
        for job in sweep:
            self.assertLessEqual(len(job["leads"]), bag_discover.SWEEP_LEADS_PER_JOB)

    def test_modes_can_run_only_one_set(self) -> None:
        leads = [
            {"id": "lead-zzz", "ip": "绝区零", "publisher": "米哈游", "carriers": ["福袋"], "channelIds": ["mihoyo-miyoushe"]},
        ]

        sweep_only, no_channel = self.plan(leads, {"sweep"})
        no_sweep, channel_only = self.plan(leads, {"channel"})

        self.assertEqual(len(sweep_only), 1)
        self.assertEqual(no_channel, [])
        self.assertEqual(no_sweep, [])
        self.assertEqual(len(channel_only), 1)

    def test_no_agent_means_no_prompt_building(self) -> None:
        """只算清单不派 Agent 时不该构造 prompt（真实跑是由 run() 判断 lane_set）。"""
        self.assertEqual(bag_discover._plan_jobs([], {}, set(), self.SINCE, self.UNTIL), ([], []))


class MergeModesTest(unittest.TestCase):
    """合并后要能看出这一条是哪条路找到的：全网扫街 / 定向渠道 / 两条都命中。"""

    LEAD = {
        "id": "lead-zzz",
        "ip": "绝区零",
        "ipType": "game",
        "carriers": ["福袋"],
        "channelIds": ["mihoyo-miyoushe"],
    }

    def raw(self) -> dict:
        return {
            "ip": "绝区零",
            "officialName": "绝区零 双11 福袋",
            "carrier": "福袋",
            "tiers": [{"price": 89, "items": "随机7件", "quote": "89元", "source": "https://www.miyoushe.com/goods/1"}],
            "source": "https://www.miyoushe.com/goods/1",
            "quote": "89元 随机7件",
        }

    def test_modes_accumulate_across_two_paths(self) -> None:
        left = bag_accept.normalize_candidate(self.raw(), self.LEAD, "workbuddy", "channel")
        right = bag_accept.normalize_candidate(self.raw(), self.LEAD, "deepseek", "sweep")

        merged = bag_accept.merge([left, right])

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0]["lane"], "both")
        self.assertEqual(merged[0]["modes"], ["channel", "sweep"])

    def test_single_path_keeps_its_mode(self) -> None:
        only = bag_accept.normalize_candidate(self.raw(), self.LEAD, "workbuddy", "channel")

        merged = bag_accept.merge([only])

        self.assertEqual(merged[0]["modes"], ["channel"])

    def test_mode_defaults_to_sweep_for_legacy_candidates(self) -> None:
        legacy = bag_accept.normalize_candidate(self.raw(), self.LEAD, "deepseek")

        self.assertEqual(legacy["mode"], "sweep")


class JobTimeoutTest(unittest.TestCase):
    """单 job 等待不能是死数：26 个 job 全并发时，慢的那个决定整轮时长。"""

    def test_wait_scales_with_lead_count(self) -> None:
        with mock.patch.object(bag_discover, "WB_WAIT_FIXED", 0):
            self.assertLess(bag_discover._job_timeout(3), bag_discover._job_timeout(11))

    def test_budget_clips_wait(self) -> None:
        with mock.patch.object(bag_discover, "WB_WAIT_FIXED", 0), mock.patch.object(bag_discover, "BUDGET_RESERVE", 300):
            clipped = bag_discover._job_timeout(20, remaining=900)

        self.assertLessEqual(clipped, 600, "剩余 900 秒、留 300 给验收，单个 job 最多等 600")

    def test_fixed_override_wins(self) -> None:
        with mock.patch.object(bag_discover, "WB_WAIT_FIXED", 5):
            self.assertEqual(bag_discover._job_timeout(12, remaining=1000), 5)

    def test_never_waits_zero(self) -> None:
        with mock.patch.object(bag_discover, "WB_WAIT_FIXED", 0), mock.patch.object(bag_discover, "BUDGET_RESERVE", 300):
            self.assertEqual(bag_discover._job_timeout(3, remaining=310), 30)

    def test_budget_covers_whole_run(self) -> None:
        """默认预算 + 预留 ≈ 半小时：采集 25 分钟、验收 5 分钟。"""
        self.assertLessEqual(bag_discover.RUN_BUDGET_SECONDS + bag_discover.BUDGET_RESERVE, 1800)

    def test_all_jobs_can_start_together(self) -> None:
        self.assertGreaterEqual(bag_discover.MAX_INFLIGHT_JOBS, 26, "26 个 job 要能一把起跑")


class TextOutputParseTest(unittest.TestCase):
    """轻量 prompt 只要求「商品名称 / 内容 / IP」，agent 会按表格或竖线行返回，得有兜底解析。"""

    TABLE = """| 商品名称 | 内容 | IP |
|---|---|---|
| 双11心动福袋 | 88元，随机7件，2026-10-20 开售，https://mihoyogift.com/goods/123 | 绝区零 |
| 红运福袋 | 游戏内掉落道具，非售卖商品 | 三角洲行动 |"""

    def test_markdown_table(self) -> None:
        rows = dispatch.parse_text_candidates(self.TABLE)

        self.assertEqual(len(rows), 2, "表头和分隔行不能被当成商品")
        self.assertEqual(rows[0]["officialName"], "双11心动福袋")
        self.assertEqual(rows[0]["ip"], "绝区零")

    def test_extracts_price_source_and_carrier(self) -> None:
        row = dispatch.parse_text_candidates(self.TABLE)[0]

        self.assertEqual(row["tiers"][0]["price"], 88)
        self.assertEqual(row["source"], "https://mihoyogift.com/goods/123")
        self.assertEqual(row["carrier"], "福袋")

    def test_row_without_price_keeps_empty_tiers(self) -> None:
        row = dispatch.parse_text_candidates(self.TABLE)[1]

        self.assertEqual(row["tiers"], [])
        self.assertEqual(row["source"], "")

    def test_plain_pipe_rows_and_bullets(self) -> None:
        rows = dispatch.parse_text_candidates("- 神秘盒子A | 299元，内含2~3款 | 英雄联盟\n无")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["ip"], "英雄联盟")

    def test_garbage_returns_empty(self) -> None:
        self.assertEqual(dispatch.parse_text_candidates("没查到，无。"), [])


class MissingSourceTest(unittest.TestCase):
    def test_missing_source_goes_pending(self) -> None:
        """轻量任务常常给不出来源 URL：机器不能证实也别急着判废。"""
        lead = {"id": "lead-x", "ip": "绝区零", "ipType": "game", "carriers": ["福袋"], "channelIds": []}
        raw = {"ip": "绝区零", "officialName": "双11心动福袋", "carrier": "福袋", "tiers": [], "source": "", "quote": "88元"}
        normalized = bag_accept.normalize_candidate(raw, lead, "workbuddy", "sweep")

        with mock.patch.object(bag_accept, "_page", lambda cache, url: (True, "88元", "")):
            record = bag_accept.verify(normalized, lead, {}, {})

        self.assertEqual(record["status"], "pending_review")
        self.assertIn("source_missing", record["reasons"])


if __name__ == "__main__":
    unittest.main()
