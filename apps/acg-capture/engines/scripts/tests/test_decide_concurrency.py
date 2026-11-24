"""裁决并发测试：同时点多个「采信」，不能只有一个成功。

跑法：python3 -m unittest discover -s apps/acg-capture/engines/scripts/tests -v

2026-11-18 的问题：插件里每个「采信」按钮都会 spawn 一个引擎进程，各自读改写同一个 run.json。
没有锁时两个进程都读到「都还是待确认」，各自改自己那条再整体覆盖，后写的把先写的顶回 pending_review，
表现就是「点好几个只有一个成功」。这里用独立进程并发跑真实的 --decide 来复现与验收。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
BAG_RUN = SCRIPTS / "bag_run.py"
RUN_ID = "r-20261118-000000-bag-discover"


def _make_run(root: Path, items: int) -> Path:
    run_dir = root / "runs" / RUN_ID
    run_dir.mkdir(parents=True)
    state = {
        "id": RUN_ID,
        "kind": "bag-discover",
        "status": "partial",
        "stage": "done",
        "startedAt": "2026-11-18T00:00:00+08:00",
        "endedAt": "2026-11-18T00:00:10+08:00",
        "dryRun": False,
        "params": {},
        "table": {},
        "counts": {
            "dispatched": 0,
            "done": 0,
            "accepted": 0,
            "rejected": 0,
            "pending": items,
            "unavailable": 0,
            "written": 0,
        },
        "items": [
            {
                "id": f"bag-test-{index}",
                "leadId": "lead-test",
                "lane": "workbuddy",
                "ip": f"测试IP{index}",
                "officialName": f"测试福袋{index}",
                "carrier": "福袋",
                "status": "pending_review",
                "reasons": ["quote_unverified"],
                "tiers": [],
            }
            for index in range(items)
        ],
    }
    (run_dir / "run.json").write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    (run_dir / "events.jsonl").write_text("", encoding="utf-8")
    return run_dir


class ConcurrentDecideTest(unittest.TestCase):
    def test_parallel_accepts_all_land(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = _make_run(root, 4)
            env = {**os.environ, "ACG_DATA_DIR": str(root)}

            processes = [
                subprocess.Popen(
                    [
                        sys.executable,
                        str(BAG_RUN),
                        "--decide",
                        RUN_ID,
                        "--item",
                        f"bag-test-{index}",
                        "--decision",
                        "accept",
                        "--note",
                        "并发验收",
                    ],
                    cwd=str(SCRIPTS),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
                for index in range(4)
            ]
            results = [(process.wait(timeout=60), process.communicate()) for process in processes]

            for code, (stdout, stderr) in results:
                self.assertEqual(code, 0, f"decide 失败：{stdout}{stderr}")

            state = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
            statuses = [item["status"] for item in state["items"]]
            self.assertEqual(statuses, ["accepted"] * 4, f"有条目状态被覆盖：{statuses}")
            self.assertEqual(state["counts"]["accepted"], 4)
            self.assertEqual(state["counts"]["pending"], 0)

    def test_second_decide_on_same_item_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_run(root, 1)
            env = {**os.environ, "ACG_DATA_DIR": str(root)}
            base = [sys.executable, str(BAG_RUN), "--decide", RUN_ID, "--item", "bag-test-0"]

            first = subprocess.run([*base, "--decision", "accept"], cwd=str(SCRIPTS), env=env, capture_output=True, text=True)
            second = subprocess.run([*base, "--decision", "accept"], cwd=str(SCRIPTS), env=env, capture_output=True, text=True)

            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertNotEqual(second.returncode, 0, "同一条不应被裁决两次")
            self.assertIn("只有待确认才能裁决", second.stdout)


if __name__ == "__main__":
    unittest.main()
