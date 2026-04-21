#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
SCRIPT="$ROOT_DIR/skills/create-report/scripts/create-report-skill.sh"
BUILD_INVENTORY="$ROOT_DIR/skills/create-report/scripts/build-output-inventory.py"
TMP_DIR=$(mktemp -d)
L0_SKILL="test-create-report-l0"
L1_SKILL="test-create-report-l1"

cleanup() {
  for path in "$TMP_DIR" "$ROOT_DIR/skills/$L0_SKILL" "$ROOT_DIR/skills/$L1_SKILL"; do
    [[ ! -e "$path" ]] || rm -R "$path"
  done
}
trap cleanup EXIT

cat > "$TMP_DIR/spec.md" <<'SPEC'
# Normalized Spec

## report_goal

- report_name: Test Report

## report_outline

### S1: Core Trend
- section_id: s1
- required_metrics: GMV, 成交买家数
- charts_count: 2
- tables_count: 1

### S2: Channel Detail
- section_id: s2
- required_metrics:
  - CTR
- charts_count: 1
- tables_count: 2

## output_contract
- format: html
SPEC

cat > "$TMP_DIR/source.md" <<'SOURCE'
# Source Requirement
SOURCE

fail() {
  echo "FAIL: $1" >&2
  exit 1
}

assert_file() {
  [[ -f "$1" ]] || fail "expected file: $1"
}

assert_contains() {
  local file="$1"
  local expected="$2"
  grep -Fq -- "$expected" "$file" || fail "expected '$expected' in $file"
}

echo "[test] L0 generation writes level metadata and acceptance matrix"
bash "$SCRIPT" "$L0_SKILL" "Test Create Report L0" "$TMP_DIR/spec.md" "$TMP_DIR/source.md" L0 >/tmp/create-report-l0.out
assert_file "$ROOT_DIR/skills/$L0_SKILL/skill-manifest.yaml"
assert_file "$ROOT_DIR/skills/$L0_SKILL/assets/validation-contract.md"
assert_contains "$ROOT_DIR/skills/$L0_SKILL/skill-manifest.yaml" "declared_level: L0"
assert_contains "$ROOT_DIR/skills/$L0_SKILL/skill-manifest.yaml" "effective_level: L0"
assert_contains "$ROOT_DIR/skills/$L0_SKILL/skill-manifest.yaml" "acceptance_status: passed"
assert_contains "$ROOT_DIR/skills/$L0_SKILL/assets/validation-checklist.md" "L0 Documentation"
assert_contains "$ROOT_DIR/skills/create-report/SKILL.md" "Output"
assert_contains "$ROOT_DIR/skills/create-report/SKILL.md" "downstream report skill"
assert_contains "$ROOT_DIR/skills/create-report/SKILL.md" "sample test"
assert_contains "$ROOT_DIR/skills/create-report/SKILL.md" "Tuning Backflow"
assert_contains "$ROOT_DIR/skills/create-report/references/report-skill-contract.md" "execution design"
assert_contains "$ROOT_DIR/skills/create-report/references/report-skill-contract.md" "sample test"
assert_contains "$ROOT_DIR/skills/create-report/references/report-skill-contract.md" "tuning backflow"
assert_contains "$ROOT_DIR/skills/create-report/assets/validation-contract.md" "Adjustment Backflow"
assert_contains "$ROOT_DIR/skills/create-report/assets/review-output-template.md" "Backflow Decision"
assert_contains "$ROOT_DIR/skills/$L0_SKILL/SKILL.md" "Current level: L0 Documentation"
assert_file "$ROOT_DIR/skills/$L0_SKILL/examples/expected-output-inventory.json"
assert_file "$ROOT_DIR/skills/$L0_SKILL/scripts/validate-output-inventory.py"
assert_contains "$ROOT_DIR/skills/$L0_SKILL/assets/validation-checklist.md" "chart/table counts and required metric labels match expected-output-inventory.json"
assert_contains "$ROOT_DIR/skills/$L0_SKILL/examples/expected-output-inventory.json" '"charts": 3'
assert_contains "$ROOT_DIR/skills/$L0_SKILL/examples/expected-output-inventory.json" '"tables": 3'

echo "[test] generated downstream skill does not reference missing files"
while IFS= read -r ref; do
  [[ -e "$ROOT_DIR/skills/$L0_SKILL/$ref" ]] || fail "downstream skill references missing file: $ref"
done < <(grep -RhoE '\]\(\./[^)]+' "$ROOT_DIR/skills/$L0_SKILL" | sed 's/.*](\.\/\(.*\)$/\1/' | sort -u)

echo "[test] inventory builder rejects complex report specs with zero totals"
python3 "$BUILD_INVENTORY" --spec "$ROOT_DIR/docs/skills/工房业务交易双周报需求.md" --output "$TMP_DIR/gongfang-inventory.json"
assert_contains "$TMP_DIR/gongfang-inventory.json" '"sections": 3'
python3 - "$TMP_DIR/gongfang-inventory.json" <<'PY' || fail "complex report inventory should not have zero chart or table totals"
import json
import sys

with open(sys.argv[1], encoding="utf-8") as fh:
    totals = json.load(fh)["totals"]

if totals["charts"] == 0 or totals["tables"] == 0:
    raise SystemExit(1)
PY

echo "[test] output inventory validator catches missing charts and tables"
cat > "$TMP_DIR/expected-output-inventory.json" <<'JSON'
{
  "source_requirement": "source.md",
  "totals": {
    "sections": 2,
    "charts": 2,
    "tables": 3
  },
  "required_metrics": [
    { "metric_name": "GMV" },
    { "metric_name": "成交买家数" }
  ],
  "judgment_metrics": [
    { "metric_name": "内容效率分", "llm_judgment_allowed": true }
  ]
}
JSON
cat > "$TMP_DIR/report.html" <<'HTML'
<!DOCTYPE html>
<html><body>
  <section class="section" id="s1"><div class="chart-container"><canvas id="c1"></canvas></div><div class="table-wrap"><table><thead><tr><th>GMV</th></tr></thead></table></div></section>
  <section class="section" id="s2"></section>
</body></html>
HTML
set +e
python3 "$ROOT_DIR/skills/$L0_SKILL/scripts/validate-output-inventory.py" \
  --inventory "$TMP_DIR/expected-output-inventory.json" \
  --html "$TMP_DIR/report.html" >"$TMP_DIR/inventory.out" 2>"$TMP_DIR/inventory.err"
status=$?
set -e
[[ $status -ne 0 ]] || fail "expected output inventory validator to fail on missing views"
assert_contains "$TMP_DIR/inventory.err" "charts expected 2, found 1"
assert_contains "$TMP_DIR/inventory.err" "tables expected 3, found 1"
assert_contains "$TMP_DIR/inventory.err" "metric 成交买家数 expected, found 0"
if grep -Fq "内容效率分" "$TMP_DIR/inventory.err"; then
  fail "judgment metrics should not be required for rendered HTML presence"
fi

echo "[test] L1 generation without evidence is blocked"
set +e
bash "$SCRIPT" "$L1_SKILL" "Test Create Report L1" "$TMP_DIR/spec.md" "$TMP_DIR/source.md" L1 >"$TMP_DIR/l1.out" 2>"$TMP_DIR/l1.err"
status=$?
set -e
[[ $status -ne 0 ]] || fail "expected L1 generation without evidence to fail"
assert_contains "$TMP_DIR/l1.err" "L1 requires real runner, sample-backed execution evidence, and validation evidence"
[[ ! -d "$ROOT_DIR/skills/$L1_SKILL" ]] || fail "L1 failure should not leave target skill directory"

echo "PASS"
