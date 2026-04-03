#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)
TEST_TMP=$(mktemp -d)
trap 'rm -rf "$TEST_TMP"' EXIT

INPUT_DIR="$ROOT_DIR/docs/周报生成器_v3/docs"
OUTPUT_DIR="$TEST_TMP/output"
mkdir -p "$OUTPUT_DIR"

"$ROOT_DIR/skills/trade-weekly-report/scripts/run-report.sh" \
  --input-dir "$INPUT_DIR" \
  --output-dir "$OUTPUT_DIR" \
  --run-id test-run

test -f "$OUTPUT_DIR/report.html"
grep -q "核心数据趋势" "$OUTPUT_DIR/report.html"
grep -q "行业拆解" "$OUTPUT_DIR/report.html"
grep -q "小店商家" "$OUTPUT_DIR/report.html"
grep -q "流量渠道" "$OUTPUT_DIR/report.html"
grep -q "成交体裁" "$OUTPUT_DIR/report.html"
