#!/usr/bin/env bash
set -euo pipefail

URL=""
URL_FILE=""
OUT_DIR="/tmp"
WAIT_MS="12000"
OPEN_CHROME="1"

CAPTURE_SCRIPT_DEFAULT="/Users/raincai/Documents/GitHub/raincoat/tools/wecom_capture_opendoc.js"
CAPTURE_SCRIPT="${WXURL2MD_CAPTURE_SCRIPT:-$CAPTURE_SCRIPT_DEFAULT}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)
      URL="${2:-}"
      shift 2
      ;;
    --out-dir)
      OUT_DIR="${2:-/tmp}"
      shift 2
      ;;
    --url-file)
      URL_FILE="${2:-}"
      shift 2
      ;;
    --wait-ms)
      WAIT_MS="${2:-12000}"
      shift 2
      ;;
    --no-open)
      OPEN_CHROME="0"
      shift 1
      ;;
    *)
      echo "Unknown arg: $1" >&2
      echo "Usage: $0 (--url <wecom_doc_url> | --url-file <file>) [--out-dir /tmp] [--wait-ms 12000] [--no-open]" >&2
      exit 1
      ;;
  esac
done

if [[ -n "$URL" && -n "$URL_FILE" ]]; then
  echo "Provide either --url or --url-file, not both." >&2
  exit 1
fi

if [[ -z "$URL" && -z "$URL_FILE" ]]; then
  echo "Usage: $0 (--url <wecom_doc_url> | --url-file <file>) [--out-dir /tmp] [--wait-ms 12000] [--no-open]" >&2
  exit 1
fi

if [[ ! -f "$CAPTURE_SCRIPT" ]]; then
  echo "Capture script not found: $CAPTURE_SCRIPT" >&2
  echo "Set WXURL2MD_CAPTURE_SCRIPT to override path." >&2
  exit 1
fi

if [[ "$OPEN_CHROME" == "1" ]]; then
  osascript -e 'tell application "Google Chrome" to activate' >/dev/null
fi

run_one() {
  local one_url="$1"
  if [[ "$OPEN_CHROME" == "1" ]]; then
    osascript -e "tell application \"Google Chrome\" to open location \"$one_url\"" >/dev/null
  fi
  node "$CAPTURE_SCRIPT" \
    --url "$one_url" \
    --out-dir "$OUT_DIR" \
    --wait-ms "$WAIT_MS"
}

if [[ -n "$URL" ]]; then
  run_one "$URL"
  DOC_ID=$(echo "$URL" | sed -n 's#.*\/doc\/\(w3_[A-Za-z0-9]*\).*#\1#p')
  PREFIX="wecom_${DOC_ID:-doc}"
  echo "Recommended AI input: ${OUT_DIR}/${PREFIX}_for_ai.md"
  echo "Verification source: ${OUT_DIR}/${PREFIX}_keyframe.json"
  exit 0
fi

if [[ ! -f "$URL_FILE" ]]; then
  echo "URL file not found: $URL_FILE" >&2
  exit 1
fi

REPORT_FILE="${OUT_DIR}/wxurl2md_batch_report_$(date +%Y%m%d_%H%M%S).txt"
touch "$REPORT_FILE"

index=0
while IFS= read -r raw || [[ -n "$raw" ]]; do
  line="$(echo "$raw" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')"
  [[ -z "$line" ]] && continue
  [[ "$line" =~ ^# ]] && continue
  index=$((index + 1))

  echo "[${index}] START ${line}"
  if run_one "$line"; then
    DOC_ID=$(echo "$line" | sed -n 's#.*\/doc\/\(w3_[A-Za-z0-9]*\).*#\1#p')
    PREFIX="wecom_${DOC_ID:-doc}"
    echo "[${index}] OK ${line}" | tee -a "$REPORT_FILE"
    echo "  - AI: ${OUT_DIR}/${PREFIX}_for_ai.md" | tee -a "$REPORT_FILE"
    echo "  - VERIFY: ${OUT_DIR}/${PREFIX}_keyframe.json" | tee -a "$REPORT_FILE"
  else
    echo "[${index}] FAIL ${line}" | tee -a "$REPORT_FILE"
  fi
done < "$URL_FILE"

echo "Batch report: $REPORT_FILE"
