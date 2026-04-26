#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TEST_TMP=$(mktemp -d)
trap 'rm -rf "$TEST_TMP"' EXIT

test -f "$ROOT_DIR/skills/skill-health/agents/openai.yaml"
grep -q 'display_name: "Skill Health"' "$ROOT_DIR/skills/skill-health/agents/openai.yaml"
grep -q 'short_description: "Audit local agent skills"' "$ROOT_DIR/skills/skill-health/agents/openai.yaml"
grep -q 'Use \$skill-health' "$ROOT_DIR/skills/skill-health/agents/openai.yaml"
grep -q '^## Usage$' "$ROOT_DIR/skills/skill-health/SKILL.md"
grep -q 'Use `doctor` for the normal audit path' "$ROOT_DIR/skills/skill-health/SKILL.md"
grep -q -- '--host hermes' "$ROOT_DIR/skills/skill-health/SKILL.md"
grep -q -- '--agent hermes' "$ROOT_DIR/skills/skill-health/SKILL.md"
grep -q '~/.hermes/skill_usage.jsonl' "$ROOT_DIR/skills/skill-health/SKILL.md"

SKILLS_ROOT="$TEST_TMP/skills"
STATE_DIR="$TEST_TMP/state"
REPORT_DIR="$TEST_TMP/report"
mkdir -p "$SKILLS_ROOT/report-alpha" "$SKILLS_ROOT/report-beta" "$SKILLS_ROOT/weak-trigger" "$SKILLS_ROOT/_templates/basic" "$STATE_DIR" "$REPORT_DIR"

cat >"$SKILLS_ROOT/report-alpha/SKILL.md" <<'SKILL'
---
name: report-alpha
description: Use when generating weekly HTML reports from Excel or CSV business data.
---

# Report Alpha
SKILL

cat >"$SKILLS_ROOT/report-beta/SKILL.md" <<'SKILL'
---
name: report-beta
description: Use when generating weekly HTML reports from CSV or Excel business metrics.
---

# Report Beta
SKILL

cat >"$SKILLS_ROOT/weak-trigger/SKILL.md" <<'SKILL'
---
name: weak-trigger
description: Helps with things.
---

# Weak Trigger
SKILL

cat >"$SKILLS_ROOT/_templates/basic/SKILL.md" <<'SKILL'
---
name: your-skill-name
description: Short description of what this skill helps an agent do.
---

# Your Skill Name
SKILL

cat >"$TEST_TMP/events.jsonl" <<'JSONL'
{"skill_name":"report-alpha","scenario":"weekly report from csv","timestamp":"2026-04-20T10:00:00Z","agent":"openclaw","session_id":"s1","outcome_signal":"completed","source":"fixture"}
{"skill_name":"missing-skill","scenario":"unknown","timestamp":"2026-04-21T10:00:00Z","agent":"hermes","session_id":"s2","outcome_signal":"unknown","source":"fixture"}
JSONL

"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$STATE_DIR" \
  scan --root "$SKILLS_ROOT" >"$TEST_TMP/scan.json"

test -f "$STATE_DIR/index.json"
grep -q '"name": "report-alpha"' "$STATE_DIR/index.json"
grep -q '"host": "custom"' "$STATE_DIR/index.json"
grep -q '"adapter_status"' "$STATE_DIR/index.json"
grep -q '"root_status": "available"' "$STATE_DIR/index.json"
if grep -q '"name": "your-skill-name"' "$STATE_DIR/index.json"; then
  echo "template skills should not be indexed"
  exit 1
fi

"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$STATE_DIR" \
  import --agent openclaw --events "$TEST_TMP/events.jsonl" >"$TEST_TMP/import.json"

test -f "$STATE_DIR/events.jsonl"
grep -q '"skill_name": "report-alpha"' "$STATE_DIR/events.jsonl"

"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$STATE_DIR" \
  import --agent openclaw --events "$TEST_TMP/events.jsonl" >"$TEST_TMP/import-again.json"

if [[ $(grep -c '"skill_name": "report-alpha"' "$STATE_DIR/events.jsonl") -ne 1 ]]; then
  echo "duplicate imports should not append the same usage event twice"
  exit 1
fi

"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$STATE_DIR" \
  report --stale-days 1 --format json >"$TEST_TMP/report.json"

grep -q '"usage_available": true' "$TEST_TMP/report.json"
grep -q '"kind": "duplicate_candidate"' "$TEST_TMP/report.json"
grep -q '"skill_name": "weak-trigger"' "$TEST_TMP/report.json"
grep -q '"kind": "weak_trigger"' "$TEST_TMP/report.json"
grep -q '"kind": "unused_skill"' "$TEST_TMP/report.json"
grep -q '"finding_id": "duplicate_candidate:report-alpha:report-beta"' "$TEST_TMP/report.json"

"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$STATE_DIR" \
  report --stale-days 1 --format md --language zh >"$TEST_TMP/report.zh.md"

grep -q "Skill 健康报告" "$TEST_TMP/report.zh.md"
grep -q "建议" "$TEST_TMP/report.zh.md"
grep -q "Finding ID" "$TEST_TMP/report.zh.md"

"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$STATE_DIR" \
  feedback --finding-id duplicate_candidate:report-alpha:report-beta --verdict suppressed --note "fixture duplicate is expected" >"$TEST_TMP/feedback-suppressed.json"

