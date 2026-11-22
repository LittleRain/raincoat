#!/usr/bin/env python3
"""Consolidate a primary judge directory with targeted repair passes.

A repair pass writes the same record ids as the primary pass. This tool builds a
read-only view: one row per id, taking the completed row when any pass has one and
otherwise keeping the failed row, so the audit trail (attempts, raw/) stays in the
original directories. Nothing is deleted or rewritten in the sources.
"""
import argparse
import json
import shutil
from pathlib import Path


def rows(directory):
    path = directory / "judges.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--merge", type=Path, action="append", default=[])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.primary / "private-mapping.json", out / "private-mapping.json")

    merged = {}
    order = []
    for directory in [args.primary, *args.merge]:
        for row in rows(directory):
            key = row["id"]
            if key not in merged:
                merged[key] = row
                order.append(key)
                continue
            if row["status"] == "completed" and merged[key]["status"] != "completed":
                merged[key] = row
    with (out / "judges.jsonl").open("w") as handle:
        for key in order:
            handle.write(json.dumps(merged[key], ensure_ascii=False) + "\n")
    completed = sum(1 for row in merged.values() if row["status"] == "completed")
    print(f"rows: {len(merged)}; completed: {completed}; failed: {len(merged) - completed}")


if __name__ == "__main__":
    main()
