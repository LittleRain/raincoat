# 创建周报 Skill 中间规格

## 目的

本文档定义 `create-report` 产出的标准化中间 spec。

它是：

- 原始业务需求
- 下游 `report-<domain>` skill 生成

之间的硬边界。

下游周报 skill 不允许直接基于原始业务文档生成，必须经过标准化 spec。

## Spec 结构

标准化 spec 最少必须包含以下顶层部分。

### `report_goal`

定义这份周报为什么存在，以及谁会使用它。

必填字段：

- `report_name`
- `domain`
- `audience`
- `decision_goals`
- `success_definition`

### `business_context`

定义影响解读方式的业务背景。

必填字段：

- `business_summary`
- `business_units`
- `scope_notes`

可选字段：

- `excluded_scope`
- `known_limitations`

### `terminology`

定义名词解释和分类规则。

必填字段：

- `terms`
- `segment_rules`

每个 `term` 需要包含：

- `name`
- `definition`
- `source_fields`

每个 `segment_rule` 需要包含：

- `segment_name`
- `rule_type`
- `rule_logic`
- `source_fields`

### `time_definition`

定义所有时间周期和对比逻辑。

必填字段：

- `reporting_granularity`
- `current_period_definition`
- `comparison_period_definition`

可选字段：

- `historical_window`
- `timezone`

### `report_outline`

按栏目定义整份周报结构。

每个栏目必须包含：

- `section_id`
- `title`
- `purpose`
- `required_views`
- `required_metrics`
- `required_dimensions`
- `required_outputs`
- `narrative_expectations`

如果栏目需要图表或表格，必须显式写在 `required_views` 中。

### `data_contracts`

定义所有可用输入数据集。

每个数据合同必须包含：

- `contract_id`
- `display_name`
- `file_name_pattern`
- `time_granularity`
- `dimensions`
- `metrics`
- `field_notes`
- `supported_sections`

可选字段：

- `join_keys`
- `known_quality_risks`
- `attachment_dependencies`

### `analysis_rules`

定义允许做什么分析、必须做什么分析、不允许做什么推断。

必填字段：

- `must_explain_conditions`
- `allowed_evidence`
- `forbidden_inferences`

可选字段：

- `ranking_rules`
- `threshold_rules`
- `fallback_behavior`

### `output_contract`

定义最终周报输出合同。

必填字段：

- `format`
- `required_sections`
- `section_order`
- `required_blocks`
- `citation_rules`

默认值：

- `format` 必须为 `html`

### `skill_generation_contract`

定义生产器 skill 必须产出的下游 skill 包结构。

必填字段：

- `skill_name`
- `skill_title`
- `required_files`
- `required_assets`
- `required_examples`

默认要求的 `required_files`：

- `SKILL.md`
- `README.md`
- `skill.json`

默认要求的 `required_assets`：

- 报告结构模板
- HTML 合同模板
- 校验清单

默认要求的 `required_examples`：

- 标准化 spec 样例
- 输入清单样例
- HTML 输出样例

### `acceptance_checks`

定义生成前和生成后的验收检查项。

至少包含：

- `spec_completeness_checks`
- `spec_consistency_checks`
- `generation_readiness_checks`
- `html_output_checks`

## 生成门槛

当出现以下任一情况时，`create-report` 必须停止生成：

- `report_goal` 不完整
- 某个栏目没有可支撑的数据合同
- 某个指标没有字段来源或计算公式
- 时间定义缺失或相互冲突
- 分析要求超出允许推断范围
- 输出合同与 HTML 周报不兼容

## 圈子业务周报映射说明

样例
[圈子业务周报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/圈子业务周报需求.md)
映射到本 spec 时：

- 周报目标和读者进入 `report_goal`
- 业务介绍、业务线、自定义行业口径进入 `business_context` 和 `terminology`
- 周五到周四的定义进入 `time_definition`
- 五个大栏目进入 `report_outline`
- “数据源文档”部分进入 `data_contracts`
- 波动阈值、归因限制等进入 `analysis_rules`
- 最终 HTML 输出要求进入 `output_contract`

## 编写规则

当原始需求中包含大量业务 prose 时，`create-report` 应保留业务语义，
但要去掉冗余叙述。标准化 spec 是合同文档，不是原始对话记录。
