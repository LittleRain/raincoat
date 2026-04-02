#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
SKILLS_DIR="$ROOT_DIR/skills"

usage() {
  echo "Usage: $0 <skill-name> <skill-title> <normalized-spec-path> <source-requirement-path> [skill-level]" >&2
}

if [[ $# -lt 4 || $# -gt 5 ]]; then
  usage
  exit 1
fi

SKILL_NAME="$1"
SKILL_TITLE="$2"
NORMALIZED_SPEC_PATH="$3"
SOURCE_REQUIREMENT_PATH="$4"
SKILL_LEVEL="${5:-documentation-only}"
TARGET_DIR="$SKILLS_DIR/$SKILL_NAME"

if [[ ! "$SKILL_NAME" =~ ^[a-z0-9]+(-[a-z0-9]+)*$ ]]; then
  echo "Skill name must use kebab-case." >&2
  exit 1
fi

if [[ "$SKILL_LEVEL" != "documentation-only" && "$SKILL_LEVEL" != "runnable" ]]; then
  echo "skill-level must be documentation-only or runnable." >&2
  exit 1
fi

mkdir -p "$TARGET_DIR" "$TARGET_DIR/assets" "$TARGET_DIR/examples" "$TARGET_DIR/scripts"

cat > "$TARGET_DIR/SKILL.md" <<EOF
---
name: $SKILL_NAME
description: Generate a validated HTML weekly report for $SKILL_TITLE.
---

# $SKILL_TITLE

## 目的

根据 skill 内置的栏目合同、输入合同和输出合同，
生成最终 HTML 周报。

## 输入

- data files declared by the normalized spec
- see: [examples/input_inventory.md](./examples/input_inventory.md)

## 工作流

1. validate the embedded contract and input inventory
2. map input files to the declared data contracts
3. build each section in the validated order
4. generate conclusions using only declared metrics and evidence rules
5. determine whether the current package is documentation-only or runnable
6. render the final HTML report and include source-data notes

## 约束

- do not change the validated section order
- do not infer undeclared metric logic
- do not change the output format away from HTML
- do not explain changes without data evidence declared by the normalized spec
- do not present documentation-only output as runnable output

## 参考资料

- [input_inventory.md](./examples/input_inventory.md)
- [html-contract.md](./assets/html-contract.md)
- [report-outline.md](./assets/report-outline.md)
EOF

cat > "$TARGET_DIR/README.md" <<EOF
# $SKILL_TITLE

## 说明

This downstream skill produces an HTML weekly report using a validated spec and
declared data contracts.

Current level: \`$SKILL_LEVEL\`

## 输入要求

Users must prepare the required input files in a single directory.

- File list and field expectations: \`examples/input_inventory.md\`
- Output structure and required sections: \`assets/report-outline.md\`
- HTML contract: \`assets/html-contract.md\`

This package should remain self-contained and must not require external repo
documents to understand the runtime contract.

## 目录结构

- \`SKILL.md\`: agent-facing report generation workflow
- \`skill.json\`: metadata
- \`assets/\`: HTML contract, outline, prompt, validation checklist
- \`examples/\`: spec and output examples
- \`scripts/\`: execution packaging area
EOF

cat > "$TARGET_DIR/skill.json" <<EOF
{
  "name": "$SKILL_NAME",
  "title": "$SKILL_TITLE",
  "description": "Generate an HTML weekly report for $SKILL_TITLE from a validated spec.",
  "version": "0.1.0",
  "status": "draft",
  "visibility": "internal",
  "entry": "SKILL.md",
  "tags": ["reports", "weekly", "html", "generated"],
  "author": "raincai"
}
EOF

cat > "$TARGET_DIR/assets/html-contract.md" <<EOF
# HTML 合同

- title block
- period block
- stable section order
- charts and tables declared by the normalized spec
- conclusion blocks
- source-data notes
- if table schema is declared, output columns must match the spec
- if narrative schema is declared, direction words must match the spec
EOF

cat > "$TARGET_DIR/assets/report-outline.md" <<EOF
# 周报结构

Populate each report section from the embedded contract in this skill.

Required structure:

1. report header
2. period metadata
3. report body in validated section order
4. source-data notes

If the spec declares table schemas or WoW display rules, copy them into this file
before claiming the downstream skill is runnable.
EOF

cat > "$TARGET_DIR/assets/report-prompt.md" <<EOF
# 周报生成 Prompt

Generate the HTML weekly report from the normalized spec and declared data
contracts only.

Rules:

- use only metrics and fields declared in the normalized spec
- keep the validated section order
- include charts, tables, and conclusion blocks where required
- block unsupported analysis instead of guessing
- follow declared table schemas and WoW rules exactly when present
- do not claim runnable output unless real execution and verification exist
EOF

cat > "$TARGET_DIR/assets/validation-checklist.md" <<EOF
# 校验清单

- normalized spec exists
- required data contracts are mapped
- required sections are present
- output format is HTML
- skill level is declared
- runnable skills require sample-backed execution evidence
EOF

cat > "$TARGET_DIR/examples/normalized-spec.md" <<EOF
# 标准化 Spec 参考

本 skill 默认优先读取以下内部文件：

- examples/normalized-spec-summary.md
- assets/report-outline.md
- assets/html-contract.md

仅在字段口径冲突或合同不一致时，回到本 skill 内部文件逐条核对。
EOF

cat > "$TARGET_DIR/examples/normalized-spec-summary.md" <<EOF
# 标准化 Spec 摘要

- 在此保留执行所需的最小字段集合
- 建议控制在 30-80 行，避免重复粘贴完整长 spec
- 应至少包含：report_goal、time_definition、report_outline、data_contracts、output_contract 的关键摘要
EOF

cat > "$TARGET_DIR/examples/input_inventory.md" <<EOF
# 输入文件清单

Fill with the datasets required by the normalized spec.

If the target level is \`runnable\`, replace this placeholder with real sample
files and actual file-name patterns before claiming the skill is runnable.
EOF

cat > "$TARGET_DIR/examples/output-outline.html" <<EOF
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>$SKILL_TITLE</title>
  </head>
  <body>
    <header>
      <h1>$SKILL_TITLE</h1>
    </header>
    <main></main>
  </body>
</html>
EOF

cat > "$TARGET_DIR/scripts/README.md" <<EOF
# Scripts

Current level: \`$SKILL_LEVEL\`

- \`documentation-only\`: stubs are allowed, but the package must not be presented as runnable
- \`runnable\`: replace stubs with a real execution script, dependencies, tests, and sample-backed verification
EOF

cat > "$TARGET_DIR/scripts/run-report.sh" <<EOF
#!/usr/bin/env bash

set -euo pipefail

echo "This generated skill is currently marked as: $SKILL_LEVEL"
echo "Replace this stub with a real execution entry before claiming runnable output."
exit 1
EOF

chmod +x "$TARGET_DIR/scripts/run-report.sh"

cat > "$TARGET_DIR/scripts/requirements.txt" <<EOF
# Replace with real runtime dependencies when the skill moves to runnable.
EOF

echo "Created or updated report skill: $SKILL_NAME"
