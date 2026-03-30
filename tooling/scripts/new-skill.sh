#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TEMPLATE_DIR="$ROOT_DIR/skills/_templates/basic"
SKILLS_DIR="$ROOT_DIR/skills"

usage() {
  echo "Usage: ./tooling/scripts/new-skill.sh <skill-name>" >&2
}

to_title() {
  printf '%s\n' "$1" | perl -pe 's/-/ /g; s/\b([a-z])/\U$1/g'
}

replace_placeholders() {
  local file_path="$1"
  local skill_name="$2"
  local skill_title="$3"

  SKILL_NAME_REPLACE="$skill_name" SKILL_TITLE_REPLACE="$skill_title" \
    perl -0pi -e 's/your-skill-name/$ENV{SKILL_NAME_REPLACE}/g; s/Your Skill Name/$ENV{SKILL_TITLE_REPLACE}/g' \
    "$file_path"
}

if [[ $# -ne 1 ]]; then
  usage
  exit 1
fi

SKILL_NAME="$1"

if [[ ! "$SKILL_NAME" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  echo "Skill name must use kebab-case." >&2
  exit 1
fi

if [[ ! -d "$TEMPLATE_DIR" ]]; then
  echo "Template directory not found: $TEMPLATE_DIR" >&2
  exit 1
fi

TARGET_DIR="$SKILLS_DIR/$SKILL_NAME"

if [[ -e "$TARGET_DIR" ]]; then
  echo "Skill already exists: $SKILL_NAME" >&2
  exit 1
fi

SKILL_TITLE=$(to_title "$SKILL_NAME")

mkdir -p "$TARGET_DIR"
cp -R "$TEMPLATE_DIR"/. "$TARGET_DIR"

replace_placeholders "$TARGET_DIR/SKILL.md" "$SKILL_NAME" "$SKILL_TITLE"
replace_placeholders "$TARGET_DIR/README.md" "$SKILL_NAME" "$SKILL_TITLE"
replace_placeholders "$TARGET_DIR/skill.json" "$SKILL_NAME" "$SKILL_TITLE"

echo "Created skill: $SKILL_NAME"
