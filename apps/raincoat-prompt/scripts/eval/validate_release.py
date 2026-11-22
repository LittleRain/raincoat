#!/usr/bin/env python3
"""v0.3 release gate: version consistency plus slot/profile data integrity.

Replaces the v0.2 blind-judge release manifest. Behaviour is now checked by
scripts/eval/structure_check.py, which renders the real binary; this gate only
guards the data the renderer depends on and the version it ships under.
"""
import json
import plistlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESOURCES = ROOT / "Sources" / "PromptCore" / "Resources"
SLOTS = {"role", "goal", "material", "acceptance", "boundary", "format"}
SCENES = {"writing", "report", "meeting", "data", "research", "plan", "code"}
TIERS = {"frontier", "mid", "restricted"}


def validate(root=ROOT):
    profiles = json.loads((root / "Sources/PromptCore/Resources/model-profiles.json").read_text())
    scenes = json.loads((root / "Sources/PromptCore/Resources/scene-slots.json").read_text())
    app_version = plistlib.loads((root / "assets/Info.plist").read_bytes())["CFBundleShortVersionString"]

    assert profiles["version"] == scenes["version"] == app_version, \
        "profiles / slots / Info.plist versions must match"

    ids = {p["id"] for p in profiles["profiles"]}
    assert {"gpt", "claude", "bitto", "workbuddy", "deepseek"} <= ids, f"missing profiles: {ids}"
    for profile in profiles["profiles"]:
        assert profile["tier"] in TIERS, profile["id"]
        assert profile["sentence_budget"] > 0 and profile["char_budget"] > 0, profile["id"]
        assert profile["order"] and set(profile["order"]) <= SLOTS | {"constraint"}, profile["id"]
        assert profile["source"].startswith("https://"), profile["id"]
        if profile["official"]:
            assert "官方" in profile["notes"] or "official" in profile["source"], profile["id"]

    assert set(scenes["slots"]) == SLOTS
    scene_ids = {s["id"] for s in scenes["scenes"]}
    assert scene_ids == SCENES, f"scene set mismatch: {scene_ids ^ SCENES}"
    for scene in scenes["scenes"]:
        assert set(scene["blocking"]) <= SLOTS, scene["id"]
        assert set(scene["optional"]) <= SLOTS, scene["id"]
        assert scene["blocking"], scene["id"]
        for slot in scene["blocking"]:
            if slot == "goal":
                continue
            assert scene["defaults"].get(slot), f"{scene['id']} blocking slot {slot} needs a default"

    workbuddy = next(p for p in profiles["profiles"] if p["id"] == "workbuddy")
    assert "no_tools_boundary" in (workbuddy.get("extra") or []), \
        "workbuddy must keep the tool-boundary sentence"


if __name__ == "__main__":
    validate()
    print("Validated v0.3 profile/scene data and version consistency")
