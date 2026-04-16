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

echo "[test] L1 generation without evidence is blocked"
set +e
bash "$SCRIPT" "$L1_SKILL" "Test Create Report L1" "$TMP_DIR/spec.md" "$TMP_DIR/source.md" L1 >"$TMP_DIR/l1.out" 2>"$TMP_DIR/l1.err"
status=$?
set -e
[[ $status -ne 0 ]] || fail "expected L1 generation without evidence to fail"
assert_contains "$TMP_DIR/l1.err" "L1 requires real runner, sample-backed execution evidence, and validation evidence"
[[ ! -d "$ROOT_DIR/skills/$L1_SKILL" ]] || fail "L1 failure should not leave target skill directory"

echo "PASS"
