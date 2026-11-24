"""通道派发的离线测试：不联网、不派 Agent、不写表。

跑法：python3 -m unittest discover -s apps/acg-capture/engines/scripts/tests -v

盯的是 2026-11-23 那次复盘的四件事：
1. 19 盘塞一个 job → 每盘只回赏名、个数全空；现在必须按 LANE_CHUNK_SIZE 切块，并限制并发；
2. CLI 被删 / credential helper 缺失在提交时才暴露 → 整轮 failed；现在必须派发前自检，
   把原因写进 run.json，并以 partial 结束（CLI 退出码非 0），不要假装完成；
3. job 一起步就 interrupted，脚本空等 28 分钟；interrupted 现在算终态，并且会重试一次；
4. 两个通道合并后看不出谁给的料；候选现在带 lane，合并后必须留并集。
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

import acg.common as common  # noqa: E402
import acg_run  # noqa: E402
from acg import accept, dispatch  # noqa: E402


def make_pan(index: int) -> dict:
    return {
        "rid": f"p{index}",
        "name": f"一番赏 测试盘 {index}",
        "alias": "",
        "brand": "一番赏",
        "price": "未公布",
        "release": "2026-11-20",
    }


def make_sub(index: int) -> dict:
    return {"rid": f"r{index}", "pan_rid": f"p{index}", "kind": "A", "name": "A赏", "qty": None}


def candidate_text(name: str) -> str:
    return json.dumps(
        [
            {
                "pan": name,
                "price": {"value": None, "currency": "CNY", "quote": "", "source": ""},
                "total": None,
                "prizes": [],
                "missing": ["test"],
            }
        ],
        ensure_ascii=False,
    )


class ChunkTest(unittest.TestCase):
    def test_19_pans_become_4_jobs_of_at_most_6(self):
        self.assertEqual([len(piece) for piece in dispatch.chunk(list(range(19)))], [6, 6, 6, 1])

    def test_bad_size_falls_back_to_default(self):
        self.assertEqual([len(piece) for piece in dispatch.chunk([1, 2, 3], "oops")], [3])

    def test_negative_size_keeps_one_per_job(self):
        self.assertEqual([len(piece) for piece in dispatch.chunk([1, 2, 3], -2)], [1, 1, 1])


class TerminalTest(unittest.TestCase):
    def test_interrupted_is_terminal_and_exposes_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            path.write_text(
                json.dumps({"status": "interrupted", "error": "Missing dsh-workbuddy-connect credential helper"}),
                encoding="utf-8",
            )
            started = time.time()
            state = dispatch.wait_job(str(path), timeout=30, interval=0.01)
        self.assertEqual(state["status"], "interrupted")
        self.assertLess(time.time() - started, 5, "interrupted 必须当终态，不能空等到超时")
        self.assertIn("credential", dispatch.job_error(state))


class PreflightTest(unittest.TestCase):
    def test_missing_cli_is_reported(self):
        with mock.patch.object(dispatch, "LOCAL_AGENT", "/nonexistent/local-agent"):
            result = dispatch.preflight_workbuddy()
        self.assertFalse(result["ok"])
        self.assertTrue(result["error"].startswith("local_agent_missing"))

    def test_missing_credential_helper_is_reported(self):
        with mock.patch.object(dispatch, "LOCAL_AGENT", sys.executable), mock.patch.object(
            dispatch, "_credential_helper", return_value=""
        ):
            result = dispatch.preflight_workbuddy()
        self.assertFalse(result["ok"])
        self.assertTrue(result["error"].startswith("credential_helper_missing"))

    def test_status_payload_makes_lane_ready(self):
        payload = json.dumps({"backend": "workbuddy", "installed": True, "execution_ready": True})
        fake = mock.Mock(returncode=0, stdout=payload, stderr="")
        with mock.patch.object(dispatch, "LOCAL_AGENT", sys.executable), mock.patch.object(
            dispatch, "_credential_helper", return_value="/tmp/host-heartbeat-x.js"
        ), mock.patch.object(dispatch.subprocess, "run", return_value=fake):
            result = dispatch.preflight_workbuddy()
        self.assertTrue(result["ok"], result)
        self.assertTrue(result["detail"]["executionReady"])

    def test_deepseek_missing_script_is_reported(self):
        with mock.patch.object(dispatch, "DS_SEARCH", Path("/nonexistent/ds_search.py")):
            result = dispatch.preflight_deepseek()
        self.assertFalse(result["ok"])
        self.assertTrue(result["error"].startswith("ds_search_missing"))

    def test_missing_wrapper_is_recreated_from_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            cli = Path(tmp) / "bin" / "local-agent"
            bridge = Path(tmp) / "bridge.py"
            bridge.write_text("# fake bridge\n", encoding="utf-8")
            with mock.patch.object(dispatch, "LOCAL_AGENT", str(cli)), mock.patch.object(
                dispatch, "LOCAL_AGENT_BRIDGE", bridge
            ):
                result = dispatch.ensure_local_agent()
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["repaired"])
            self.assertIn("bridge.py", cli.read_text(encoding="utf-8"))
            self.assertTrue(cli.stat().st_mode & 0o111, "复原出来的包装必须可执行")

    def test_missing_wrapper_without_bridge_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(dispatch, "LOCAL_AGENT", str(Path(tmp) / "bin" / "local-agent")), mock.patch.object(
                dispatch, "LOCAL_AGENT_BRIDGE", Path(tmp) / "missing-bridge.py"
            ):
                result = dispatch.ensure_local_agent()
        self.assertFalse(result["ok"])
        self.assertTrue(result["error"].startswith("bridge_missing"))


class MergeLaneTest(unittest.TestCase):
    def test_single_workbuddy_candidate_keeps_lane(self):
        merged = accept.merge_candidates(
            [{"pan": "A", "lane": "workbuddy", "prizes": [], "price": {"value": None}, "total": None}]
        )
        self.assertEqual(merged["lanes"], ["workbuddy"])

    def test_two_lanes_become_union(self):
        merged = accept.merge_candidates(
            [
                {"pan": "A", "lane": "workbuddy", "prizes": [], "price": {"value": None}, "total": None},
                {
                    "pan": "A",
                    "lane": "deepseek",
                    "prizes": [],
                    "price": {"value": 100, "currency": "CNY", "quote": "100元", "source": "https://x"},
                    "total": 10,
                },
            ]
        )
        self.assertEqual(merged["lanes"], ["deepseek", "workbuddy"])


class BackfillDispatchTest(unittest.TestCase):
    """整条补齐链路：自检 → 切块派发 → 等结果 → 重试 → 通道台账。"""

    def setUp(self):
        self._runs_dir = common.RUNS_DIR
        self.tmp = tempfile.TemporaryDirectory()
        common.RUNS_DIR = Path(self.tmp.name)
        self.runs_dir = Path(self.tmp.name)
        self.prompts: list[str] = []

    def tearDown(self):
        common.RUNS_DIR = self._runs_dir
        self.tmp.cleanup()

    def _patches(self, wait_states, preflight_workbuddy=None, preflight_deepseek=None, ds_items=None):
        state_dir = self.runs_dir / "jobstate"
        state_dir.mkdir(parents=True, exist_ok=True)
        counter = {"n": 0}
        queued = list(wait_states)

        def submit(prompt, title, workdir, model=None):
            counter["n"] += 1
            job_id = f"job-{counter['n']}"
            path = state_dir / f"{job_id}.json"
            path.write_text(json.dumps({"status": "submitted"}), encoding="utf-8")
            self.prompts.append(prompt)
            return {
                "jobId": job_id,
                "status": "submitted",
                "model": "m",
                "resultPath": str(path),
                "statePath": str(path),
            }

        def wait_jobs(paths, timeout=600, interval=5, on_tick=None):
            batch = queued.pop(0) if queued else [{"status": "succeeded", "text": ""}] * len(paths)
            out = []
            for index, _path in enumerate(paths):
                out.append(batch[index] if index < len(batch) else {"status": "succeeded", "text": ""})
            return out

        ds_result = {
            "items": ds_items or [],
            "perPan": {},
            "errors": [],
            "elapsed": 1.0,
            "sources": 3,
        }
        return [
            mock.patch.object(acg_run, "page_renderer", return_value=lambda url: ""),
            mock.patch.object(dispatch, "submit_workbuddy", side_effect=submit),
            mock.patch.object(dispatch, "wait_jobs", side_effect=wait_jobs),
            mock.patch.object(
                dispatch, "preflight_workbuddy",
                return_value=preflight_workbuddy or {"ok": True, "error": "", "detail": {}},
            ),
            mock.patch.object(
                dispatch, "preflight_deepseek",
                return_value=preflight_deepseek or {"ok": True, "error": "", "detail": {}},
            ),
            mock.patch("acg.backfill_ds.run_pans", return_value=ds_result),
        ]

    def _run(self, pans, *, wait_states, lanes=("workbuddy",), **kwargs):
        patches = self._patches(wait_states, **kwargs)
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        pans_payload = [make_pan(index) for index in range(1, pans + 1)]
        subs_payload = [make_sub(index) for index in range(1, pans + 1)]
        with mock.patch.object(acg_run.table, "load_pans", return_value=pans_payload), mock.patch.object(
            acg_run.table, "load_subs", return_value=subs_payload
        ):
            run = common.Run("backfill", trigger="test", dry_run=True)
            acg_run.backfill(run, 999, True, False, wait=5, lanes=list(lanes))
        return run

    def test_big_batch_is_split_into_small_jobs(self):
        run = self._run(13, wait_states=[[{"status": "succeeded", "text": candidate_text("一番赏 测试盘 1")}] * 3])
        self.assertEqual(len(self.prompts), 3, "13 盘必须切成 3 个 job，不能一坨")
        for prompt in self.prompts:
            lines = [line for line in prompt.splitlines() if line.startswith("盘")]
            self.assertLessEqual(len(lines), dispatch.LANE_CHUNK_SIZE)
        self.assertEqual(run.state["status"], "done")
        self.assertTrue(run.state["lanes"]["workbuddy"]["ok"])
        self.assertEqual(len(run.state["lanes"]["workbuddy"]["jobs"]), 3)
        self.assertEqual(len(run.state["params"]["jobIds"]), 3)

    def test_candidates_carry_lane(self):
        run = self._run(2, wait_states=[[{"status": "succeeded", "text": candidate_text("一番赏 测试盘 1")}]])
        candidate = run.state["items"][0]["candidate"]
        self.assertEqual(candidate["lanes"], ["workbuddy"])

    def test_unready_workbuddy_fails_loudly_but_keeps_deepseek(self):
        run = self._run(
            2,
            wait_states=[],
            lanes=("workbuddy", "deepseek"),
            preflight_workbuddy={
                "ok": False,
                "error": "credential_helper_missing:dsh-workbuddy-connect",
                "detail": {},
            },
            ds_items=[{"pan": "一番赏 测试盘 1", "price": {"value": None}, "prizes": [], "total": None}],
        )
        self.assertEqual(self.prompts, [], "通道未就绪时不该再派 job")
        self.assertEqual(run.state["status"], "partial")
        self.assertIn("workbuddy", run.state["error"])
        self.assertFalse(run.state["lanes"]["workbuddy"]["ok"])
        self.assertTrue(run.state["lanes"]["deepseek"]["ok"])
        self.assertEqual(run.state["items"][0]["candidate"]["lanes"], ["deepseek"])

    def test_interrupted_job_is_retried_once(self):
        run = self._run(
            6,
            wait_states=[
                [{"status": "interrupted", "error": "Missing dsh-workbuddy-connect credential helper"}],
                [{"status": "succeeded", "text": candidate_text("一番赏 测试盘 1")}],
            ],
        )
        self.assertEqual(len(self.prompts), 2, "起步就死的 job 必须重试一次")
        self.assertEqual(run.state["status"], "done")
        self.assertTrue(run.state["lanes"]["workbuddy"]["ok"])

    def test_both_lanes_missing_marks_partial(self):
        run = self._run(
            2,
            wait_states=[],
            lanes=("workbuddy", "deepseek"),
            preflight_workbuddy={"ok": False, "error": "local_agent_missing:/x", "detail": {}},
            preflight_deepseek={"ok": False, "error": "ds_api_key_missing", "detail": {}},
        )
        self.assertEqual(run.state["status"], "partial")
        self.assertIn("deepseek", run.state["error"])
        self.assertIn("workbuddy", run.state["error"])


if __name__ == "__main__":
    unittest.main()
