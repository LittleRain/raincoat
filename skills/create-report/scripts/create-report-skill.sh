#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
SKILLS_DIR="$ROOT_DIR/skills"
CREATE_REPORT_DIR="$SKILLS_DIR/create-report"
TEMPLATE_DIR="$CREATE_REPORT_DIR/assets/templates"

usage() {
  cat >&2 <<'USAGE'
Usage: create-report-skill.sh <skill-name> <skill-title> <normalized-spec-path> <source-requirement-path> [level] [--evidence-dir <dir>]

Levels:
  L0 | documentation-only    Documentation skill. Allows stubs and gap records.
  L1 | runnable              Runnable MVP. Requires real execution evidence.
  L2 | publishable           Publishable/stable. Requires L1 evidence plus browser/validation evidence.
USAGE
}

fail() {
  echo "$1" >&2
  exit 1
}

normalize_level() {
  case "$1" in
    ""|L0|l0|documentation-only) echo "L0" ;;
    L1|l1|runnable) echo "L1" ;;
    L2|l2|publishable|stable) echo "L2" ;;
    *) fail "skill-level must be L0, L1, L2, documentation-only, runnable, or publishable." ;;
  esac
}

level_label() {
  case "$1" in
    L0) echo "L0 Documentation" ;;
    L1) echo "L1 Runnable MVP" ;;
    L2) echo "L2 Publishable" ;;
  esac
}

require_file() {
  [[ -f "$1" ]] || fail "$2"
}

require_dir() {
  [[ -d "$1" ]] || fail "$2"
}

sed_escape() {
  printf '%s' "$1" | sed -e 's/[\/&]/\\&/g'
}

render_template() {
  local template="$1"
  local output="$2"
  local skill_name_escaped skill_title_escaped level_escaped level_label_escaped

  require_file "$template" "Template not found: $template"
  skill_name_escaped=$(sed_escape "$SKILL_NAME")
  skill_title_escaped=$(sed_escape "$SKILL_TITLE")
  level_escaped=$(sed_escape "$SKILL_LEVEL")
  level_label_escaped=$(sed_escape "$SKILL_LEVEL_LABEL")

  sed \
    -e "s/__SKILL_NAME__/$skill_name_escaped/g" \
    -e "s/__SKILL_TITLE__/$skill_title_escaped/g" \
    -e "s/__SKILL_LEVEL__/$level_escaped/g" \
    -e "s/__SKILL_LEVEL_LABEL__/$level_label_escaped/g" \
    "$template" > "$output"
}

validate_evidence() {
  local level="$1"
  local evidence_dir="$2"

  if [[ "$level" == "L0" ]]; then
    return 0
  fi

  [[ -n "$evidence_dir" ]] || fail "$level requires real runner, sample-backed execution evidence, and validation evidence. Provide --evidence-dir <dir> or generate L0 first."
  require_dir "$evidence_dir" "$level evidence dir not found: $evidence_dir"

  require_file "$evidence_dir/scripts/run-report.sh" "$level requires real runner, sample-backed execution evidence, and validation evidence: missing scripts/run-report.sh"
  require_dir "$evidence_dir/sample_data" "$level requires real sample data: missing sample_data/"
  require_file "$evidence_dir/output/report.html" "$level requires generated HTML evidence: missing output/report.html"
  require_file "$evidence_dir/output/run.log" "$level requires runtime log evidence: missing output/run.log"
  require_file "$evidence_dir/output/validation-report.json" "$level requires validation evidence: missing output/validation-report.json"

  if grep -Eiq 'placeholder|replace this stub|currently marked as' "$evidence_dir/scripts/run-report.sh"; then
    fail "$level requires a real runner; scripts/run-report.sh still looks like a stub."
  fi

  if [[ "$level" == "L2" ]]; then
    require_dir "$evidence_dir/output/screenshots" "L2 requires browser evidence: missing output/screenshots/"
    require_file "$evidence_dir/output/browser-validation.json" "L2 requires browser validation evidence: missing output/browser-validation.json"
  fi
}

