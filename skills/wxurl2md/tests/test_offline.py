import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / 'scripts/wecom_capture_opendoc.js'
ARCHIVER = ROOT / 'scripts/wecom_archive.py'


class OfflineTests(unittest.TestCase):
    def test_cli_help_and_invalid_options_do_not_need_browser(self):
        with tempfile.TemporaryDirectory() as cwd:
            result = subprocess.run(['node', str(CAPTURE), '--help'], cwd=cwd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for args in [[], ['--unknown'], ['--wait-ms', 'NaN'], ['--url', 'file:///private/doc']]:
                failed = subprocess.run(['node', str(CAPTURE), *args], cwd=cwd, capture_output=True, text=True)
                self.assertNotEqual(failed.returncode, 0)

    def test_capture_parameters_and_local_module_can_load_without_playwright(self):
        script = '''const {parseArgs}=require(process.argv[1]);
const p=parseArgs(['node','script','--url','https://doc.weixin.qq.com/doc/w3_fake','--python',process.argv[2],'--wait-ms','12']);
console.log(JSON.stringify(p));'''
        result = subprocess.run(['node', '-e', script, str(CAPTURE), sys.executable], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        options = json.loads(result.stdout)
        self.assertEqual(options['python'], sys.executable)
        self.assertEqual(options['waitMs'], 12)
        self.assertTrue(Path(options['profileDir']).is_absolute())

    def test_archive_preserves_raw_and_numeric_table_values_from_foreign_cwd(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            draft = base / 'decoded.md'
            original = '# Synthetic document\n\nSource bytes: 12345 / 12.5% / ￥678.90\n'
            draft.write_text(original, encoding='utf-8')
            structured = base / 'tables.md'
            structured.write_text('| 指标 | 数值 |\n| --- | --- |\n| 合成订单 | 12345 |\n| 合成转化率 | 12.5% |\n', encoding='utf-8')
            output = base / 'nested/output'
            result = subprocess.run([sys.executable, str(ARCHIVER), '--draft', str(draft), '--structured', str(structured), '--out-dir', str(output)], cwd=d, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((output / 'wecom_doc_raw_snapshot.md').read_bytes(), draft.read_bytes())
            ai = (output / 'wecom_doc_ai_accuracy.md').read_text(encoding='utf-8')
            for value in ['12345', '12.5%']:
                self.assertIn(value, ai)
            self.assertTrue((output / 'wecom_doc_anchor_check.md').is_file())

    def test_archive_missing_input_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / 'output'
            result = subprocess.run([sys.executable, str(ARCHIVER), '--draft', str(Path(d)/'missing'), '--out-dir', str(output)], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())

    @unittest.skipUnless(shutil.which('bash'), 'optional Bash wrapper')
    def test_batch_reports_failure_and_handles_space_in_script_path(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            capture = base / 'fake capture.js'
            capture.write_text("process.exit(process.argv.includes('https://doc.weixin.qq.com/doc/w3_fail') ? 1 : 0);", encoding='utf-8')
            urls = base / 'urls.txt'
            urls.write_text('# comment\n\nhttps://doc.weixin.qq.com/doc/w3_ok\nhttps://doc.weixin.qq.com/doc/w3_fail\n', encoding='utf-8')
            env = dict(os.environ, WXURL2MD_CAPTURE_SCRIPT=str(capture))
            result = subprocess.run(['bash', str(ROOT / 'scripts/run-wecom-doc.sh'), '--url-file', str(urls), '--out-dir', str(base/'new output'), '--no-open'], cwd=d, env=env, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('[1] OK', result.stdout)
            self.assertIn('[2] FAIL', result.stdout)


if __name__ == '__main__':
    unittest.main()
