from pathlib import Path
import sys
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import install

class MigrationTests(unittest.TestCase):
    def test_codex_preserves_other_sections_and_is_idempotent(self):
        old='model = "example"\n[mcp_servers.bitto]\ncommand = "old"\nargs = []\n[mcp_servers.other]\ncommand = "untouched"\n'
        new=install.codex_config(old,'python','/runtime/bridge.py')
        self.assertIn('[mcp_servers.other]\ncommand = "untouched"',new)
        self.assertEqual(new,install.codex_config(new,'python','/runtime/bridge.py'))
    def test_old_and_new_nested_env_tables_do_not_survive_migration(self):
        old='[mcp_servers.bitto]\ncommand="old"\n[mcp_servers.bitto.env]\nFOO="old"\n[mcp_servers."local_agents".env] # old nested environment\nBAR="old"\n[mcp_servers.other.env]\nKEEP="yes"\n'
        new=install.codex_config(old,'python','/runtime/bridge.py')
        self.assertNotIn('FOO=',new);self.assertNotIn('BAR=',new)
        self.assertIn('KEEP="yes"',new)
        self.assertEqual(new,install.codex_config(new,'python','/runtime/bridge.py'))
    def test_dsh_preserves_neighbor_insert_and_is_idempotent(self):
        old='- id: locale\n  config:\n    preference: zh\n- insert:\n    - id: bitto-agent-bridge\n      config:\n        serverName: bitto\n    - id: other\n      config:\n        serverName: unrelated\n'
        new=install.dsh_config(old,'python','/runtime/bridge.py')
        self.assertIn('    - id: other\n      config:\n        serverName: unrelated\n',new)
        self.assertEqual(new,install.dsh_config(new,'python','/runtime/bridge.py'))
if __name__=='__main__':unittest.main()
