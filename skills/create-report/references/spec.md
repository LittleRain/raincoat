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

### `output_contract`

Define the final report output contract.

Required fields:

- `format`
- `required_sections`
- `section_order`
- `required_blocks`
- `citation_rules`

Defaults:

- `format` must be `html`

### `skill_generation_contract`

Define the downstream package shape `create-report` must generate.

Required fields:

- `skill_name`
- `skill_title`
- `required_files`
- `required_assets`
- `required_examples`

Recommended default `required_files`:

- `SKILL.md`
- `agents/openai.yaml`

Recommended default `required_assets`:

- report outline template
- HTML contract template
- validation checklist

Recommended default `required_examples`:

- normalized spec example
- input inventory example
- output outline example

### `acceptance_checks`

Define pre-generation and post-generation validation.

Must include at least:

- `spec_completeness_checks`
- `spec_consistency_checks`
- `generation_readiness_checks`
- `html_output_checks`

## Stop Conditions

`create-report` must stop if any of the following are unresolved:

- `report_goal` is incomplete
- a section lacks a supporting data contract
- a metric lacks a source field or formula
- time definitions are missing or conflict
- analysis requirements exceed allowed inference bounds
- the output contract is incompatible with HTML
