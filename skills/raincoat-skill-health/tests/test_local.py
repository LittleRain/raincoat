import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/raincoat-skill-health.py'
spec = importlib.util.spec_from_file_location('health_module', SCRIPT)
health = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = health
spec.loader.exec_module(health)

class LocalUsageTest(unittest.TestCase):
    def test_missing_host_log_does_not_fabricate_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with patch.dict(os.environ, {'HERMES_HOME': str(root)}):
                result = health.import_events([root / 'skill_usage.jsonl'], root / 'state', 'hermes')
            self.assertEqual(result.diagnosis_code, 'log_path_missing')
            self.assertEqual(result.imported, 0)
            self.assertFalse(result.usage_available)
            self.assertFalse((root / 'skill_usage.jsonl').exists())

    def test_explicit_events_are_imported_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); events = root / 'skill_usage.jsonl'
            events.write_text(json.dumps({'skill_name': 'raincoat-example', 'timestamp': '2026-10-29T00:00:00Z', 'session_id': 'synthetic', 'source': 'test', 'agent': 'hermes'})+'\n')
            with patch.dict(os.environ, {'HERMES_HOME': str(root)}):
                first = health.import_events([events], root / 'state', 'hermes')
                second = health.import_events([events], root / 'state', 'hermes')
            self.assertEqual(first.imported, 1)
            self.assertEqual(second.imported, 0)
            self.assertEqual(first.diagnosis_code, 'available')
if __name__ == '__main__': unittest.main()
