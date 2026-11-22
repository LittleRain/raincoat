"""Tier/budget logic is pure, so it is the cheapest part to pin down."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import plan  # noqa: E402


class ClassifyTests(unittest.TestCase):
    def test_boundaries(self):
        self.assertEqual(plan.classify(1), "S")
        self.assertEqual(plan.classify(10), "S")
        self.assertEqual(plan.classify(11), "M")
        self.assertEqual(plan.classify(50), "M")
        self.assertEqual(plan.classify(51), "L")
        self.assertEqual(plan.classify(300), "L")
        self.assertEqual(plan.classify(301), "XL")

    def test_zero_rejected(self):
        with self.assertRaises(ValueError):
            plan.classify(0)

    def test_behaviour(self):
        self.assertFalse(plan.tier_config("S")["continue_on_error"])
        self.assertTrue(plan.tier_config("M")["continue_on_error"])
        self.assertTrue(plan.tier_config("L")["probe"])
        self.assertEqual(plan.tier_config("L")["concurrency"], 2)


class EstimateTests(unittest.TestCase):
    def test_requests_and_probe(self):
        stats = plan.estimate(4, topn=300, page_size=100, tier="S")
        self.assertEqual(stats["detail_requests"], 4 * 3)
        self.assertEqual(stats["probe_requests"], 0)
        self.assertEqual(stats["requests"], 12)

    def test_probe_only_for_large_tiers(self):
        stats = plan.estimate(60, topn=300, page_size=100, tier="L")
        self.assertEqual(stats["probe_requests"], 60)
        self.assertEqual(stats["requests"], 60 * 3 + 60)

    def test_partial_last_page(self):
        stats = plan.estimate(1, topn=110, page_size=100, tier="S")
        self.assertEqual(stats["detail_requests"], 2)


class BuildTests(unittest.TestCase):
    def pairs(self, count):
        return [{"plat": "all", "cid": str(i), "alias": f"c{i}"} for i in range(count)]

    def test_small_run(self):
        result = plan.build(self.pairs(3), {}, topn=300, page_size=100)
        self.assertEqual(result.tier, "S")
        self.assertFalse(result.continue_on_error)
        # 3 pairs x 3 pages x 2 default order_by slices
        self.assertEqual(result.requests, 18)

    def test_single_slice_halves_the_budget(self):
        config = {"fetch": {"order_by_slices": ["sale"]}}
        result = plan.build(self.pairs(3), config, topn=300, page_size=100)
        self.assertEqual(result.requests, 9)

    def test_budget_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            plan.build(self.pairs(10), {}, topn=300, page_size=100, max_requests=5)
        self.assertIn("超过 budget.max_requests", str(ctx.exception))

    def test_xl_requires_explicit_limit(self):
        with self.assertRaises(ValueError) as ctx:
            plan.build(self.pairs(400), {}, topn=10, page_size=10)
        self.assertIn("max_categories", str(ctx.exception))

    def test_xl_with_limit(self):
        config = {"fetch": {"max_categories": 50}}
        result = plan.build(self.pairs(400), config, topn=10, page_size=10,
                            max_requests=10_000)
        self.assertEqual(result.tier, "XL")
        self.assertTrue(result.continue_on_error)

    def test_empty_rejected(self):
        with self.assertRaises(ValueError):
            plan.build([], {}, topn=10, page_size=10)


if __name__ == "__main__":
    unittest.main()