test -f "$STATE_DIR/feedback.jsonl"
grep -q '"verdict": "suppressed"' "$STATE_DIR/feedback.jsonl"

"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$STATE_DIR" \
  report --stale-days 1 --format json >"$TEST_TMP/report-suppressed.json"

grep -q '"findings_suppressed": 1' "$TEST_TMP/report-suppressed.json"
grep -q '"suppressed_findings"' "$TEST_TMP/report-suppressed.json"
if grep -q '"finding_id": "duplicate_candidate:report-alpha:report-beta"' "$TEST_TMP/report-suppressed.json" \
  && grep -B2 -A8 '"finding_id": "duplicate_candidate:report-alpha:report-beta"' "$TEST_TMP/report-suppressed.json" | grep -q '"findings"'; then
  echo "suppressed finding should not remain in active findings"
  exit 1
fi

"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$STATE_DIR" \
  feedback --finding-id weak_trigger:weak-trigger --verdict confirmed --note "description is vague" >"$TEST_TMP/feedback-confirmed.json"

"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$STATE_DIR" \
  report --stale-days 1 --format json >"$TEST_TMP/report-confirmed.json"

grep -q '"finding_id": "weak_trigger:weak-trigger"' "$TEST_TMP/report-confirmed.json"
grep -q '"feedback_status": "confirmed"' "$TEST_TMP/report-confirmed.json"

printf '{bad json\n' >>"$STATE_DIR/feedback.jsonl"
"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$STATE_DIR" \
  report --stale-days 1 --format json >"$TEST_TMP/report-malformed-feedback.json"
grep -q '"feedback_applied"' "$TEST_TMP/report-malformed-feedback.json"

"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$STATE_DIR" \
  doctor --root "$SKILLS_ROOT" --events "$TEST_TMP/events.jsonl" --output-dir "$REPORT_DIR" >/tmp/skill-health-doctor.out

test -f "$STATE_DIR/review-state.json"
grep -q '"last_doctor_at"' "$STATE_DIR/review-state.json"
grep -q '"last_active_findings"' "$STATE_DIR/review-state.json"

test -f "$REPORT_DIR/skill-health-report.md"
test -f "$REPORT_DIR/skill-health-report.en.md"
test -f "$REPORT_DIR/skill-health-report.zh.md"
test -f "$REPORT_DIR/skill-health-report.json"
grep -q "Skill Health Report" "$REPORT_DIR/skill-health-report.md"
grep -q "Skill Health Report" "$REPORT_DIR/skill-health-report.en.md"
grep -q "Skill 健康报告" "$REPORT_DIR/skill-health-report.zh.md"
grep -q "duplicate_candidate" "$REPORT_DIR/skill-health-report.md"

MISSING_STATE_DIR="$TEST_TMP/missing-state"
MISSING_REPORT_DIR="$TEST_TMP/missing-report"
mkdir -p "$MISSING_STATE_DIR" "$MISSING_REPORT_DIR"

"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$MISSING_STATE_DIR" \
  doctor --root "$SKILLS_ROOT" --events "$TEST_TMP/does-not-exist.jsonl" --output-dir "$MISSING_REPORT_DIR" >"$TEST_TMP/missing-doctor.json"

grep -q '"usage_available": false' "$MISSING_REPORT_DIR/skill-health-report.json"
grep -q '"usage_unavailable"' "$MISSING_REPORT_DIR/skill-health-report.json"
grep -q "Usage data unavailable" "$MISSING_REPORT_DIR/skill-health-report.en.md"
grep -q "使用数据不可用" "$MISSING_REPORT_DIR/skill-health-report.zh.md"

HERMES_STATE_DIR="$TEST_TMP/hermes-state"
mkdir -p "$HERMES_STATE_DIR"

"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$HERMES_STATE_DIR" \
  import --agent hermes >"$TEST_TMP/hermes-import.json"

grep -q '.hermes/skill_usage.jsonl' "$TEST_TMP/hermes-import.json"
grep -q '.codex/skill_usage.jsonl' "$TEST_TMP/hermes-import.json"

REVIEW_STATE_DIR="$TEST_TMP/review-state"
mkdir -p "$REVIEW_STATE_DIR"

"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$REVIEW_STATE_DIR" \
  review-status >"$TEST_TMP/review-status-never.json"

grep -q '"should_prompt": true' "$TEST_TMP/review-status-never.json"
grep -q '"reason": "never_run"' "$TEST_TMP/review-status-never.json"

"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$REVIEW_STATE_DIR" \
  review-snooze --days 7 >"$TEST_TMP/review-snooze.json"

"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$REVIEW_STATE_DIR" \
  review-status >"$TEST_TMP/review-status-snoozed.json"

grep -q '"should_prompt": false' "$TEST_TMP/review-status-snoozed.json"
grep -q '"reason": "snoozed"' "$TEST_TMP/review-status-snoozed.json"

"$ROOT_DIR/skills/skill-health/scripts/skill-health" \
  --state-dir "$REVIEW_STATE_DIR" \
  review-done >"$TEST_TMP/review-done.json"

grep -q '"last_feedback_at"' "$REVIEW_STATE_DIR/review-state.json"

echo "skill-health tests passed."
