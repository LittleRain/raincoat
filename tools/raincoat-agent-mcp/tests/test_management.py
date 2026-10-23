import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from raincoat_agent_mcp import management, dependencies, updates, __version__

class ManagementTests(unittest.TestCase):
    def test_setup_preview_does_not_create_config(self):
        with tempfile.TemporaryDirectory() as tmp,patch('pathlib.Path.home',return_value=Path(tmp)):
            result=management.setup(client='codex')
            self.assertFalse(result['apply']);self.assertFalse((Path(tmp)/'.codex').exists())
    def test_auto_setup_does_not_create_uninstalled_profiles(self):
        with tempfile.TemporaryDirectory() as tmp,patch('pathlib.Path.home',return_value=Path(tmp)):
            (Path(tmp)/'.codex').mkdir()
            result=management.setup()
            self.assertEqual(len(result['files']),1);self.assertIn('.codex',result['files'][0])
            self.assertFalse((Path(tmp)/'.dsh').exists())
    def test_generic_setup_is_standard_mcp_json(self):
        result=management.setup(client='generic')
        self.assertEqual(result['mcpServers']['local_agents']['args'],['-m','raincoat_agent_mcp','mcp'])
    def test_unsupported_platform_is_explicit(self):
        with patch.object(sys,'platform','win32'):
            result=management.doctor()
            self.assertFalse(result['healthy']);self.assertIn('macOS',result['error'])
    def test_supported_node_range_matches_pinned_helper(self):
        for version,expected in [('v22.18.0',False),('v22.19.0',True),('v23.1.0',False),('v24.0.0',True)]:
            with self.subTest(version=version),patch.object(dependencies,'node_binary',return_value='/node'),patch('subprocess.run',return_value=subprocess.CompletedProcess([],0,version,'')):
                self.assertEqual(dependencies.node_check()['available'],expected)
    def test_removed_cached_node_falls_back_to_new_path(self):
        with patch.dict(os.environ,{'LOCAL_AGENT_NODE':''}),patch.object(dependencies,'settings',return_value={'node':'/removed/node'}),patch('shutil.which',return_value='/new/node'),patch.object(Path,'is_file',lambda path:str(path)=='/new/node'):
            self.assertEqual(dependencies.node_binary(),'/new/node')
    def test_missing_helper_does_not_fall_back_to_dsh(self):
        with tempfile.TemporaryDirectory() as tmp,patch('pathlib.Path.home',return_value=Path(tmp)),patch.dict(os.environ,{'WORKBUDDY_CREDENTIAL_HELPER':''}):
            root=Path(tmp)/'.dsh/profiles/desktop/node_modules/dsh-workbuddy-connect/lib'
            root.mkdir(parents=True);(root/'host-heartbeat-example.js').write_text('')
            self.assertIsNone(dependencies.helper_path())
    def test_update_check_compares_versions(self):
        response=io.BytesIO(json.dumps({'info':{'version':'0.2.0'}}).encode())
        with patch('urllib.request.urlopen',return_value=response):
            self.assertTrue(updates.check_update()['update_available'])
    def test_offline_update_check_has_clear_error(self):
        with patch('urllib.request.urlopen',side_effect=OSError('offline')):
            with self.assertRaisesRegex(RuntimeError,'当前安装仍可使用'):updates.check_update()
    def test_version_rollback_uses_explicit_spec(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(sys,'prefix',tmp),patch.object(updates,'ensure_idle'),patch('shutil.which',return_value='/uv'):
            (Path(tmp)/'uv-receipt.toml').write_text('')
            results=[subprocess.CompletedProcess([],0),subprocess.CompletedProcess([],0,'0.0.9\n','')]
            with patch('subprocess.run',side_effect=results) as run:
                result=updates.update(target_version='0.0.9')
                self.assertEqual(result['installed_version'],'0.0.9')
                self.assertEqual(run.call_args_list[0].args[0],['/uv','tool','install','--force','--python',getattr(sys,'_base_executable',sys.executable),'raincoat-agent-mcp==0.0.9'])
    def test_failed_upgrade_does_not_report_success(self):
        with tempfile.TemporaryDirectory() as tmp,patch.object(sys,'prefix',tmp),patch.object(updates,'ensure_idle'),patch('shutil.which',return_value='/uv'):
            (Path(tmp)/'uv-receipt.toml').write_text('')
            with patch('subprocess.run',return_value=subprocess.CompletedProcess([],1)):
                with self.assertRaisesRegex(RuntimeError,'升级未成功'):updates.update()

if __name__=='__main__':unittest.main()
