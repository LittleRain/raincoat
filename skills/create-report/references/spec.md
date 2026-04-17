# Standardized Report Spec

## Purpose

This document defines the normalized intermediate spec that `create-report`
must produce before generating any downstream report skill.

Downstream skills must not be generated directly from raw business prose.

## Required Top-Level Sections

### `report_goal`

Define why the report exists and who will use it.

Required fields:

- `report_name`
- `domain`
- `audience`
- `decision_goals`
- `success_definition`

### `business_context`

Define the business background that affects interpretation.

Required fields:

- `business_summary`
- `business_units`
- `scope_notes`

Optional fields:

- `excluded_scope`
- `known_limitations`

### `terminology`

Define terms and segmentation rules.

Required fields:

- `terms`
- `segment_rules`

Each `term` should contain:

- `name`
- `definition`
- `source_fields`

Each `segment_rule` should contain:

- `segment_name`
- `rule_type`
- `rule_logic`
- `source_fields`

### `semantic_contract`

Define requester-specific business language that downstream skills must obey.
This contract prevents terms such as 行业、分类、业务线、渠道、内容类型 from
being reinterpreted as generic labels.

Required fields:

- `business_terms`
- `term_aliases`
- `segment_rules`
- `semantic_examples`
- `judgment_terms`

Rules:

- Terms with explicit source fields or classification rules are hard constraints.
- Aliases such as “分行业”“行业拆解”“行业维度” must resolve to a canonical term.
- If a term is named but lacks source fields or rules, mark it `needs_clarification`.
- Downstream skills may infer judgment metrics, but must not override hard-constrained business terms.
- `semantic_examples` should contain representative input rows and expected labels for classification-sensitive terms.

### `time_definition`

Define reporting windows and comparison logic.

Required fields:

- `reporting_granularity`
- `current_period_definition`
- `comparison_period_definition`

Optional fields:

- `historical_window`
- `timezone`

### `report_outline`

Define the report structure section by section.

Each section must contain:

- `section_id`
- `title`
- `purpose`
- `required_views`
- `required_metrics`
- `required_dimensions`
- `required_outputs`
- `narrative_expectations`

Recommended additional fields for `L1` / `L2` reliability:

- `section_data_mapping` (primary/fallback contracts and precedence)
- `table_schemas`
- `table_layout_contract` (how dimensions become rows, columns, separate tables, or hybrid subtables)
- `narrative_schema`
- `view_inventory` (expected chart/table counts, explicit required metrics, business-scene dimensions, required labels, and optional judgment metrics derived from the source requirement)

If a section needs charts or tables, they must be declared in
`required_views`.

### `table_layout_contract`

Define table layout intent separately from business dimensions.

Supported `layout_mode` values:

- `separate_tables_by_dimension`: split one dimension into multiple table instances.
- `dimension_as_rows`: render the dimension as row fields in one table.
- `dimension_as_columns`: render the dimension as columns or column groups in one table.
- `hybrid_section_with_subtables`: render a section-level overview plus one or more subtables.
- `unresolved`: wording is too ambiguous; generation must surface the ambiguity.

Each layout entry should contain:

- `section` or `section_id`
- `layout_mode`
- `split_dimension`
- `row_dimensions`
- `column_dimensions`
- `required_table_instances`
- `required_tables`
- `table_grain`
- `source_phrase`
- `interpretation_reason`
- `ambiguity_level`

Interpretation defaults:

- “按某维度拆分” defaults to `dimension_as_rows`.
- “每个/分别/各自/单独/逐个表格” indicates `separate_tables_by_dimension`.
- “行业拆解” with both “分行业” and “分行业及分类” indicates `hybrid_section_with_subtables`.
- High-ambiguity layouts must include `source_phrase` and `interpretation_reason`.

### `data_contracts`

Define all available input datasets.

Each contract must contain:

- `contract_id`
- `display_name`
- `file_name_pattern`
- `time_granularity`
- `dimensions`
- `metrics`
- `field_notes`
- `supported_sections`

