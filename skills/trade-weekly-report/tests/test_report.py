import importlib.util
from pathlib import Path
import re
import json
import pandas as pd
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fixture', ROOT / 'tests/generate_fixture.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class ReportTest(unittest.TestCase):
    def test_legacy_contract_retained_with_synthetic_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            fixture.generate(base)
            names = {'整体.xlsx': '整体数据.csv', '行业.xlsx': '区分行业.csv',
                     '流量.xlsx': '分行业x流量渠道.csv', '内容类型.xlsx': '分行业x内容类型.csv'}
            for original, name in names.items():
                frame = pd.read_excel(base / original).rename(columns={'订单数': '支付订单数', '买家数': '支付订单买家数'})
                frame.to_csv(base / name, index=False)
            pd.DataFrame({'商家ID': [4]}).to_csv(base / '头部UPlist.csv', index=False)
            output = base / 'legacy.html'
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/legacy/generate_report.py'), '--dir', d, '-o', str(output)], cwd=d, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            html = output.read_text(encoding='utf-8')
            data, _ = json.JSONDecoder().raw_decode(html.split('var D=', 1)[1])
            self.assertEqual([x['GMV'] for x in data['s1']['xd']], [15000, 30000])

    def test_missing_files_return_error_without_installing_or_creating_output(self):
        with tempfile.TemporaryDirectory() as d:
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/run_report.py'), '--input-dir', d, '--output-dir', str(Path(d)/'output')], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('missing input files', result.stderr)
            self.assertFalse((Path(d)/'output').exists())

    def test_standalone_report_with_known_gmv_and_growth(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            fixture.generate(base / 'input')
            output = base / 'nested/report.html'
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/run_report.py'), '--input-dir', str(base/'input'), '--output', str(output)], cwd=d, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            html = output.read_text(encoding='utf-8')
            for title in ['核心数据趋势', '行业拆解', '小店商家', '流量渠道', '成交体裁']:
                self.assertIn(title, html)
            # Fixture shop GMV is 1k+2k+3k+4k+5k in W15 and doubles in W16.
            self.assertRegex(html, r'label: \'小店\', data: \[15000\.0, 30000\.0\]')
            self.assertIn('+100.0%', html)
            self.assertIn('合成店铺1', html)


if __name__ == '__main__':
    unittest.main()
