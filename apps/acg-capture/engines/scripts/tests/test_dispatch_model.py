"""派发模型的离线测试：不联网、不派 Agent、不写表。

跑法：python3 -m unittest discover -s apps/acg-capture/engines/scripts/tests -v

盯的是 2026-11-18 的那次改动：三条抓取逻辑（官方赏 / 官方福袋 / 游戏虚拟商品）
派 WorkBuddy 时统一走用户自定义模型 `custom-local:deepseek-v4.1-flash`。
裸写 `deepseek-v4.1-flash` 会被桥接层判成「与官方模型冲突」拒收，所以前缀不能丢。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

from acg import dispatch  # noqa: E402

EXPECTED = "custom-local:deepseek-v4.1-flash"


def _fake_submit(captured: dict):
    class _Result:
        returncode = 0
        stdout = json.dumps(
            {"job_id": "job-1", "status": "submitted", "result_path": "/tmp/job-1/state.json"}
        )
        stderr = ""

    def run(command, **kwargs):
        captured["command"] = command
        return _Result()

    return run


class DispatchModelTest(unittest.TestCase):
    def test_default_model_is_custom_route(self) -> None:
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ACG_WORKBUDDY_MODEL", None)
            self.assertEqual(dispatch.workbuddy_model(), EXPECTED)

    def test_env_override(self) -> None:
        with mock.patch.dict(os.environ, {"ACG_WORKBUDDY_MODEL": "deep-model"}):
            self.assertEqual(dispatch.workbuddy_model(), "deep-model")

    def test_submit_passes_model_to_local_agent(self) -> None:
        captured: dict = {}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(
            os.environ, {}, clear=False
        ):
            os.environ.pop("ACG_WORKBUDDY_MODEL", None)
            with mock.patch.object(dispatch.subprocess, "run", _fake_submit(captured)):
                job = dispatch.submit_workbuddy("prompt", "title", Path(tmp))

        command = captured["command"]
        self.assertIn("--model", command)
        self.assertEqual(command[command.index("--model") + 1], EXPECTED)
        self.assertEqual(job["model"], EXPECTED)
        self.assertEqual(job["jobId"], "job-1")

    def test_explicit_model_argument_wins(self) -> None:
        captured: dict = {}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(
            dispatch.subprocess, "run", _fake_submit(captured)
        ):
            job = dispatch.submit_workbuddy("prompt", "title", Path(tmp), model="deepseek-v4-flash")

        command = captured["command"]
        self.assertEqual(command[command.index("--model") + 1], "deepseek-v4-flash")
        self.assertEqual(job["model"], "deepseek-v4-flash")


if __name__ == "__main__":
    unittest.main()
