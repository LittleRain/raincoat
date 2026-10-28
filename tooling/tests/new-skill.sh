#!/usr/bin/env bash
set -euo pipefail
TEST_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
cd "$TEST_DIR"
exec python3 -m unittest test_skill_tools.TestScaffold
