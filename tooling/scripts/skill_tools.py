#!/usr/bin/env python3
"""Portable Raincoat scaffolding, structural checks and release packaging."""
import argparse
import json
import re
import shutil
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
NAME = re.compile(r"raincoat-[a-z0-9]+(?:-[a-z0-9]+)*\Z")
FIELDS = {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}
DIRECTORIES = {"scripts", "references", "assets", "examples", "agents", "tests"}
FILES = {"SKILL.md", "README.md", "LICENSE", "LICENSE.txt", "LICENSE.md", ".gitignore",
         "skill.json", "plugin.json", "requirements.txt", "pyproject.toml", "package.json",
         "package-lock.json", "uv.lock", "config.example.yaml", ".env.example"}
IGNORED = {"__pycache__", ".git", ".venv", "venv", "node_modules", "input", "output",
           "dist", "coverage", ".pytest_cache", ".DS_Store"}
DATA_SUFFIXES = {".pyc", ".pyo", ".xlsx", ".xls", ".csv", ".mp4", ".mov", ".mp3",
                 ".sqlite", ".sqlite3", ".db"}


def metadata(folder):
    text = (folder / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"\A---\r?\n(.*?)\r?\n---(?:\r?\n|$)", text, re.S)
    if not match:
        raise ValueError("SKILL.md needs YAML frontmatter")
    data = yaml.safe_load(match[1])
    if not isinstance(data, dict):
        raise ValueError("frontmatter must be a mapping")
    return data, text


def check(folder, release=False):
    errors = []
    try:
        data, text = metadata(folder)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        return [str(exc)]
    for key in sorted(set(data) - FIELDS):
        errors.append(f"unsupported frontmatter field: {key}")
    name = data.get("name")
    if not isinstance(name, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or len(name) > 64:
        errors.append("name must be kebab-case, 1–64 characters")
    if name != folder.name:
        errors.append("name must match directory")
    desc = data.get("description")
    if not isinstance(desc, str) or not 1 <= len(desc.strip()) <= 1024:
        errors.append("description must contain 1–1024 characters")
    if "metadata" in data and (not isinstance(data["metadata"], dict) or
            any(not isinstance(k, str) or not isinstance(v, str) for k, v in data["metadata"].items())):
        errors.append("metadata keys and values must be strings")
    if "compatibility" in data and (not isinstance(data["compatibility"], str) or
            not 1 <= len(data["compatibility"]) <= 500):
        errors.append("compatibility must contain 1–500 characters")
    if release:
        if not isinstance(name, str) or not NAME.fullmatch(name):
            errors.append("release name must start with raincoat-")
        for required in ("README.md",):
            if not (folder / required).is_file():
                errors.append(f"missing {required}")
        if not any((folder / f).is_file() for f in ("LICENSE", "LICENSE.md", "LICENSE.txt")):
            errors.append("missing bundled license")
        meta = data.get("metadata", {})
        if not isinstance(meta, dict) or not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-z0-9.-]+)?", str(meta.get("version", ""))):
            errors.append("metadata.version must be a quoted semantic version")
        for path in folder.rglob("*.md"):
            if any(part in IGNORED for part in path.relative_to(folder).parts):
                continue
            if path.is_symlink():
                errors.append(f"symlink: {path.relative_to(folder)}")
                continue
            body = path.read_text(encoding="utf-8")
            if re.search(r"/Users/|/home/|[A-Za-z]:\\", body):
                errors.append(f"machine-specific path in {path.relative_to(folder)}")
            if re.search(r"\[TODO:|your-skill-name|Your Skill Name", body):
                errors.append(f"unfinished scaffold in {path.relative_to(folder)}")
            for target in re.findall(r"\]\(([^\s)]+)\)", body):
                if re.match(r"[a-zA-Z][\w+.-]*:", target) or target.startswith("#"):
                    continue
                resolved = (path.parent / target.split("#")[0]).resolve()
                if not resolved.is_relative_to(folder.resolve()) or not resolved.exists():
                    errors.append(f"missing or external local reference in {path.relative_to(folder)}: {target}")
        for manifest in ("skill.json", "plugin.json"):
            if (folder / manifest).is_file():
                try:
                    info = json.loads((folder / manifest).read_text(encoding="utf-8"))
                    if not isinstance(info, dict) or info.get("name") != name or info.get("version") != meta.get("version"):
                        errors.append(f"{manifest} name/version differs from SKILL.md")
                except (ValueError, AttributeError):
                    errors.append(f"invalid {manifest}")
    return errors


