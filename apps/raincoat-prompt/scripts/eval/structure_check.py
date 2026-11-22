#!/usr/bin/env python3
"""v0.3 structural regression: slots, budget, plain text, determinism, questions.

Runs the real app binary (--v3-json) over the whole case bank and every target.
No model calls: this checks the generator, not model answers.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BIN = ROOT / "dist" / "Raincoat Prompt.app" / "Contents" / "MacOS" / "RaincoatPrompt"
CASES = ROOT / "docs" / "evaluation-cases.json"
PROFILES = ROOT / "Sources" / "PromptCore" / "Resources" / "model-profiles.json"
TARGETS = ["chatGPT", "claude", "codex", "bitto", "workBuddy", "deepseek"]
MARKERS = [r"#", r"\*\*", r"<\/?[a-zA-Z][^>]*>", r"(?m)^\s*\d+\.\s"]
PLACEHOLDERS = ["TODO", "待补充", "[请填写]", "TBD"]


def compose(text, target):
    proc = subprocess.run([str(BIN), "--v3-json", target], input=text,
                          capture_output=True, text=True, timeout=60)
    if proc.returncode != 0:
        return None, f"exit {proc.returncode}: {proc.stderr[:200]}"
    try:
        return json.loads(proc.stdout), None
    except json.JSONDecodeError as error:
        return None, f"bad json: {error}"


def added_parts(text, original):
    parts = text.split(original)
    return [p for p in parts if p]


def check(case, target, profile):
    draft, error = compose(case["input"], target)
    if error:
        return [f"{case['id']}/{target}: {error}"]
    failures = []
    text = draft["text"]
    if not text.strip() or not text.endswith("。"):
        failures.append(f"{case['id']}/{target}: text empty or missing final period")
    for part in added_parts(text, case["input"]):
        for pattern in MARKERS:
            if re.search(pattern, part):
                failures.append(f"{case['id']}/{target}: marker {pattern!r} in added text")
                break
        for token in PLACEHOLDERS:
            if token in part:
                failures.append(f"{case['id']}/{target}: placeholder {token}")
        if re.search(r"\d", part):
            failures.append(f"{case['id']}/{target}: added text contains a number")
    if len(draft["questions"]) > 3:
        failures.append(f"{case['id']}/{target}: {len(draft['questions'])} questions > 3")
    if draft["addedCharacters"] > profile["char_budget"]:
        failures.append(f"{case['id']}/{target}: {draft['addedCharacters']} chars > {profile['char_budget']}")
    if draft["addedSentences"] > profile["sentence_budget"]:
        failures.append(f"{case['id']}/{target}: {draft['addedSentences']} sentences > {profile['sentence_budget']}")
    if profile["tier"] == "frontier" and "你是" in text:
        failures.append(f"{case['id']}/{target}: frontier profile got a role sentence")
    if target == "workBuddy" and "没有工具执行能力" not in text:
        failures.append(f"{case['id']}/{target}: missing no-tools boundary")
    for question in draft["questions"]:
        if question["slot"] not in draft["missing"]:
            failures.append(f"{case['id']}/{target}: question for a slot not marked missing")
        if not question["defaultValue"]:
            failures.append(f"{case['id']}/{target}: question without a default value")
    again, error = compose(case["input"], target)
    if error or again != draft:
        failures.append(f"{case['id']}/{target}: not deterministic")
    return failures


SCENE_PROBES = [
    ("writing", "把这段通知改得客气一点，明天发全员"),
    ("report", "写个本周周报，老板要看"),
    ("meeting", "整理一下今天的会议纪要"),
    ("data", "这两周退货率是不是变高了，问题主要出在哪"),
    ("research", "调研一下竞品定价"),
    ("plan", "设计一个为期两周的试点方案"),
    ("code", "支付回调重试会不会重复扣款"),
]


def check_scene_coverage(scenes):
    failures = []
    for expected, text in SCENE_PROBES:
        for target in TARGETS:
            draft, error = compose(text, target)
            if error:
                failures.append(f"scene/{expected}/{target}: {error}")
                continue
            if draft["scene"] != expected:
                failures.append(f"scene/{expected}/{target}: detected {draft['scene']}")
    return failures


SLOT_HINTS = {
    "role": ["你是", "作为"],
    "material": ["材料", "附件", "数据", "口径", "预算", "周期", "代码", "报错", "记录", "报价",
                 "访谈", "约束", "人手", "期间", "分母"],
    "acceptance": ["验收", "标准", "怎么算", "可复算", "通过", "测试", "检查", "复算"],
    "boundary": ["不要", "别", "禁止", "不得", "未知", "待确认", "不确定"],
    "format": ["字", "句", "格式", "表格", "JSON", "json", "列表", "一行", "段落", "篇幅"],
}


def check_slot_coverage(case, target, scene_spec):
    draft, error = compose(case["input"], target)
    if error:
        return []
    failures = []
    for slot in scene_spec["blocking"]:
        if slot == "goal" or slot in draft["missing"]:
            continue
        if any(hint in case["input"] for hint in SLOT_HINTS.get(slot, [])):
            continue  # the user already supplied this slot in their own words
        default = scene_spec["defaults"].get(slot, "")
        if default and default not in draft["text"]:
            failures.append(f"{case['id']}/{target}: blocking slot {slot} neither rendered nor asked")
    return failures


def main():
    profiles = {p["id"]: p for p in json.loads(PROFILES.read_text())["profiles"]}
    mapping = {"chatGPT": "gpt", "codex": "gpt", "claude": "claude",
               "bitto": "bitto", "workBuddy": "workbuddy", "deepseek": "deepseek"}
    scenes = json.loads((ROOT / "Sources" / "PromptCore" / "Resources" / "scene-slots.json").read_text())
    scene_by_id = {s["id"]: s for s in scenes["scenes"]}
    cases = json.loads(CASES.read_text())["cases"]
    failures = check_scene_coverage(scene_by_id)
    for case in cases:
        for target in TARGETS:
            failures += check(case, target, profiles[mapping[target]])
            draft, error = compose(case["input"], target)
            if not error:
                failures += check_slot_coverage(case, target, scene_by_id[draft["scene"]])
    lines = ["# v0.3 结构回归", "",
             f"题目 {len(cases)} × 目标 {len(TARGETS)} = {len(cases) * len(TARGETS)} 次本地渲染", ""]
    if failures:
        lines.append(f"失败 {len(failures)} 项：")
        lines += [f"- {item}" for item in failures[:50]]
        (ROOT / ".build" / "v03").mkdir(parents=True, exist_ok=True)
        (ROOT / ".build" / "v03" / "structure-report.md").write_text("\n".join(lines) + "\n")
        print("\n".join(lines[:20]))
        return 1
    lines.append("全部通过：槽位、预算、无标记、无占位符、无编造数字、追问 ≤3、两次渲染一致。")
    (ROOT / ".build" / "v03").mkdir(parents=True, exist_ok=True)
    (ROOT / ".build" / "v03" / "structure-report.md").write_text("\n".join(lines) + "\n")
    print(lines[-1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
