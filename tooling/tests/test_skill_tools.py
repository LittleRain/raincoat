import importlib.util
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/skill_tools.py"
spec = importlib.util.spec_from_file_location("skill_tools", SCRIPT)
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "repo"
        self.original_root = tools.ROOT
        self.addCleanup(setattr, tools, "ROOT", self.original_root)
        tools.ROOT = self.root
        shutil.copytree(self.original_root / "skills/_templates/basic", self.root / "skills/_templates/basic")
        self.skill = self.root / "skills/raincoat-example"
        self.skill.mkdir()
        (self.skill / "SKILL.md").write_text('''---
name: raincoat-example
description: Summarize meeting text when a user asks for meeting minutes.
license: MIT
metadata:
  version: "1.0.0"
---
Summarize only the provided text.
''', encoding="utf-8")
        (self.skill / "README.md").write_text("# Example\n", encoding="utf-8")
        (self.skill / "LICENSE").write_text("Test fixture only\n", encoding="utf-8")


class TestScaffold(Fixture):
    def test_new_skill_is_minimal_and_cannot_be_released_unfinished(self):
        tools.create("raincoat-new-tool")
        created = self.root / "skills/raincoat-new-tool"
        self.assertEqual(tools.check(created), [])
        self.assertTrue(tools.check(created, release=True))
        self.assertEqual({p.name for p in created.iterdir()}, {"README.md", "SKILL.md"})

    def test_invalid_names_and_duplicates_do_not_overwrite(self):
        for name in ("example", "../raincoat-outside", "raincoat-", "raincoat-a--b", "raincoat-" + "a" * 60):
            with self.subTest(name=name), self.assertRaises(ValueError):
                tools.create(name)
        original = (self.skill / "SKILL.md").read_bytes()
        with self.assertRaises(ValueError):
            tools.create(self.skill.name)
        self.assertEqual((self.skill / "SKILL.md").read_bytes(), original)

    def test_cli_runs_without_shell(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "lint", "raincoat-meeting-summary", "--release"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class TestValidation(Fixture):
    def test_release_allows_standard_compatibility_and_optional_manifests(self):
        entry = self.skill / "SKILL.md"
        entry.write_text(entry.read_text().replace("license: MIT", "license: MIT\ncompatibility: Requires a text-capable agent"))
        self.assertEqual(tools.check(self.skill, True), [])

    def test_rejects_broken_external_and_machine_specific_references(self):
        for text in ("[missing](references/missing.md)", "[outside](../outside.md)", "Run /Users/test/script.py"):
            with self.subTest(text=text):
                (self.skill / "README.md").write_text(text)
                self.assertTrue(tools.check(self.skill, True))

    def test_rejects_blank_description_name_mismatch_and_manifest_drift(self):
        entry = self.skill / "SKILL.md"
        original = entry.read_text()
        for text in (original.replace("description: Summarize meeting text when a user asks for meeting minutes.", 'description: ""'),
                     original.replace("name: raincoat-example", "name: other-name")):
            entry.write_text(text)
            self.assertTrue(tools.check(self.skill))
        entry.write_text(original)
        (self.skill / "plugin.json").write_text(json.dumps({"name": "old-name", "version": "1.0.0"}))
        self.assertTrue(tools.check(self.skill, True))


class TestExport(Fixture):
    def test_excluded_runtime_symlink_never_enters_package(self):
        private = self.base / "private-input.txt"
        private.write_text("private")
        (self.skill / "output").mkdir()
        try:
            (self.skill / "output/input-link.md").symlink_to(private)
        except OSError:
            self.skipTest("symlinks unavailable on this host")
        destination = self.base / "export"
        tools.package(self.skill, destination)
        self.assertFalse((destination / "output").exists())
        self.assertEqual(private.read_text(), "private")

    def test_package_excludes_runtime_data_and_preserves_resources_and_ignore(self):
        for name in ("scripts/run.py", "references/rules.md", "examples/summary.md", "assets/template.html", ".env.example", ".gitignore", "skill-manifest.yaml"):
            path = self.skill / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("custom-rule\n")
        for name in ("scripts/__pycache__/run.pyc", "input/private.json", "output/report.html", "report.html", "data.xlsx", "references/data.csv", ".env", ".env.production", "node_modules/a.js"):
            path = self.skill / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("private")
        dest = self.base / "export"
        tools.package(self.skill, dest)
        self.assertTrue((dest / "assets/template.html").is_file())
        self.assertTrue((dest / "skill-manifest.yaml").is_file())
        self.assertTrue((dest / ".env.example").is_file())
        self.assertIn("custom-rule", (dest / ".gitignore").read_text())
        self.assertFalse(any("private" in p.read_text() for p in dest.rglob("*") if p.is_file()))
        self.assertEqual(tools.check(dest.rename(self.base / self.skill.name), True), [])

    def test_filter_cannot_silently_break_a_reference(self):
        (self.skill / "README.md").write_text("[data](data.xlsx)")
        (self.skill / "data.xlsx").write_text("private")
        dest = self.base / "export"
        with self.assertRaises(ValueError):
            tools.package(self.skill, dest)
        self.assertFalse(dest.exists())

    def test_symlinks_and_nonempty_destinations_are_not_overwritten(self):
        dest = self.base / "export"
        dest.mkdir()
        sentinel = dest / "keep.txt"
        sentinel.write_text("keep")
        with self.assertRaises(ValueError):
            tools.package(self.skill, dest)
        self.assertEqual(sentinel.read_text(), "keep")
        try:
            (self.skill / "link").symlink_to(sentinel)
        except OSError:
            self.skipTest("symlinks unavailable on this host")
        with self.assertRaises(ValueError):
            tools.package(self.skill, self.base / "other")

    def test_rejects_repository_destination_and_traversal(self):
        with self.assertRaises(ValueError):
            tools.package(self.skill, self.root / "export")
        with self.assertRaises(ValueError):
            tools.resolve_skill("../outside")


if __name__ == "__main__":
    unittest.main()
