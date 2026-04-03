#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
INPUT_DIR=""
OUTPUT_DIR=""
RUN_ID=""

usage() {
  echo "Usage: $0 --input-dir <dir> --output-dir <dir> [--run-id <id>]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --input-dir)
      INPUT_DIR="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --run-id)
      RUN_ID="${2:-}"
      shift 2
      ;;
    *)
      usage
      exit 1
      ;;
  esac
done

if [[ -z "$INPUT_DIR" || -z "$OUTPUT_DIR" ]]; then
  usage
  exit 1
fi

if [[ ! -d "$INPUT_DIR" ]]; then
  echo "Input directory not found: $INPUT_DIR" >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"

PYTHON_BIN="${PYTHON_BIN:-python3}"
OUTPUT_HTML="$OUTPUT_DIR/report.html"
LOG_PATH="$OUTPUT_DIR/run.log"

{
  echo "run_id=${RUN_ID:-manual-run}"
  echo "input_dir=$INPUT_DIR"
  echo "output_html=$OUTPUT_HTML"
  "$PYTHON_BIN" -u "$ROOT_DIR/generate_report.py" --dir "$INPUT_DIR" --output "$OUTPUT_HTML"
} | tee "$LOG_PATH"
