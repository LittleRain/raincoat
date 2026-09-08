#!/usr/bin/env python3
"""Check local prerequisites without exposing authentication data."""
from __future__ import annotations
import shutil
import subprocess
import sys

def run(label: str, args: list[str]) -> tuple[bool, str]:
    if not shutil.which(args[0]):
        return False, f"{label}: missing ({args[0]})"
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"{label}: unavailable ({type(exc).__name__})"
    lines = (result.stdout or result.stderr).strip().splitlines()
    return result.returncode == 0, f"{label}: {lines[0] if lines else 'available'}"

def main() -> int:
    checks = [run("ffmpeg", ["ffmpeg", "-version"]), run("ffprobe", ["ffprobe", "-version"])]
    if shutil.which("mmx"):
        checks += [run("mmx", ["mmx", "--version"]), run("mmx auth", ["mmx", "auth", "status"]), run("mmx quota", ["mmx", "quota"])]
    else:
        checks.append((False, "mmx: missing (optional unless provider=minimax-cli)"))
    for ok, message in checks:
        print(("OK  " if ok else "WARN ") + message)
    return 0 if all(ok for ok, _ in checks[:2]) else 1

if __name__ == "__main__":
    sys.exit(main())
