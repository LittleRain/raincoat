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
mkdir -p "$TARGET_DIR/agents"

cat > "$TARGET_DIR/SKILL.md" <<EOF
---
name: $SKILL_NAME
description: Use when generating or updating the $SKILL_TITLE HTML weekly report from validated report contracts and sample-backed data rules.
---

# $SKILL_TITLE

## 目的

根据 skill 内置的栏目合同、输入合同和输出合同，
生成最终 HTML 周报。

## 输入

- data files declared by the normalized spec
- see: [examples/input_inventory.md](./examples/input_inventory.md)
- runtime metadata: [agents/openai.yaml](./agents/openai.yaml)

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
- do not require external CDN/network to render charts in delivered HTML
- ensure chart rendering works when opening output via \`file://\`
- do not explain changes without data evidence declared by the normalized spec
- do not present documentation-only output as runnable output

## 参考资料

- [input_inventory.md](./examples/input_inventory.md)
- [html-contract.md](./assets/html-contract.md)
- [report-outline.md](./assets/report-outline.md)
EOF

cat > "$TARGET_DIR/agents/openai.yaml" <<EOF
version: 1
interface:
  display_name: $SKILL_TITLE
  short_description: Generate the $SKILL_TITLE HTML weekly report from packaged contracts and declared input files.
  default_prompt: |
    Generate the $SKILL_TITLE HTML weekly report using the packaged spec summary,
    input inventory, and output contract. Ensure chart rendering works when
    opening via file:// and avoid required external CDN dependencies. Do not
    infer undeclared metrics or claim runnable output unless the package
    includes real execution evidence.
EOF

cat > "$TARGET_DIR/assets/html-contract.md" <<EOF
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
- Chart.js 4.x 必须内联（不依赖外部 CDN）
- 必须在 Chart.js 之后内联 chart-defaults.js (位于本 skill 的 assets/chart-defaults.js)
- 使用 chartPresets.line / .bar / .doughnut / .combo 创建图表
- 使用 REPORT_FORMAT.gmv / .pv / .pct / .num 格式化数值
- 使用 REPORT_WOW(current, previous) 计算环比
- opening report.html via \`file://\` must still render charts

## 数据合同
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

- Chart.js 4.x 必须内联到 HTML 中（禁止外部 CDN）
- chart-defaults.js 必须在 Chart.js 之后内联
- 使用标准 API 创建图表：
  - reportChart(canvasId, config) — 挂载图表
  - chartPresets.line(labels, datasets, opts) — 折线图
  - chartPresets.bar(labels, datasets, opts) — 柱状图
  - chartPresets.doughnut(labels, data, opts) — 环形图
  - chartPresets.combo(labels, datasets, opts) — 组合图（双Y轴）
  - REPORT_FORMAT.gmv/pv/pct/num — 数值格式化
  - REPORT_WOW(cur, prev) — 环比计算
  - reportHTML.metricCard(label, value, wow, color) — 指标卡 HTML
  - reportHTML.wowTag(wow) — 环比标签 HTML

## 数据规则

- use only metrics and fields declared in the normalized spec
- keep the validated section order
- include charts, tables, and conclusion blocks where required
- block unsupported analysis instead of guessing
- follow declared table schemas and WoW rules exactly when present
- if a section has multiple contracts, obey the declared primary/fallback precedence
- for ratio metrics, use declared primary formula and fallback formula only
- hide period columns that are empty for all rows when spec requires that behavior
- emit runtime logs for file discovery, file read status, and key processing checkpoints
- stream logs during execution (avoid end-of-run dump only)
- do not claim runnable output unless real execution and verification exist
EOF

cat > "$TARGET_DIR/assets/validation-checklist.md" <<EOF
# 校验清单

## Spec 完整性
- normalized spec exists
- required data contracts are mapped
- required sections are present
- output format is HTML
- skill level is declared
- section-level data-source precedence is declared when multiple contracts exist
- ratio metric fallback rules are declared when required fields may be missing
- empty-period-column behavior is declared for table-heavy sections

## 样式合规
- base-report.css 已完整内联到 <style>
- 使用 base-report.css 定义的标准 class，未自行发明替代样式
- 数值列使用 tnum（表格已自动启用）
- 指标卡使用 .metric-card 组件
- 图表容器使用 .chart-container + .chart-area
- 结论框使用 .conclusion 组件
- 导航使用 .nav 锚点模式

## 图表合规
- Chart.js 源码已内联（非 CDN 引用）
- chart-defaults.js 已在 Chart.js 之后内联
- 使用 chartPresets / reportChart API 创建图表
- output HTML is verified under \`file://\` for chart visibility
- 图表配色使用 REPORT_PALETTE

## 运行时合规（仅 runnable）
- runnable skills require sample-backed execution evidence
- runnable skills must include real-time process logs with INFO/WARN/ERROR semantics
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
<html lang="zh-CN">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>$SKILL_TITLE</title>
    <style>
    /* ── Inline base-report.css here ──
       Source: assets/base-report.css (included in this skill package)
       Copy the FULL content of that file into this <style> block.
       Do NOT use <link> — reports must be self-contained. */
    </style>
  </head>
  <body>
    <div class="page">

      <!-- Hero / Report Header -->
      <header class="hero">
        <div class="hero-eyebrow">$SKILL_TITLE</div>
        <h1>数据概览</h1>
        <p class="hero-desc"><!-- 报告摘要描述 --></p>
        <div class="hero-meta">
          <span class="hero-badge"><strong>W##</strong> 本周</span>
          <span class="hero-badge">W## 上周</span>
        </div>
      </header>

      <!-- Sticky Nav -->
      <nav class="nav">
        <!-- 按 spec 声明的栏目生成锚点链接 -->
        <a href="#s1" class="active">核心数据趋势</a>
        <a href="#s2">栏目二</a>
        <a href="#s3">栏目三</a>
      </nav>

      <!-- Section 1 -->
      <section class="section" id="s1">
        <div class="section-head">
          <div>
            <span class="section-num">SECTION 01</span>
            <h2>核心数据趋势</h2>
          </div>
        </div>

        <!-- Metric Cards -->
        <div class="metric-grid">
          <!-- 按 spec 声明的核心指标生成 .metric-card -->
        </div>

        <!-- Charts -->
        <div class="grid-2" style="margin-top: var(--sp-7);">
          <div class="chart-container">
            <figcaption>图表标题</figcaption>
            <div class="chart-area"><canvas id="c1"></canvas></div>
          </div>
        </div>

        <!-- Conclusion -->
        <div class="conclusion">
          <h4>结论</h4>
          <ul>
            <li><span class="hl">指标名:</span> 数据摘要</li>
          </ul>
        </div>
      </section>

      <!-- Additional sections follow same pattern -->

      <!-- Footnote -->
      <div class="footnote">
        <strong>数据说明</strong><br/>
        <!-- 数据口径、来源、统计周期等说明 -->
      </div>

    </div>

    <!-- Chart.js (inline, not CDN) -->
    <script>
    /* ── Inline Chart.js 4.x minified source here ──
       Download from: https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js
       Paste the full minified content. */
    </script>

    <!-- Chart defaults (inline) -->
    <script>
    /* ── Inline chart-defaults.js here ──
       Source: assets/chart-defaults.js (included in this skill package)
       Copy the FULL content of that file. */
    </script>

    <!-- Report data & chart initialization -->
    <script>
    // var D = { ... }; // Python generate_report.py injects data here
    // Use: reportChart('c1', chartPresets.line(labels, datasets, { yFormat: 'gmv' }));
    </script>
  </body>
</html>
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

# ── Copy shared design-system assets into downstream skill ──
# These are referenced by html-contract.md and report-prompt.md.
# Downstream skills need local copies to be self-contained.
SHARED_ASSETS_DIR="$SKILLS_DIR/create-report/assets"

if [[ -f "$SHARED_ASSETS_DIR/base-report.css" ]]; then
  cp "$SHARED_ASSETS_DIR/base-report.css" "$TARGET_DIR/assets/base-report.css"
  echo "  Copied base-report.css → $TARGET_DIR/assets/"
else
  echo "  WARNING: base-report.css not found at $SHARED_ASSETS_DIR" >&2
fi

if [[ -f "$SHARED_ASSETS_DIR/chart-defaults.js" ]]; then
  cp "$SHARED_ASSETS_DIR/chart-defaults.js" "$TARGET_DIR/assets/chart-defaults.js"
  echo "  Copied chart-defaults.js → $TARGET_DIR/assets/"
else
  echo "  WARNING: chart-defaults.js not found at $SHARED_ASSETS_DIR" >&2
fi

if [[ -f "$SHARED_ASSETS_DIR/DESIGN.md" ]]; then
  cp "$SHARED_ASSETS_DIR/DESIGN.md" "$TARGET_DIR/assets/DESIGN.md"
  echo "  Copied DESIGN.md → $TARGET_DIR/assets/"
fi

echo "Created or updated report skill: $SKILL_NAME"
