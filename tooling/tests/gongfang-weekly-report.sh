#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
SKILL_DIR="$ROOT_DIR/skills/raincoat-gongfang-weekly-report"
PYTHON_BIN="${PYTHON_BIN:-python3}"

cd "$SKILL_DIR"
exec "$PYTHON_BIN" -m unittest discover -s tests -p 'test_*.py' -v