write_stub_runner() {
  local target_dir="$1"
  cat > "$target_dir/scripts/run-report.sh" <<EOF_STUB
#!/usr/bin/env bash

set -euo pipefail

echo "This generated skill is currently marked as: $SKILL_LEVEL"
echo "This is an L0 documentation runner stub. Add real sample-backed execution evidence before promoting to L1."
exit 1
EOF_STUB
  chmod +x "$target_dir/scripts/run-report.sh"
}

copy_evidence() {
  local target_dir="$1"
  local evidence_dir="$2"

  cp "$evidence_dir/scripts/run-report.sh" "$target_dir/scripts/run-report.sh"
  chmod +x "$target_dir/scripts/run-report.sh"

  mkdir -p "$target_dir/sample_data" "$target_dir/output"
  cp -R "$evidence_dir/sample_data"/. "$target_dir/sample_data/"
  cp -R "$evidence_dir/output"/. "$target_dir/output/"

  if [[ -f "$evidence_dir/scripts/requirements.txt" ]]; then
    cp "$evidence_dir/scripts/requirements.txt" "$target_dir/scripts/requirements.txt"
  fi
}

write_manifest() {
  local target_dir="$1"
  local acceptance_date
  acceptance_date=$(date +%Y-%m-%d)

  cat > "$target_dir/skill-manifest.yaml" <<EOF_MANIFEST
version: 1
skill_name: $SKILL_NAME
skill_title: $SKILL_TITLE
declared_level: $SKILL_LEVEL
effective_level: $SKILL_LEVEL
acceptance_status: passed
acceptance_date: $acceptance_date
acceptance_evidence:
EOF_MANIFEST

  case "$SKILL_LEVEL" in
    L0)
      cat >> "$target_dir/skill-manifest.yaml" <<'EOF_MANIFEST'
  - SKILL.md
  - assets/html-contract.md
  - assets/report-outline.md
  - assets/validation-checklist.md
  - assets/validation-contract.md
  - examples/expected-output-inventory.json
blocking_gaps:
  - real sample-backed execution is not included
  - runner is a documentation stub
  - browser validation has not been run
EOF_MANIFEST
      ;;
    L1)
      cat >> "$target_dir/skill-manifest.yaml" <<'EOF_MANIFEST'
  - scripts/run-report.sh
  - sample_data/
  - output/report.html
  - output/run.log
  - output/validation-report.json
  - examples/expected-output-inventory.json
blocking_gaps: []
EOF_MANIFEST
      ;;
    L2)
      cat >> "$target_dir/skill-manifest.yaml" <<'EOF_MANIFEST'
  - scripts/run-report.sh
  - sample_data/
  - output/report.html
  - output/run.log
  - output/validation-report.json
  - output/browser-validation.json
  - output/screenshots/
  - examples/expected-output-inventory.json
blocking_gaps: []
EOF_MANIFEST
      ;;
  esac
}

