#!/usr/bin/env python3
"""Strict stdlib-only validation for the fixed evaluation case bank."""
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "docs" / "evaluation-cases.json"
SCHEMA = ROOT / "docs" / "evaluation-cases.schema.json"
SCENES = ("调研", "数据分析", "开发", "写方案", "写报告")
SPLITS = {"pilot", "development", "holdout"}
TOP_KEYS = {"version", "common_instruction", "cases", "pilot", "extended_pilot", "scoring"}
CASE_KEYS = {"id", "scene", "subscene", "input", "original", "optimized", "materials", "checks", "core_checks", "bonus_check", "critical_errors", "split"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    data = json.loads(DATA.read_text(encoding="utf-8"))
    require(schema.get("$schema", "").endswith("2020-12/schema"), "schema must declare JSON Schema 2020-12")
    require(set(data) == TOP_KEYS, f"top-level fields mismatch: {sorted(set(data) ^ TOP_KEYS)}")
    require(isinstance(data["version"], str) and data["version"], "version must be nonempty")
    require(isinstance(data["common_instruction"], str) and data["common_instruction"], "common_instruction must be nonempty")
    cases = data["cases"]
    require(isinstance(cases, list) and len(cases) >= 40, "at least 40 cases are required")
    ids = [c.get("id") for c in cases]
    require(all(isinstance(i, str) and i for i in ids), "every case needs a nonempty id")
    require(len(ids) == len(set(ids)), "case ids must be unique")
    scene_counts = Counter()
    holdout_counts = Counter()
    for index, case in enumerate(cases):
        label = f"case[{index}] {case.get('id', '<missing id>')}"
        require(set(case) == CASE_KEYS, f"{label}: fields mismatch: {sorted(set(case) ^ CASE_KEYS)}")
        require(case["scene"] in SCENES, f"{label}: unknown scene {case['scene']!r}")
        require(isinstance(case["subscene"], str) and case["subscene"].strip(), f"{label}: subscene required")
        require(case["split"] in SPLITS, f"{label}: invalid split {case['split']!r}")
        for key in ("input", "original", "optimized", "bonus_check"):
            require(isinstance(case[key], str) and case[key].strip(), f"{label}: {key} must be nonempty text")
        require(case["input"] == case["original"], f"{label}: original must preserve the input compatibility field")
        for key in ("materials", "checks", "core_checks", "critical_errors"):
            require(isinstance(case[key], list), f"{label}: {key} must be an array")
            require(all(isinstance(x, str) and x.strip() for x in case[key]), f"{label}: {key} contains an empty/non-string item")
        require(case["materials"], f"{label}: materials must not be empty")
        require(len(case["checks"]) == 4, f"{label}: checks must contain exactly 3 core and 1 bonus")
        require(len(case["core_checks"]) == 3, f"{label}: core_checks must contain exactly 3 items")
        require(case["core_checks"] == case["checks"][:3], f"{label}: core_checks must match checks[0:3]")
        require(case["bonus_check"] == case["checks"][3], f"{label}: bonus_check must match checks[3]")
        require(case["critical_errors"], f"{label}: at least one critical error required")
        scene_counts[case["scene"]] += 1
        if case["split"] == "holdout":
            holdout_counts[case["scene"]] += 1
    for scene in SCENES:
        require(scene_counts[scene] >= 8, f"scene {scene!r} needs at least 8 cases, got {scene_counts[scene]}")
    require(sum(holdout_counts.values()) >= 8, f"at least 8 holdout cases required, got {sum(holdout_counts.values())}")
    id_set = set(ids)
    for key in ("pilot", "extended_pilot"):
        values = data[key]
        minimum = 4 if key == "pilot" else 10
        require(isinstance(values, list) and len(values) >= minimum, f"{key} must have at least {minimum} case references")
        require(len(values) == len(set(values)), f"{key} references must be unique")
        unknown = set(values) - id_set
        require(not unknown, f"{key} has unknown references: {sorted(unknown)}")
        by_id = {c["id"]: c for c in cases}
        chosen = [by_id[i] for i in values]
        require(all(c["split"] != "holdout" for c in chosen), f"{key} cannot include holdout cases")
        if key == "extended_pilot":
            chosen_scenes = Counter(c["scene"] for c in chosen)
            for scene in SCENES:
                require(chosen_scenes[scene] >= 2, f"{key} needs at least 2 non-holdout cases for {scene!r}")
    scoring = data["scoring"]
    require(set(scoring) == {"core_checks", "bonus_checks", "decision_order"}, "scoring fields mismatch")
    require(scoring["core_checks"] == 3 and scoring["bonus_checks"] == 1, "scoring must declare 3 core and 1 bonus check")
    require(scoring["decision_order"] == ["critical_failure", "core_passes", "bonus_passes"], "unexpected scoring decision order")
    print(f"Validated {len(cases)} cases; scenes: " + ", ".join(f"{s}={scene_counts[s]}" for s in SCENES))
    print(f"Holdouts: {sum(holdout_counts.values())}; pilot={len(data['pilot'])}; extended_pilot={len(data['extended_pilot'])}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
        print(f"evaluation cases validation failed: {exc}", file=sys.stderr)
        sys.exit(1)
