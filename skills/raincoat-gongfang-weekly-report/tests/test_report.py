"""Synthetic regression for the current six-file, weekly Gongfang contract."""
import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SKILL_ROOT = Path(__file__).resolve().parents[1]
GENERATOR = SKILL_ROOT / "scripts" / "generate_report.py"


class GongfangReportTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.input_dir = self.root / "input"
        self.input_dir.mkdir()
        self.output = self.root / "report.html"
        self._write_six_weekly_csvs()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_csv(self, filename, fields, rows):
        with (self.input_dir / filename).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    @staticmethod
    def _row(week, industry="", channel="", entry="", seller="", product="",
             pv=0, uv=0, orders=0, buyers=0, gmv=0, pvctr=0.1):
        return {
            "周五-周四周": week,
            "后台一级类目名称": industry,
            "内容类型": channel,
            "资源位二级入口": entry,
            "店铺名称": seller,
            "商品名称": product,
            "商品曝光PV": pv,
            "PVCTR": pvctr,
            "商详UV": uv,
            "支付订单数": orders,
            "支付订单买家数": buyers,
            "GMV（不减退款）": gmv,
            "商详支付转化率-UV": orders / uv if uv else 0,
            "GPM": gmv / pv * 1000 if pv else 0,
        }

    def _write_six_weekly_csvs(self):
        base_fields = [
            "周五-周四周", "商品曝光PV", "PVCTR", "商详UV", "支付订单数",
            "支付订单买家数", "GMV（不减退款）", "商详支付转化率-UV", "GPM",
        ]
        dimensions = [
            "周五-周四周", "后台一级类目名称", "内容类型", "资源位二级入口",
            "店铺名称", "商品名称", "商品曝光PV", "PVCTR", "商详UV",
            "支付订单数", "支付订单买家数", "GMV（不减退款）",
            "商详支付转化率-UV", "GPM",
        ]
        weeks = [14, 15]

        overall = [
            {"周五-周四周": 14, "商品曝光PV": 10000, "PVCTR": .10, "商详UV": 100,
             "支付订单数": 10, "支付订单买家数": 8, "GMV（不减退款）": 1000,
             "商详支付转化率-UV": .10, "GPM": 100},
            {"周五-周四周": 15, "商品曝光PV": 15000, "PVCTR": .16, "商详UV": 240,
             "支付订单数": 24, "支付订单买家数": 18, "GMV（不减退款）": 3000,
             "商详支付转化率-UV": .10, "GPM": 200},
        ]
        self._write_csv("整体数据-weekly.csv", base_fields, overall)

        industry = []
        for week, values in {
            14: [("绘画", 6000, 60, 6, 5, 600), ("VUP周边", 4000, 40, 4, 3, 400)],
            15: [("绘画", 9000, 144, 15, 11, 1800), ("VUP周边", 6000, 96, 9, 7, 1200)],
        }.items():
            for name, pv, uv, orders, buyers, gmv in values:
                industry.append(self._row(week, industry=name, pv=pv, uv=uv, orders=orders,
                                          buyers=buyers, gmv=gmv, pvctr=uv / pv))
        self._write_csv("行业数据-weekly.csv", dimensions, industry)

        channels = []
        channel_gmv = {
            14: {"绘画": {"商品": 400, "视频": 200}, "VUP周边": {"商品": 300, "视频": 100}},
            15: {"绘画": {"商品": 1200, "视频": 600}, "VUP周边": {"商品": 600, "视频": 600}},
        }
        for week in weeks:
            for name, channel_values in channel_gmv[week].items():
                for channel, gmv in channel_values.items():
                    channels.append(self._row(week, industry=name, channel=channel,
                                              pv=gmv * 10, uv=gmv // 10, orders=gmv // 100,
                                              buyers=gmv // 120, gmv=gmv,
                                              pvctr=(gmv // 10) / (gmv * 10)))
        self._write_csv("内容渠道数据-weekly.csv", dimensions, channels)

        goods = []
        sellers = []
        resource = []
        goods_gmv = {14: {"绘画": 300, "VUP周边": 200}, 15: {"绘画": 900, "VUP周边": 600}}
        seller_gmv = {14: {"绘画": 600, "VUP周边": 400}, 15: {"绘画": 1800, "VUP周边": 1200}}
        resource_gmv = {
            14: {"绘画": {"首页推荐": 1200, "搜索入口": 800},
                 "VUP周边": {"首页推荐": 800, "搜索入口": 600}},
            15: {"绘画": {"首页推荐": 2400, "搜索入口": 1200},
                 "VUP周边": {"首页推荐": 1800, "搜索入口": 600}},
        }
        for week in weeks:
            for name in ("绘画", "VUP周边"):
                goods.append(self._row(week, industry=name, product=f"{name}合成商品",
                                       pv=goods_gmv[week][name] * 10, uv=goods_gmv[week][name] // 10,
                                       orders=goods_gmv[week][name] // 100,
                                       buyers=goods_gmv[week][name] // 150,
                                       gmv=goods_gmv[week][name]))
                sellers.append(self._row(week, industry=name, seller=f"{name}合成商家",
                                         pv=seller_gmv[week][name] * 10, uv=seller_gmv[week][name] // 10,
                                         orders=seller_gmv[week][name] // 100,
                                         buyers=seller_gmv[week][name] // 150,
                                         gmv=seller_gmv[week][name]))
                for entry, gmv in resource_gmv[week][name].items():
                    resource.append(self._row(week, industry=name, channel="商品", entry=entry,
                                              pv=gmv * 10, uv=gmv // 10, orders=gmv // 100,
                                              buyers=gmv // 150, gmv=gmv))

        self._write_csv("行业商品明细数据-weekly.csv", dimensions, goods)
        self._write_csv("商家销售明细-weekly.csv", dimensions, sellers)
        self._write_csv("资源位二级入口数据-weekly.csv", dimensions, resource)

    def test_six_file_weekly_run_has_expected_values_and_structure(self):
        result = subprocess.run(
            [sys.executable, str(GENERATOR), "--input-dir", str(self.input_dir),
             "--output", str(self.output), "--run-id", "synthetic-weekly-test"],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        html = self.output.read_text(encoding="utf-8")

        # The aggregate fixture is W14=1,000 and W15=3,000, with 24 orders / 240 UV = 10%.
        self.assertIn("W15", html)
        self.assertIn("W14", html)
        self.assertIn("3,000.00", html)
        self.assertIn("1,000.00", html)
        self.assertIn("+200.0%", html)
        self.assertIn("10.0%", html)
        self.assertIn("绘画合成商家", html)
        self.assertIn("绘画合成商品", html)
        self.assertIn("首页推荐", html)
        self.assertIn("synthetic-weekly-test", html)

        # Contract baseline: 3 report sections, 16 charts, and 8 tables.
        self.assertEqual(html.count('class="chart-container"'), 16)
        self.assertEqual(html.count("<table>"), 8)
        for section_id in ("s1", "s2", "s3", "s4"):
            self.assertIn(f'id="{section_id}"', html)
        self.assertIn("核心数据趋势", html)
        self.assertIn("GMV 拆解", html)
        self.assertIn("流量拆解", html)
        self.assertIn("数据说明", html)
        self.assertIn("Chart.js 4.x (inline, not CDN)", html)


if __name__ == "__main__":
    unittest.main()
