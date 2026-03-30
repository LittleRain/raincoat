#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TEST_TMP=$(mktemp -d)
trap 'rm -rf "$TEST_TMP"' EXIT

cp -R "$ROOT_DIR/skills" "$TEST_TMP/skills"
cp -R "$ROOT_DIR/tooling" "$TEST_TMP/tooling"
mkdir -p "$TEST_TMP/exports"

pushd "$TEST_TMP" >/dev/null

./tooling/scripts/export-skill.sh personal-kb "$TEST_TMP/exports/personal-kb"

test -f "$TEST_TMP/exports/personal-kb/SKILL.md"
test -f "$TEST_TMP/exports/personal-kb/README.md"
test -f "$TEST_TMP/exports/personal-kb/skill.json"
test -f "$TEST_TMP/exports/personal-kb/.gitignore"

grep -q 'dist' "$TEST_TMP/exports/personal-kb/.gitignore"
grep -q '"name": "personal-kb"' "$TEST_TMP/exports/personal-kb/skill.json"

if ./tooling/scripts/export-skill.sh missing-skill "$TEST_TMP/exports/missing" >/tmp/export-missing.out 2>&1; then
  echo "expected missing skill export to fail"
  exit 1
fi

popd >/dev/null
