"""New-product detection against synthetic snapshots: window, seeds, dedupe."""
import json
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import diff_new  # noqa: E402


def write_snapshot(data_dir: Path, plat: str, cid: str, label: str, items: list[dict]) -> None:
    path = data_dir / "snapshots" / plat / cid / f"{label}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            row = {"snapshot_date": label, "plat": plat, "cid": cid, "month": label[:7],
                   "brand": "B", "shop": "S", "price": 100.0}
            row.update(item)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_seed(data_dir: Path, plat: str, cid: str, month: str, items: list[dict]) -> None:
    path = data_dir / "seeds" / plat / cid / f"{month}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for item in items:
            row = {"snapshot_date": month, "plat": plat, "cid": cid, "month": month}
            row.update(item)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def item(item_id: str, **extra) -> dict:
    base = {"item_id": item_id, "title": f"商品{item_id}", "rank": 1,
            "sold": 10.0, "sale": 1000.0}
    base.update(extra)
    return base


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_only_items_first_seen_inside_window(self):
        write_snapshot(self.data, "all", "1", "2026-11-10", [item("A"), item("B")])
        write_snapshot(self.data, "all", "1", "2026-11-17", [item("A"), item("B"), item("C")])
        write_snapshot(self.data, "all", "1", "2026-11-19", [item("A"), item("C"), item("D")])

        rows, meta = diff_new.window_rows(
            self.data, plat="all", cid="1", alias="面膜", cat_path="美容/面膜",
            day=date(2026, 11, 19), window=7,
        )
        ids = {row["item_id"] for row in rows}
        self.assertEqual(ids, {"C", "D"})
        self.assertFalse(meta["window_partial"])
        self.assertEqual(len(meta["snapshot_dates"]) if isinstance(meta["snapshot_dates"], list) else meta["snapshot_dates"], 3)

    def test_window_boundary_is_inclusive(self):
        write_snapshot(self.data, "all", "1", "2026-11-12", [item("X")])
        write_snapshot(self.data, "all", "1", "2026-11-13", [item("Y")])
        write_snapshot(self.data, "all", "1", "2026-11-19", [item("X"), item("Y")])

        rows, _ = diff_new.window_rows(
            self.data, plat="all", cid="1", alias="a", cat_path="", day=date(2026, 11, 19), window=7,
        )
        # window covers 11-13..11-19, so X (11-12) is out and Y (11-13) is in
        self.assertEqual({row["item_id"] for row in rows}, {"Y"})

    def test_partial_window_flagged(self):
        write_snapshot(self.data, "all", "1", "2026-11-16", [item("A")])
        write_snapshot(self.data, "all", "1", "2026-11-19", [item("A"), item("B")])
        rows, meta = diff_new.window_rows(
            self.data, plat="all", cid="1", alias="a", cat_path="", day=date(2026, 11, 19), window=7,
        )
        self.assertTrue(meta["window_partial"])
        self.assertTrue(all(row["window_partial"] for row in rows))
        self.assertEqual({row["item_id"] for row in rows}, {"A", "B"})

    def test_seed_month_is_not_new(self):
        write_seed(self.data, "all", "1", "2026-10", [item("OLD")])
        write_snapshot(self.data, "all", "1", "2026-11-19", [item("OLD"), item("NEW")])

        rows, _ = diff_new.window_rows(
            self.data, plat="all", cid="1", alias="a", cat_path="", day=date(2026, 11, 19), window=7,
        )
        by_id = {row["item_id"]: row for row in rows}
        self.assertNotIn("OLD", by_id)
        self.assertEqual(by_id["NEW"]["first_seen_month"], "2026-11")

    def test_seed_supplies_first_month_for_old_items(self):
        write_seed(self.data, "all", "1", "2026-10", [item("OLD")])
        write_snapshot(self.data, "all", "1", "2026-11-19", [item("OLD")])
        index = diff_new.first_seen(self.data, "all", "1", date(2026, 11, 19))
        self.assertEqual(index["OLD"]["first_month"], "2026-10")
        self.assertEqual(index["OLD"]["first_date"], "2026-11-19")

    def test_item_that_dropped_out_is_still_reported(self):
        write_snapshot(self.data, "all", "1", "2026-11-18", [item("A"), item("GONE")])
        write_snapshot(self.data, "all", "1", "2026-11-19", [item("A")])
        rows, _ = diff_new.window_rows(
            self.data, plat="all", cid="1", alias="a", cat_path="", day=date(2026, 11, 19), window=7,
        )
        by_id = {row["item_id"]: row for row in rows}
        self.assertIn("GONE", by_id)
        self.assertFalse(by_id["GONE"]["in_latest"])


class DedupeTests(unittest.TestCase):
    def test_same_item_in_two_categories_kept_once(self):
        rows = [
            {"plat": "all", "item_id": "1", "cat_alias": "面膜", "also_in": ""},
            {"plat": "all", "item_id": "1", "cat_alias": "精华", "also_in": ""},
            {"plat": "all", "item_id": "2", "cat_alias": "精华", "also_in": ""},
        ]
        kept = diff_new.dedupe_global(rows)
        self.assertEqual(len(kept), 2)
        first = next(r for r in kept if r["item_id"] == "1")
        self.assertEqual(first["cat_alias"], "面膜")
        self.assertEqual(first["also_in"], "精华")

    def test_same_id_on_different_platforms_is_distinct(self):
        rows = [
            {"plat": "all", "item_id": "1", "cat_alias": "面膜", "also_in": ""},
            {"plat": "jd", "item_id": "1", "cat_alias": "面膜", "also_in": ""},
        ]
        self.assertEqual(len(diff_new.dedupe_global(rows)), 2)


if __name__ == "__main__":
    unittest.main()