if [[ $# -lt 4 ]]; then
  usage
  exit 1
fi

SKILL_NAME="$1"
SKILL_TITLE="$2"
NORMALIZED_SPEC_PATH="$3"
SOURCE_REQUIREMENT_PATH="$4"
shift 4

RAW_LEVEL="${1:-L0}"
if [[ $# -gt 0 && "$1" != --* ]]; then
  shift
fi
SKILL_LEVEL=$(normalize_level "$RAW_LEVEL")
SKILL_LEVEL_LABEL=$(level_label "$SKILL_LEVEL")
EVIDENCE_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --evidence-dir)
      [[ $# -ge 2 ]] || fail "--evidence-dir requires a directory path."
      EVIDENCE_DIR="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage
      fail "Unknown option: $1"
      ;;
  esac
done

if [[ ! "$SKILL_NAME" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  fail "Skill name must use kebab-case."
fi

require_file "$NORMALIZED_SPEC_PATH" "Normalized spec not found: $NORMALIZED_SPEC_PATH"
require_file "$SOURCE_REQUIREMENT_PATH" "Source requirement not found: $SOURCE_REQUIREMENT_PATH"
require_file "$CREATE_REPORT_DIR/scripts/build-output-inventory.py" "build-output-inventory.py not found"
require_file "$CREATE_REPORT_DIR/scripts/validate-output-inventory.py" "validate-output-inventory.py not found"
validate_evidence "$SKILL_LEVEL" "$EVIDENCE_DIR"

TARGET_DIR="$SKILLS_DIR/$SKILL_NAME"
mkdir -p "$TARGET_DIR/assets" "$TARGET_DIR/examples" "$TARGET_DIR/scripts" "$TARGET_DIR/agents"

render_template "$TEMPLATE_DIR/SKILL.md.tpl" "$TARGET_DIR/SKILL.md"
render_template "$TEMPLATE_DIR/agents.openai.yaml.tpl" "$TARGET_DIR/agents/openai.yaml"
render_template "$TEMPLATE_DIR/html-contract.md.tpl" "$TARGET_DIR/assets/html-contract.md"
render_template "$TEMPLATE_DIR/report-outline.md.tpl" "$TARGET_DIR/assets/report-outline.md"
render_template "$TEMPLATE_DIR/report-prompt.md.tpl" "$TARGET_DIR/assets/report-prompt.md"
render_template "$TEMPLATE_DIR/validation-checklist.md.tpl" "$TARGET_DIR/assets/validation-checklist.md"
render_template "$TEMPLATE_DIR/normalized-spec.md.tpl" "$TARGET_DIR/examples/normalized-spec.md"
render_template "$TEMPLATE_DIR/normalized-spec-summary.md.tpl" "$TARGET_DIR/examples/normalized-spec-summary.md"
render_template "$TEMPLATE_DIR/input_inventory.md.tpl" "$TARGET_DIR/examples/input_inventory.md"
render_template "$TEMPLATE_DIR/output-outline.html.tpl" "$TARGET_DIR/examples/output-outline.html"
render_template "$TEMPLATE_DIR/requirements.txt.tpl" "$TARGET_DIR/scripts/requirements.txt"

cp "$NORMALIZED_SPEC_PATH" "$TARGET_DIR/examples/normalized-spec-full.md"
cp "$SOURCE_REQUIREMENT_PATH" "$TARGET_DIR/examples/source-requirement.md"
cp "$CREATE_REPORT_DIR/assets/validation-contract.md" "$TARGET_DIR/assets/validation-contract.md"
cp "$CREATE_REPORT_DIR/assets/DESIGN.md" "$TARGET_DIR/assets/DESIGN.md"
cp "$CREATE_REPORT_DIR/assets/base-report.css" "$TARGET_DIR/assets/base-report.css"
cp "$CREATE_REPORT_DIR/assets/chart-defaults.js" "$TARGET_DIR/assets/chart-defaults.js"
cp "$CREATE_REPORT_DIR/scripts/validate-output-inventory.py" "$TARGET_DIR/scripts/validate-output-inventory.py"
chmod +x "$TARGET_DIR/scripts/validate-output-inventory.py"

python3 "$CREATE_REPORT_DIR/scripts/build-output-inventory.py" \
  --spec "$NORMALIZED_SPEC_PATH" \
  --output "$TARGET_DIR/examples/expected-output-inventory.json"

write_manifest "$TARGET_DIR"

if [[ "$SKILL_LEVEL" == "L0" ]]; then
  write_stub_runner "$TARGET_DIR"
else
  copy_evidence "$TARGET_DIR" "$EVIDENCE_DIR"
fi

echo "Created or updated report skill: $SKILL_NAME ($SKILL_LEVEL_LABEL)"