def resolve_skill(name):
    if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
        raise ValueError("invalid skill name")
    folder = ROOT / "skills" / name
    if folder.is_symlink() or not folder.is_dir():
        raise ValueError(f"Skill not found or symlink: {name}")
    return folder


def create(name):
    if not NAME.fullmatch(name) or len(name) > 64:
        raise ValueError("name must use raincoat-xxx, kebab-case, at most 64 characters")
    target = ROOT / "skills" / name
    if target.exists():
        raise ValueError(f"Skill already exists: {name}")
    shutil.copytree(ROOT / "skills/_templates/basic", target)
    for path in target.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace("your-skill-name", name).replace("Your Skill Name", name), encoding="utf-8")
    print(f"Created {target}; complete TODOs before release")


def package(folder, destination, draft=False):
    errors = check(folder, release=not draft)
    if errors:
        raise ValueError("; ".join(errors))
    destination = destination.resolve()
    if destination.is_relative_to(ROOT.resolve()):
        raise ValueError("export destination must be outside repository")
    if destination.exists() and (not destination.is_dir() or any(destination.iterdir())):
        raise ValueError("destination must be an empty directory")
    included = []
    skipped = []
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder)
        # Local runtime trees may contain links to private inputs. They are not
        # package candidates: skip without reading or following their targets.
        if any(part in IGNORED for part in rel.parts):
            if path.is_file() or path.is_symlink():
                skipped.append(str(rel))
            continue
        if path.is_symlink():
            raise ValueError(f"symlinks cannot be exported: {rel}")
        if not path.is_file():
            continue
        if (any(p in IGNORED for p in rel.parts) or path.suffix.lower() in DATA_SUFFIXES or
                any(p.startswith(".env") and p != ".env.example" for p in rel.parts) or
                (rel.parts[0] not in DIRECTORIES and str(rel) not in FILES)):
            skipped.append(str(rel))
        else:
            included.append((path, rel))
    # Validate the filtered package before writing the requested destination.
    import tempfile
    with tempfile.TemporaryDirectory(prefix="raincoat-export-") as temporary:
        staged = Path(temporary) / folder.name
        staged.mkdir()
        for path, rel in included:
            (staged / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, staged / rel)
        errors = check(staged, release=not draft)
        if errors:
            raise ValueError("filtered package invalid: " + "; ".join(errors))
        ignore = staged / ".gitignore"
        existing = ignore.read_text(encoding="utf-8") if ignore.exists() else ""
        ignore.write_text(existing.rstrip() + "\n\n# Raincoat local artifacts\n__pycache__/\n*.py[cod]\n.venv/\nnode_modules/\ninput/\noutput/\n.env\n.env.*\n!.env.example\n", encoding="utf-8")
        shutil.copytree(staged, destination, dirs_exist_ok=True)
    print(f"Exported {folder.name} to {destination}")
    for rel in skipped:
        print(f"Excluded: {rel}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("new")
    new.add_argument("name")
    lint = commands.add_parser("lint")
    lint.add_argument("names", nargs="*")
    lint.add_argument("--release", action="store_true")
    export = commands.add_parser("export")
    export.add_argument("name")
    export.add_argument("destination", type=Path)
    export.add_argument("--draft", action="store_true", help="structural checks only; package is not release-approved")
    args = parser.parse_args()
    try:
        if args.command == "new":
            create(args.name)
        elif args.command == "export":
            package(resolve_skill(args.name), args.destination, args.draft)
        else:
            folders = [resolve_skill(n) for n in args.names] if args.names else sorted(
                p for p in (ROOT / "skills").iterdir() if p.is_dir() and not p.name.startswith("_"))
            failed = False
            for folder in folders:
                errors = check(folder, args.release)
                failed |= bool(errors)
                print(f"{folder.name}: " + ("; ".join(errors) if errors else "OK"))
            return int(failed)
    except (ValueError, OSError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
