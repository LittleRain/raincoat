#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)
SKILLS_DIR="$ROOT_DIR/skills"

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
  local level="$2"
  cat > "$target_dir/scripts/run-report.sh" <<EOF_STUB
#!/usr/bin/env bash

set -euo pipefail

echo "This generated skill is currently marked as: $level"
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

copy_output_inventory_validator() {
  local target_dir="$1"
  local validator="$SKILLS_DIR/create-report/scripts/validate-output-inventory.py"

  if [[ -f "$validator" ]]; then
    cp "$validator" "$target_dir/scripts/validate-output-inventory.py"
    chmod +x "$target_dir/scripts/validate-output-inventory.py"
  else
    echo "  WARNING: validate-output-inventory.py not found at $validator" >&2
  fi
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
validate_evidence "$SKILL_LEVEL" "$EVIDENCE_DIR"

TARGET_DIR="$SKILLS_DIR/$SKILL_NAME"
mkdir -p "$TARGET_DIR" "$TARGET_DIR/assets" "$TARGET_DIR/examples" "$TARGET_DIR/scripts" "$TARGET_DIR/agents"

cat > "$TARGET_DIR/SKILL.md" <<EOF_SKILL
---
name: $SKILL_NAME
description: Use when generating or updating the $SKILL_TITLE HTML weekly report from validated report contracts and sample-backed data rules.
---

# $SKILL_TITLE

Current level: $SKILL_LEVEL_LABEL

## 目的

根据 skill 内置的栏目合同、输入合同和输出合同，生成最终 HTML 周报。

## 输入

- data files declared by the normalized spec
- see: [examples/input_inventory.md](./examples/input_inventory.md)
- runtime metadata: [agents/openai.yaml](./agents/openai.yaml)
- level and evidence metadata: [skill-manifest.yaml](./skill-manifest.yaml)

## 工作流

1. validate the embedded contract and input inventory
2. map input files to the declared data contracts
3. build each section in the validated order
4. read semantic and table-layout contracts before deciding dimensions or tables
5. generate conclusions using only declared metrics and evidence rules
6. confirm the current package level before claiming runnable or publishable output
7. render the final HTML report and include source-data notes

## 约束

- do not change the validated section order
- do not infer undeclared metric logic
- do not reinterpret hard-constrained business terms from raw prose
- do not reinterpret table split wording when table-layout-contract.json declares the layout
- do not change the output format away from HTML
- do not require external CDN/network to render charts in delivered HTML
- ensure chart rendering works when opening output via \`file://\`
- do not explain changes without data evidence declared by the normalized spec
- do not present L0 documentation output as L1 runnable output
- do not present L1 internal output as L2 publishable output

## 参考资料

- [skill-manifest.yaml](./skill-manifest.yaml)
- [input_inventory.md](./examples/input_inventory.md)
- [html-contract.md](./assets/html-contract.md)
- [report-outline.md](./assets/report-outline.md)
- [acceptance-matrix.md](./assets/acceptance-matrix.md)
- [expected-output-inventory.json](./examples/expected-output-inventory.json)
- [semantic-contract.json](./examples/semantic-contract.json)
- [table-layout-contract.json](./examples/table-layout-contract.json)
EOF_SKILL

cat > "$TARGET_DIR/skill-manifest.yaml" <<EOF_MANIFEST
version: 1
skill_name: $SKILL_NAME
skill_title: $SKILL_TITLE
declared_level: $SKILL_LEVEL
effective_level: $SKILL_LEVEL
acceptance_status: passed
acceptance_date: $(date +%Y-%m-%d)
acceptance_evidence:
EOF_MANIFEST

case "$SKILL_LEVEL" in
  L0)
    cat >> "$TARGET_DIR/skill-manifest.yaml" <<'EOF_MANIFEST'
  - SKILL.md
  - assets/html-contract.md
  - assets/report-outline.md
  - assets/validation-checklist.md
  - examples/expected-output-inventory.json
  - examples/normalized-spec-summary.md
blocking_gaps:
  - real sample-backed execution is not included
  - runner is a documentation stub
  - browser validation has not been run
EOF_MANIFEST
    ;;
  L1)
    cat >> "$TARGET_DIR/skill-manifest.yaml" <<'EOF_MANIFEST'
  - scripts/run-report.sh
  - sample_data/
  - output/report.html
  - output/run.log
  - output/validation-report.json
blocking_gaps: []
EOF_MANIFEST
    ;;
  L2)
    cat >> "$TARGET_DIR/skill-manifest.yaml" <<'EOF_MANIFEST'
  - scripts/run-report.sh
  - sample_data/
  - output/report.html
  - output/run.log
  - output/validation-report.json
  - output/browser-validation.json
  - output/screenshots/
blocking_gaps: []
EOF_MANIFEST
    ;;
esac

cat > "$TARGET_DIR/agents/openai.yaml" <<EOF_AGENT
version: 1
interface:
  display_name: $SKILL_TITLE
  short_description: Generate the $SKILL_TITLE HTML weekly report from packaged contracts and declared input files.
  default_prompt: |
    Generate the $SKILL_TITLE HTML weekly report using the packaged spec summary,
    input inventory, semantic contract, table-layout contract, and output contract.
    Check skill-manifest.yaml first. Do not claim a higher level than the manifest
    supports. Ensure chart rendering works when opening via file:// and avoid
    required external CDN dependencies. Do not infer undeclared metrics or
    reinterpret hard-constrained business terms unless L1/L2 evidence exists.
EOF_AGENT

cat > "$TARGET_DIR/assets/html-contract.md" <<'EOF_HTML'
# HTML 合同

## 结构合同
- title block (使用 .hero 组件)
- period block (使用 .hero-meta + .hero-badge)
- stable section order (使用 .section + .section-head)
- charts and tables declared by the normalized spec
- conclusion blocks (使用 .conclusion 组件)
- source-data notes (使用 .footnote 组件)
- anchor navigation (使用 .nav 组件，滚动+锚点模式)

## 样式合同
- 必须内联 base-report.css (位于本 skill 的 assets/base-report.css)
- 必须使用 base-report.css 中定义的 CSS class，禁止另起炉灶写内联样式
- 数值列必须使用 font-feature-settings: "tnum" (已内置于 table 和 .metric-value)
- 环比变化使用 .tag-up / .tag-down / .delta.up / .delta.down
- 指标卡使用 .metric-card，通过 .green/.red/.amber/.blue 指定顶部色条
- 图表容器使用 .chart-container + .chart-area
- 布局网格使用 .grid-2 / .grid-3 / .grid-4

## 图表合同
- Chart.js 4.x 必须内联或本地打包（不依赖外部 CDN）
- 必须在 Chart.js 之后内联 chart-defaults.js (位于本 skill 的 assets/chart-defaults.js)
- 使用 chartPresets.line / .bar / .doughnut / .combo 创建图表
- 使用 REPORT_FORMAT.gmv / .pv / .pct / .num 格式化数值
- 使用 REPORT_WOW(current, previous) 计算环比
- opening report.html via `file://` must still render charts

## 数据合同
- if table schema is declared, output columns must match the spec
- business terms, segment rules, and layout modes declared in examples/semantic-contract.json and examples/table-layout-contract.json are hard constraints
- if narrative schema is declared, direction words must match the spec
- explicit required metrics should use declared formatter rules when available
- ambiguous or non-enumerated metrics may use model judgment when supported by source fields and marked as inferred
- rendered chart/table counts, required metrics, business dimensions, and required labels must match examples/expected-output-inventory.json
EOF_HTML

cat > "$TARGET_DIR/assets/report-outline.md" <<'EOF_OUTLINE'
# 周报结构

Populate each report section from the embedded contract in this skill.

Required structure:

1. report header
2. period metadata
3. report body in validated section order
4. source-data notes

If the spec declares table schemas or WoW display rules, copy them into this file
before claiming the downstream skill is L1 or L2.
EOF_OUTLINE

cat > "$TARGET_DIR/assets/report-prompt.md" <<'EOF_PROMPT'
# 周报生成 Prompt

Generate the HTML weekly report from the normalized spec and declared data
contracts only.

## Level Gate

- Read `skill-manifest.yaml` before generation.
- Read `examples/expected-output-inventory.json` before generation.
- Read `examples/semantic-contract.json` before generation.
- Read `examples/table-layout-contract.json` before generation.
- L0 may only produce documentation or outlines; do not claim runnable output.
- L1 may generate internal runnable reports only when sample-backed execution evidence exists.
- L2 may claim publishable output only when browser and validation evidence exists.

## 样式规则

- 必须在 <style> 中内联 assets/base-report.css 的完整内容
- 使用 base-report.css 中定义的标准 CSS class 构建页面
- 禁止另起炉灶写自定义样式；如需扩展，在 base-report.css class 之后追加
- 可用的布局组件：
  - .hero / .hero-eyebrow / .hero-meta / .hero-badge — 报告头
  - .nav / .nav a — 锚点导航
  - .section / .section-head / .section-num — 栏目
  - .metric-grid / .metric-card — 指标卡（.green/.red/.amber/.blue 控色）
  - .grid-2 / .grid-3 / .grid-4 — 网格布局
  - .card / .card-title — 通用卡片
  - .panel — 内容面板
  - .chart-container / .chart-area — 图表容器
  - .table-wrap / table — 数据表格
  - .conclusion / .hl — 结论框
  - .breakdown-block / .breakdown-head — 拆解模块
  - .footnote — 数据说明
  - .tag-up / .tag-down / .delta.up / .delta.down — 环比标记

## 图表规则

- Chart.js 4.x 必须内联或本地打包到 HTML 中（禁止 required CDN）
- chart-defaults.js 必须在 Chart.js 之后内联
- 使用标准 API 创建图表：reportChart、chartPresets、REPORT_FORMAT、REPORT_WOW、reportHTML

## 数据规则

- use declared official metrics as hard constraints; for exploratory display metrics that cannot be fully enumerated, use model judgment with source-field evidence
- render every chart, table, explicitly required metric, required dimension, and required label declared in expected-output-inventory.json
- preserve business-scene grouping from the source requirement, such as 行业、分类、业务线、渠道、内容类型; do not collapse these into generic summary tables
- apply hard-constrained business terms and segment rules from semantic-contract.json; do not redefine them from raw prose
- apply table-layout-contract.json before deciding whether a dimension becomes separate tables, rows, columns, or hybrid subtables
- if a layout is marked unresolved, surface the unresolved source phrase and interpretation reason in logs or report notes instead of silently choosing a layout
- use model judgment for ambiguous desired metrics when the requirement cannot enumerate every口径; mark those outputs as inferred or judgment-based
- keep the validated section order
- include charts, tables, and conclusion blocks where required
- block unsupported analysis instead of guessing
- follow declared table schemas and WoW rules exactly when present
- if a section has multiple contracts, obey the declared primary/fallback precedence
- for ratio metrics, use declared primary formula and fallback formula only
- hide period columns that are empty for all rows when spec requires that behavior
- emit runtime logs for file discovery, file read status, and key processing checkpoints
- stream logs during execution (avoid end-of-run dump only)
- do not claim L1/L2 output unless real execution and verification evidence exists
EOF_PROMPT

cat > "$TARGET_DIR/assets/validation-checklist.md" <<'EOF_CHECKLIST'
# 校验清单

## L0 Documentation
- normalized spec exists
- section order is fixed
- output format is HTML
- gaps are documented
- package clearly states it is L0 documentation if no real execution evidence exists

## L1 Runnable MVP
- all L0 checks pass
- real sample files exist and cover two comparable periods
- scripts/run-report.sh invokes real generation logic, not a stub
- output/report.html is generated from real samples
- output/run.log includes file discovery, row counts, period detection, section build progress, and output path
- explicit core metric formulas and formatter choices are declared when known
- ambiguous metric口径 may use LLM judgment with source-field evidence
- chart/table counts, required metric labels, required dimensions, and required text match expected-output-inventory.json
- semantic examples and table layout contracts match the generated HTML
- HTML smoke validation confirms non-placeholder standard report structure

## L2 Publishable
- all L1 checks pass
- package avoids absolute repo-local paths
- no required external CDN for CSS or chart runtime
- file:// browser validation confirms charts render
- console has no blocking errors
- regression tests cover missing values, zero denominators, and fallback behavior
- validation evidence is packaged

## 样式合规
- base-report.css 已完整内联到 <style>
- 使用 base-report.css 定义的标准 class，未自行发明替代样式
- 数值列使用 tnum（表格已自动启用）
- 指标卡使用 .metric-card 组件
- 图表容器使用 .chart-container + .chart-area
- 结论框使用 .conclusion 组件
- 导航使用 .nav 锚点模式

## 图表合规
- Chart.js 源码已内联或本地打包（非 required CDN 引用）
- chart-defaults.js 已在 Chart.js 之后内联
- 使用 chartPresets / reportChart API 创建图表
- output HTML is verified under `file://` for chart visibility when claiming L2
- 图表配色使用 REPORT_PALETTE
EOF_CHECKLIST

cat > "$TARGET_DIR/examples/normalized-spec.md" <<'EOF_SPEC'
# 标准化 Spec 参考

本 skill 默认优先读取以下内部文件：

- examples/normalized-spec-summary.md
- assets/report-outline.md
- assets/html-contract.md

仅在字段口径冲突或合同不一致时，回到本 skill 内部文件逐条核对。
EOF_SPEC

cat > "$TARGET_DIR/examples/normalized-spec-summary.md" <<'EOF_SUMMARY'
# 标准化 Spec 摘要

- 在此保留执行所需的最小字段集合
- 建议控制在 30-80 行，避免重复粘贴完整长 spec
- 应至少包含：report_goal、time_definition、report_outline、data_contracts、output_contract 的关键摘要
EOF_SUMMARY

cat > "$TARGET_DIR/examples/input_inventory.md" <<'EOF_INV'
# 输入文件清单

Fill with the datasets required by the normalized spec.

If the target level is L1 or L2, replace this placeholder with real sample files
and actual file-name patterns before claiming runnable output.
EOF_INV

cat > "$TARGET_DIR/examples/expected-output-inventory.json" <<'EOF_VIEW_INV'
{
  "source_requirement": "source requirement markdown summarized into the normalized spec",
  "description": "Expected rendered view counts. Derive these counts from 需求.md during normalization, then validate generated report.html with scripts/validate-output-inventory.py.",
  "totals": {
    "sections": 0,
    "charts": 0,
    "tables": 0
  },
  "required_metrics": [],
  "required_dimensions": [],
  "required_text": [],
  "judgment_metrics": [],
  "semantic_contract": {
    "business_terms": [],
    "term_aliases": [],
    "segment_rules": [],
    "semantic_examples": [],
    "judgment_terms": []
  },
  "table_layout_contract": [],
  "sections": []
}
EOF_VIEW_INV

cat > "$TARGET_DIR/examples/semantic-contract.json" <<'EOF_SEMANTIC'
{
  "description": "Requester-specific business language contract. Populate from 需求.md before promoting beyond L0.",
  "business_terms": [
    {
      "name": "行业",
      "definition": "Replace with the requester-specific definition.",
      "source_fields": [],
      "hard_constraint": true,
      "needs_clarification": true
    }
  ],
  "term_aliases": [
    {
      "alias": "分行业",
      "canonical_term": "行业"
    }
  ],
  "segment_rules": [],
  "rule_priority": [],
  "null_fallback": [],
  "semantic_examples": [],
  "judgment_terms": []
}
EOF_SEMANTIC

cat > "$TARGET_DIR/examples/table-layout-contract.json" <<'EOF_LAYOUT'
[
  {
    "section": "replace-with-section-title",
    "layout_mode": "unresolved",
    "split_dimension": "",
    "row_dimensions": [],
    "column_dimensions": [],
    "required_table_instances": [],
    "table_grain": "",
    "source_phrase": "",
    "interpretation_reason": "",
    "ambiguity_level": "high"
  }
]
EOF_LAYOUT

cat > "$TARGET_DIR/examples/output-outline.html" <<EOF_HTML_OUTLINE
<!DOCTYPE html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>$SKILL_TITLE</title>
    <style>
    /* Inline the FULL assets/base-report.css content here. Do NOT use <link>. */
    </style>
  </head>
  <body>
    <div class="page">
      <header class="hero">
        <div class="hero-eyebrow">$SKILL_TITLE</div>
        <h1>数据概览</h1>
        <p class="hero-desc"><!-- 报告摘要描述 --></p>
        <div class="hero-meta">
          <span class="hero-badge"><strong>W##</strong> 本周</span>
          <span class="hero-badge">W## 上周</span>
        </div>
      </header>
      <nav class="nav">
        <a href="#s1" class="active">核心数据趋势</a>
      </nav>
      <section class="section" id="s1">
        <div class="section-head"><div><span class="section-num">SECTION 01</span><h2>核心数据趋势</h2></div></div>
        <div class="metric-grid"></div>
        <div class="chart-container"><figcaption>图表标题</figcaption><div class="chart-area"><canvas id="c1"></canvas></div></div>
        <div class="conclusion"><h4>结论</h4><ul><li><span class="hl">指标名:</span> 数据摘要</li></ul></div>
      </section>
      <div class="footnote"><strong>数据说明</strong><br/></div>
    </div>
    <script>/* Inline Chart.js 4.x local source here for L2 publishable output. */</script>
    <script>/* Inline the FULL assets/chart-defaults.js content here after Chart.js. */</script>
    <script>// Use reportChart('c1', chartPresets.line(labels, datasets, { yFormat: 'gmv' }));</script>
  </body>
</html>
EOF_HTML_OUTLINE

cat > "$TARGET_DIR/scripts/requirements.txt" <<'EOF_REQ'
# Replace with real runtime dependencies when the skill moves to L1 or L2.
EOF_REQ

SHARED_ASSETS_DIR="$SKILLS_DIR/create-report/assets"
for asset in base-report.css chart-defaults.js DESIGN.md acceptance-matrix.md; do
  if [[ -f "$SHARED_ASSETS_DIR/$asset" ]]; then
    cp "$SHARED_ASSETS_DIR/$asset" "$TARGET_DIR/assets/$asset"
  else
    echo "  WARNING: $asset not found at $SHARED_ASSETS_DIR" >&2
  fi
done

if [[ "$SKILL_LEVEL" == "L0" ]]; then
  write_stub_runner "$TARGET_DIR" "$SKILL_LEVEL"
else
  copy_evidence "$TARGET_DIR" "$EVIDENCE_DIR"
fi
copy_output_inventory_validator "$TARGET_DIR"

echo "Created or updated report skill: $SKILL_NAME ($SKILL_LEVEL_LABEL)"
