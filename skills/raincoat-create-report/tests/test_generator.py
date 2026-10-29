import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/create_report_skill.py'
class GeneratorTest(unittest.TestCase):
    def test_independent_generation_and_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            spec = root / 'spec.md'
            spec.write_text('# Spec\n## report_outline\n### S1: Trend\n- section_id: s1\n- required_metrics: GMV\n- charts_count: 2\n- tables_count: 1\n')
            source = root / 'source.md'; source.write_text('# Requirement')
            cmd = [sys.executable, str(SCRIPT), 'raincoat-test-report', 'Test', str(spec), str(source)]
            result = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            target = root / 'skills/raincoat-test-report'
            inventory = json.loads((target / 'examples/expected-output-inventory.json').read_text())
            self.assertEqual(inventory['totals']['charts'], 2)
            self.assertEqual(inventory['totals']['tables'], 1)
            self.assertNotEqual(subprocess.run([sys.executable, str(target / 'scripts/run_report.py')], capture_output=True).returncode, 0)
            self.assertNotEqual(subprocess.run(cmd, cwd=root, capture_output=True).returncode, 0)
            bad = cmd.copy(); bad[2] = 'raincoat-missing-evidence'; bad += ['L1']
            self.assertNotEqual(subprocess.run(bad, cwd=root, capture_output=True).returncode, 0)
            self.assertFalse((root / 'skills/raincoat-missing-evidence').exists())
    def test_inventory_validator_rejects_missing_metrics_and_charts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inventory = root / 'inventory.json'
            inventory.write_text(json.dumps({'totals': {'sections': 1, 'charts': 2, 'tables': 1}, 'required_metrics': [{'metric_name': 'GMV'}]}))
            report = root / 'report.html'; report.write_text('<html><section class="section" id="s1"></section></html>')
            result = subprocess.run([sys.executable, str(SCRIPT.parent / 'validate-output-inventory.py'), '--inventory', str(inventory), '--html', str(report)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('charts expected 2, found 0', result.stderr)
            self.assertIn('metric GMV expected, found 0', result.stderr)
if __name__ == '__main__': unittest.main()
