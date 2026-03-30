#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SKILLS_DIR="$ROOT_DIR/skills"

required_files=(SKILL.md README.md skill.json)
status=0

for skill_dir in "$SKILLS_DIR"/*; do
  [[ -d "$skill_dir" ]] || continue

  skill_name=$(basename "$skill_dir")
  [[ "$skill_name" == _templates ]] && continue

  for required_file in "${required_files[@]}"; do
    if [[ ! -f "$skill_dir/$required_file" ]]; then
      echo "Missing $required_file in $skill_name" >&2
      status=1
    fi
  done
done

if [[ $status -eq 0 ]]; then
  echo "All skills passed basic validation."
fi

exit "$status"
