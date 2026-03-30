#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SKILLS_DIR="$ROOT_DIR/skills"

usage() {
  echo "Usage: ./tooling/scripts/export-skill.sh <skill-name> <destination-dir>" >&2
}

write_gitignore() {
  cat >"$1/.gitignore" <<'EOF'
.DS_Store
dist
coverage
.env
.env.*
EOF
}

if [[ $# -ne 2 ]]; then
  usage
  exit 1
fi

SKILL_NAME="$1"
DEST_DIR="$2"
SOURCE_DIR="$SKILLS_DIR/$SKILL_NAME"

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "Skill not found: $SKILL_NAME" >&2
  exit 1
fi

if [[ -e "$DEST_DIR" ]] && [[ -n "$(find "$DEST_DIR" -mindepth 1 -maxdepth 1 2>/dev/null)" ]]; then
  echo "Destination directory must be empty: $DEST_DIR" >&2
  exit 1
fi

mkdir -p "$DEST_DIR"
cp -R "$SOURCE_DIR"/. "$DEST_DIR"
write_gitignore "$DEST_DIR"

echo "Exported $SKILL_NAME to $DEST_DIR"