Optional fields:

- `join_keys`
- `known_quality_risks`
- `attachment_dependencies`
- `period_coverage_expectation`
- `priority_for_sections`

### `analysis_rules`

Define what analysis is required, allowed, and forbidden.

Required fields:

- `must_explain_conditions`
- `allowed_evidence`
- `forbidden_inferences`

Optional fields:

- `ranking_rules`
- `threshold_rules`
- `fallback_behavior`
- `ratio_metric_fallback_rules`

If ratio metrics are used, define both primary and fallback formulas explicitly.
Example: `CTR = click_pv / exposure_pv`; fallback `CTR ~= detail_pv / exposure_pv`
when `click_pv` is unavailable.

For non-core or ambiguous desired metrics that cannot be enumerated precisely,
the spec may set `llm_judgment_allowed: true`. Those metrics are not strict
output-presence gates, but generated reports must mark the口径 as inferred or
judgment-based and cite the supporting source fields.

### `output_contract`

Define the final report output contract.

Required fields:

- `format`
- `required_sections`
- `section_order`
- `required_blocks`
- `citation_rules`

Recommended additional fields for table stability:

- `table_column_rules`
- `wow_display_rules`
- `narrative_direction_rules`
- `expected_output_inventory` (total/section-level chart/table counts, `required_metrics`, `required_dimensions`, `required_text`, and optional `judgment_metrics`)
- `semantic_contract` (business terms and semantic examples that must be visible or validated)
- `table_layout_contract` (table layout modes that rendered HTML must satisfy)
- `empty_period_column_policy` (hide period columns that are empty for all rows)
- `runtime_dependency_policy` (must support `file://` open; no external CDN required)
- `axis_origin_policy` (numeric axes must start at zero; truncation is forbidden)

Defaults:

- `format` must be `html`
- `runtime_dependency_policy` should default to `self-contained-or-local`:
  no mandatory external network dependency for chart rendering
- `axis_origin_policy` defaults to `start-at-zero`: all chart axes using numeric values must begin at zero; mid-axis truncation is prohibited

### `skill_generation_contract`

Define the downstream package shape `create-report` must generate.

Required fields:

- `skill_name`
- `skill_title`
- `skill_level` (`L0`, `L1`, or `L2`)
- `required_files`
- `required_assets`
- `required_examples`

Recommended default `required_files`:

- `SKILL.md`
- `skill-manifest.yaml`
- `agents/openai.yaml`
- `scripts/validate-output-inventory.py`

Recommended default `required_assets`:

- report outline template
- HTML contract template
- validation checklist
- expected output inventory template

Recommended default `required_examples`:

- normalized spec example
- input inventory example
- expected output inventory example
- output outline example

Level definitions:

- `L0`: documentation-only package. Allows stubs and gap records. Must not
  claim runnable output.
- `L1`: runnable MVP. Requires real samples, real runner, generated HTML,
  runtime logs, and validation evidence.
- `L2`: publishable/stable. Requires all L1 evidence plus standalone packaging,
  no required CDN, browser validation, and regression evidence.

### `acceptance_checks`

Define pre-generation and post-generation validation.

Must include at least:

- `spec_completeness_checks`
- `spec_consistency_checks`
- `generation_readiness_checks`
- `html_output_checks`
- `level_readiness_checks`
- `level_acceptance_checks`
- `output_inventory_checks`

## Stop Conditions

`create-report` must stop if any of the following are unresolved:

- `report_goal` is incomplete
- a section lacks a supporting data contract
- a metric lacks a source field or formula
- time definitions are missing or conflict
- analysis requirements exceed allowed inference bounds
- the output contract is incompatible with HTML
- target level is `L1` or `L2` but required level evidence is missing
- target level is `L1` or `L2` but chart/table counts or explicit `required_metrics` are not declared or rendered output does not match declarations
- hard-constrained business terms are missing from `semantic_contract`
- table-producing sections lack `table_layout_contract`
