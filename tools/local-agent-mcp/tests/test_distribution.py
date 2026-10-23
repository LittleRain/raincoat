"""Distribution tests must not call models, read credentials or change real client configs."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from raincoat_agent_mcp import client_config, updates, dependencies

class DistributionTests(unittest.TestCase):
    def test_setup_uses_module_entry_instead_of_source_checkout(self):
        text=client_config.codex_config('[mcp_servers.other]\ncommand="keep"\n','/uv/env/bin/python',['-m','raincoat_agent_mcp','mcp'])
        self.assertIn('"-m", "raincoat_agent_mcp", "mcp"',text)
        self.assertNotIn('bridge.py',text)
    def test_update_rejects_non_uv_install(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(sys,'prefix',tmp):
            with self.assertRaisesRegex(RuntimeError,'uv tool'):
                updates.update()
    def test_helper_is_discoverable_without_deepseek_harness(self):
        with tempfile.TemporaryDirectory() as tmp,patch('pathlib.Path.home',return_value=Path(tmp)):
            lib=Path(tmp)/'.local/share/raincoat-agent-mcp/workbuddy/node_modules/dsh-workbuddy-connect/lib'
            lib.mkdir(parents=True);(lib/'host-heartbeat-example.js').write_text('')
            self.assertEqual(dependencies.helper_path(),str(lib/'host-heartbeat-example.js'))
    def test_update_refuses_active_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            from raincoat_agent_mcp import shared
            with patch.object(shared,'STATE',Path(tmp)):
                directory=shared.job_dir('a'*32)
                shared.atomic_json(directory/'state.json',{'status':'running'})
                with self.assertRaisesRegex(RuntimeError,'执行中'):
                    updates.ensure_idle()
    def test_pypi_unpublished_has_actionable_error(self):
        from urllib.error import HTTPError
        with patch('urllib.request.urlopen',side_effect=HTTPError('https://pypi.org',404,'not found',{},None)):
            with self.assertRaisesRegex(RuntimeError,'尚未发布'):
                updates.check_update()

if __name__=='__main__':unittest.main()
