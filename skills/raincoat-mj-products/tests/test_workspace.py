"""User state must live outside the skill package."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import mmiapi  # noqa: E402


class WorkspaceTests(unittest.TestCase):
    def test_env_override_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.dict(os.environ, {mmiapi.WORKSPACE_ENV: tmp}):
                self.assertEqual(mmiapi.workspace_dir(), Path(tmp).resolve())
                self.assertEqual(mmiapi.default_config_path(), Path(tmp).resolve() / "config.json")
                self.assertEqual(mmiapi.default_data_dir(), Path(tmp).resolve() / "data")
                self.assertEqual(mmiapi.default_output_dir(), Path(tmp).resolve() / "output")

    def test_default_is_outside_the_skill_folder(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop(mmiapi.WORKSPACE_ENV, None)
            workspace = mmiapi.workspace_dir()
        skill_dir = Path(__file__).resolve().parents[1]
        self.assertFalse(str(workspace).startswith(str(skill_dir)))
        self.assertIn("raincoat", str(workspace))

    def test_state_file_is_outside_the_skill_folder(self):
        skill_dir = Path(__file__).resolve().parents[1]
        self.assertFalse(Path(mmiapi.DEFAULT_STATE).is_absolute())
        self.assertNotIn(str(skill_dir), mmiapi.DEFAULT_STATE)


class CliTests(unittest.TestCase):
    def test_auth_error_becomes_exit_code_three(self):
        def boom():
            raise mmiapi.AuthRequired("no state")

        self.assertEqual(mmiapi.run_cli(boom), 3)

    def test_schema_error_becomes_exit_code_five(self):
        def boom():
            raise mmiapi.SchemaChanged("shape changed")

        self.assertEqual(mmiapi.run_cli(boom), 5)


if __name__ == "__main__":
    unittest.main()
