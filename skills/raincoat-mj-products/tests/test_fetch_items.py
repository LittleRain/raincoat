"""Row normalisation for the measured hot_items schema (cents, list cat_path)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import fetch_items  # noqa: E402
import mmiapi  # noqa: E402

ROW = {
    "item_id": "1065644714432",
    "title": "INANCE伊俪时黑钻奢润舒缓面膜",
    "shop_name": "伊俪时INANCE企业店",
    "brand_name": "",
    "brand": None,
    "price": 35000.0,
    "min_price": 33000.0,
    "price_raw": 35000.0,
    "sale": 490000.0,
    "sales": 490000.0,
    "sold": 14,
    "yoy": "-",
    "sold_yoy": "-",
    "cat_path": [
        {"category_id": "50025705", "category_name": "洗护清洁剂/卫生巾/纸/香薰", "level": 1},
        {"category_id": "50448025", "category_name": "面部清洁/护理", "level": 2},
        {"category_id": "50452018", "category_name": "面膜", "level": 3},
    ],
}


class NormalizeTests(unittest.TestCase):
    def test_cents_become_yuan(self):
        row = fetch_items.normalize(
            ROW, plat="all", cid="50452018", month="2026-10", label="2026-11-19",
            rank=1, slice_name="sale",
        )
        self.assertEqual(row["price"], 350.0)
        self.assertEqual(row["min_price"], 330.0)
        self.assertEqual(row["sale"], 4900.0)
        self.assertEqual(row["price_raw"], 35000.0)
        # 14 units * 350 yuan == 4900 yuan, i.e. the cents reading is self-consistent
        self.assertAlmostEqual(row["sold"] * row["price"], row["sale"])

    def test_yuan_mode_skips_conversion(self):
        row = fetch_items.normalize(
            ROW, plat="all", cid="50452018", month="2026-10", label="2026-11-19",
            rank=1, slice_name="sale", price_unit="yuan",
        )
        self.assertEqual(row["price"], 35000.0)
        self.assertEqual(row["sale"], 490000.0)

    def test_cat_path_is_a_list(self):
        row = fetch_items.normalize(
            ROW, plat="all", cid="50452018", month="2026-10", label="2026-11-19",
            rank=1, slice_name="sale",
        )
        self.assertEqual(row["cat_path"], "洗护清洁剂/卫生巾/纸/香薰/面部清洁/护理/面膜")

    def test_dash_ratio_is_missing(self):
        row = fetch_items.normalize(
            ROW, plat="all", cid="1", month="2026-10", label="2026-11-19",
            rank=2, slice_name="sold",
        )
        self.assertIsNone(row["yoy"])
        self.assertIsNone(row["sold_yoy"])

    def test_missing_item_id_is_skipped(self):
        broken = dict(ROW)
        broken.pop("item_id")
        self.assertIsNone(
            fetch_items.normalize(broken, plat="all", cid="1", month="2026-10",
                                  label="x", rank=1, slice_name="sale")
        )

    def test_missing_title_raises_instead_of_empty(self):
        broken = dict(ROW)
        broken.pop("title")
        with self.assertRaises(mmiapi.SchemaChanged):
            fetch_items.normalize(broken, plat="all", cid="1", month="2026-10",
                                  label="x", rank=1, slice_name="sale")


class ExtractTests(unittest.TestCase):
    def test_empty_page_is_not_a_schema_change(self):
        rows, total = mmiapi.extract_rows({"status": "ok", "result": {"count": 100, "data": []}})
        self.assertEqual(rows, [])
        self.assertEqual(total, 100)

    def test_page_payload(self):
        rows, total = mmiapi.extract_rows(
            {"status": "ok", "result": {"count": 100, "data": [{"item_id": "1"}]}}
        )
        self.assertEqual(rows, [{"item_id": "1"}])
        self.assertEqual(total, 100)


class ParamTests(unittest.TestCase):
    def test_paging_params(self):
        # the server ignores iDisplayStart; these two names are the ones that work
        params = fetch_items.build_params("2026-10", page=2, page_size=100, order_by="sold")
        self.assertEqual(params["page"], 2)
        self.assertEqual(params["page_size"], 100)
        self.assertEqual(params["order_by"], "sold")
        self.assertEqual(params["desc"], "true")
        self.assertNotIn("iDisplayStart", params)

    def test_hard_cap_constant(self):
        self.assertEqual(fetch_items.MAX_ROWS_PER_SLICE, 100)


if __name__ == "__main__":
    unittest.main()
