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
- `narrative_schema`

If a section needs charts or tables, they must be declared in
`required_views`.

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

Recommended default `required_assets`:

- report outline template
- HTML contract template
- validation checklist

Recommended default `required_examples`:

- normalized spec example
- input inventory example
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

## Stop Conditions

`create-report` must stop if any of the following are unresolved:

- `report_goal` is incomplete
- a section lacks a supporting data contract
- a metric lacks a source field or formula
- time definitions are missing or conflict
- analysis requirements exceed allowed inference bounds
- the output contract is incompatible with HTML
- target level is `L1` or `L2` but required level evidence is missing
