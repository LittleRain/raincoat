#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TEST_TMP=$(mktemp -d)
trap 'rm -rf "$TEST_TMP"' EXIT

cp -R "$ROOT_DIR/skills" "$TEST_TMP/skills"
cp -R "$ROOT_DIR/tooling" "$TEST_TMP/tooling"

pushd "$TEST_TMP" >/dev/null

./tooling/scripts/new-skill.sh sample-skill >/tmp/new-skill.out

test -f "$TEST_TMP/skills/sample-skill/SKILL.md"
test -f "$TEST_TMP/skills/sample-skill/README.md"
test -f "$TEST_TMP/skills/sample-skill/skill.json"

grep -q 'name: sample-skill' "$TEST_TMP/skills/sample-skill/SKILL.md"
grep -q '# Sample Skill' "$TEST_TMP/skills/sample-skill/README.md"
grep -q '"name": "sample-skill"' "$TEST_TMP/skills/sample-skill/skill.json"
grep -q '"title": "Sample Skill"' "$TEST_TMP/skills/sample-skill/skill.json"

if ./tooling/scripts/new-skill.sh sample-skill >/tmp/new-skill-duplicate.out 2>&1; then
  echo "expected duplicate skill creation to fail"
  exit 1
fi

popd >/dev/null
