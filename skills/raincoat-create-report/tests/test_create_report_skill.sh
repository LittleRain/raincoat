#!/usr/bin/env bash
set -euo pipefail
SKILL_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
exec "${PYTHON_BIN:-python3}" -m unittest discover -s "$SKILL_DIR/tests" -p 'test_*.py'
