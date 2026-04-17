#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
SCRIPT="$ROOT_DIR/skills/create-report/scripts/create-report-skill.sh"
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

- report_name: Test Report
- output_contract.format: html
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
assert_file "$ROOT_DIR/skills/$L0_SKILL/assets/acceptance-matrix.md"
assert_contains "$ROOT_DIR/skills/$L0_SKILL/skill-manifest.yaml" "declared_level: L0"
assert_contains "$ROOT_DIR/skills/$L0_SKILL/skill-manifest.yaml" "effective_level: L0"
assert_contains "$ROOT_DIR/skills/$L0_SKILL/skill-manifest.yaml" "acceptance_status: passed"
assert_contains "$ROOT_DIR/skills/$L0_SKILL/assets/validation-checklist.md" "L0 Documentation"
assert_contains "$ROOT_DIR/skills/$L0_SKILL/SKILL.md" "Current level: L0 Documentation"
assert_file "$ROOT_DIR/skills/$L0_SKILL/examples/expected-output-inventory.json"
assert_file "$ROOT_DIR/skills/$L0_SKILL/examples/semantic-contract.json"
assert_file "$ROOT_DIR/skills/$L0_SKILL/examples/table-layout-contract.json"
assert_file "$ROOT_DIR/skills/$L0_SKILL/scripts/validate-output-inventory.py"
assert_contains "$ROOT_DIR/skills/$L0_SKILL/assets/validation-checklist.md" "chart/table counts, required metric labels, required dimensions, and required text match expected-output-inventory.json"
assert_contains "$ROOT_DIR/skills/$L0_SKILL/assets/report-prompt.md" "examples/semantic-contract.json"
assert_contains "$ROOT_DIR/skills/$L0_SKILL/assets/report-prompt.md" "examples/table-layout-contract.json"

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
  ],
  "required_dimensions": [
    "行业",
    "分类"
  ],
  "required_text": [
    "南征",
    "ACG行业-出版物"
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
assert_contains "$TMP_DIR/inventory.err" "dimension 行业 expected, found 0"
assert_contains "$TMP_DIR/inventory.err" "dimension 分类 expected, found 0"
assert_contains "$TMP_DIR/inventory.err" "required text 南征 expected, found 0"
assert_contains "$TMP_DIR/inventory.err" "required text ACG行业-出版物 expected, found 0"
if grep -Fq "内容效率分" "$TMP_DIR/inventory.err"; then
  fail "judgment metrics should not be required for rendered HTML presence"
fi

echo "[test] output inventory validator catches table layout contract mismatches"
cat > "$TMP_DIR/layout-inventory.json" <<'JSON'
{
  "totals": {
    "sections": 1,
    "charts": 0,
    "tables": 2
  },
  "semantic_contract": {
    "business_terms": [
      {
        "name": "行业",
        "definition": "行业分组",
        "source_fields": ["owner_ld"],
        "hard_constraint": true
      }
    ],
    "semantic_examples": [
      {
        "input": {
          "owner_ld": "南征",
          "owner_cate": "ACG行业-出版物"
        },
        "expected": {
          "行业": "南征",
          "分类": "ACG行业-出版物"
        }
      }
    ]
  },
  "table_layout_contract": [
    {
      "section_id": "industry",
      "section": "行业拆解",
      "layout_mode": "hybrid_section_with_subtables",
      "required_tables": [
        {
          "name": "分行业汇总",
          "layout_mode": "dimension_as_rows",
          "row_dimensions": ["行业"]
        },
        {
          "name": "分行业及分类明细",
          "layout_mode": "dimension_as_rows",
          "row_dimensions": ["行业", "分类"]
        }
      ]
    }
  ]
}
JSON
cat > "$TMP_DIR/layout-report.html" <<'HTML'
<!DOCTYPE html>
<html><body>
  <section class="section" id="industry">
    <h2>行业拆解</h2>
    <h3>分行业汇总</h3>
    <div class="table-wrap"><table><thead><tr><th>行业</th><th>GMV</th></tr></thead><tbody><tr><td>南征</td><td>100</td></tr></tbody></table></div>
    <h3>分行业及分类明细</h3>
    <div class="table-wrap"><table><thead><tr><th>行业</th><th>GMV</th></tr></thead><tbody><tr><td>南征</td><td>100</td></tr></tbody></table></div>
  </section>
</body></html>
HTML
set +e
python3 "$ROOT_DIR/skills/$L0_SKILL/scripts/validate-output-inventory.py" \
  --inventory "$TMP_DIR/layout-inventory.json" \
  --html "$TMP_DIR/layout-report.html" >"$TMP_DIR/layout.out" 2>"$TMP_DIR/layout.err"
status=$?
set -e
[[ $status -ne 0 ]] || fail "expected layout contract validation to fail on missing table dimensions and semantic labels"
assert_contains "$TMP_DIR/layout.err" "section industry table 分行业及分类明细 dimension 分类 expected in table, found 0"
assert_contains "$TMP_DIR/layout.err" "semantic example expected 分类=ACG行业-出版物, found 0"

echo "[test] output inventory validator accepts matching semantic and table layout contracts"
cat > "$TMP_DIR/layout-report-pass.html" <<'HTML'
<!DOCTYPE html>
<html><body>
  <section class="section" id="industry">
    <h2>行业拆解</h2>
    <h3>分行业汇总</h3>
    <div class="table-wrap"><table><thead><tr><th>行业</th><th>GMV</th></tr></thead><tbody><tr><td>南征</td><td>100</td></tr></tbody></table></div>
    <h3>分行业及分类明细</h3>
    <div class="table-wrap"><table><thead><tr><th>行业</th><th>分类</th><th>GMV</th></tr></thead><tbody><tr><td>南征</td><td>ACG行业-出版物</td><td>100</td></tr></tbody></table></div>
  </section>
</body></html>
HTML
python3 "$ROOT_DIR/skills/$L0_SKILL/scripts/validate-output-inventory.py" \
  --inventory "$TMP_DIR/layout-inventory.json" \
  --html "$TMP_DIR/layout-report-pass.html" >"$TMP_DIR/layout-pass.out" 2>"$TMP_DIR/layout-pass.err"
assert_contains "$TMP_DIR/layout-pass.out" "output inventory validation passed"

echo "[test] L1 generation without evidence is blocked"
set +e
bash "$SCRIPT" "$L1_SKILL" "Test Create Report L1" "$TMP_DIR/spec.md" "$TMP_DIR/source.md" L1 >"$TMP_DIR/l1.out" 2>"$TMP_DIR/l1.err"
status=$?
set -e
[[ $status -ne 0 ]] || fail "expected L1 generation without evidence to fail"
assert_contains "$TMP_DIR/l1.err" "L1 requires real runner, sample-backed execution evidence, and validation evidence"
[[ ! -d "$ROOT_DIR/skills/$L1_SKILL" ]] || fail "L1 failure should not leave target skill directory"

echo "PASS"
