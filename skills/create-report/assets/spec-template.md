# 标准化周报 Spec 模板

## report_goal

- `report_name`:
- `domain`:
- `audience`:
- `decision_goals`:
- `success_definition`:

## business_context

- `business_summary`:
- `business_units`:
- `scope_notes`:

## terminology

- `terms`:
- `segment_rules`:

## semantic_contract

- `business_terms`:
  - `name`:
  - `definition`:
  - `source_fields`:
  - `hard_constraint`: `true` / `false`
  - `needs_clarification`: `true` / `false`
- `term_aliases`:
  - `alias`:
  - `canonical_term`:
- `segment_rules`:
  - `segment_name`:
  - `applies_to`:
  - `rule_logic`:
  - `source_fields`:
  - `allowed_categories`:
- `rule_priority`:
- `null_fallback`:
- `semantic_examples`:
  - `input`:
  - `expected`:
- `judgment_terms`:

## time_definition

- `reporting_granularity`:
- `current_period_definition`:
- `comparison_period_definition`:

## report_outline

- `section_id`:
- `title`:
- `purpose`:
- `required_views`:
- `required_metrics`:
- `required_dimensions`:
- `required_outputs`:
- `narrative_expectations`:
- `view_inventory`:
  - `charts_count`:
  - `tables_count`:
  - `required_metric_names`:
  - `required_dimensions`:
  - `required_text`:
  - `judgment_metric_candidates`:
  - `llm_judgment_allowed`:
  - `source_requirement_evidence`:
- `table_schemas`:
- `table_layout_contract`:
  - `layout_mode`: `separate_tables_by_dimension` / `dimension_as_rows` / `dimension_as_columns` / `hybrid_section_with_subtables` / `unresolved`
  - `split_dimension`:
  - `row_dimensions`:
  - `column_dimensions`:
  - `required_table_instances`:
  - `table_grain`:
  - `source_phrase`:
  - `interpretation_reason`:
  - `ambiguity_level`: `low` / `medium` / `high`
- `narrative_schema`:
- `section_data_mapping`:
  - `primary_contracts`:
  - `fallback_contracts`:
  - `merge_or_override_rule`:

## data_contracts

- `contract_id`:
- `display_name`:
- `file_name_pattern`:
- `time_granularity`:
- `dimensions`:
- `metrics`:
- `field_notes`:
- `supported_sections`:
- `sample_file_required`:
- `period_coverage_expectation`:
- `priority_for_sections`:

## analysis_rules

- `must_explain_conditions`:
- `allowed_evidence`:
- `forbidden_inferences`:
- `metric_calculation_contracts`:
- `ratio_metric_fallback_rules`:
  - `metric_name`:
  - `primary_formula`:
  - `fallback_formula`:
  - `fallback_condition`:

## output_contract

- `format`: `html`
- `required_sections`:
- `section_order`:
- `required_blocks`:
- `citation_rules`:
- `expected_output_inventory`:
  - `totals`:
    - `sections`:
    - `charts`:
    - `tables`:
  - `required_metrics`:
  - `required_dimensions`:
  - `required_text`:
  - `judgment_metrics`:
  - `semantic_contract`:
  - `table_layout_contract`:
  - `sections`:
- `table_column_rules`:
- `wow_display_rules`:
- `narrative_direction_rules`:
- `runtime_logging_rules`:
- `runtime_dependency_policy`:
  - `mode`: `self-contained-or-local`
  - `allow_external_cdn`: `false`
  - `file_protocol_must_render`: `true`
- `empty_period_column_policy`:
  - `hide_when_all_rows_empty`:
  - `applies_to_tables`:

## skill_generation_contract

- `skill_name`:
- `skill_title`:
- `skill_level`: `L0` / `L1` / `L2`
- `level_readiness`:
  - `real_samples_present`:
  - `two_period_coverage`:
  - `real_runner_present`:
  - `validation_evidence_present`:
  - `browser_evidence_present`:
- `required_files`:
- `required_references`:
- `required_assets`:
- `required_examples`:
- `required_tests`:

## acceptance_checks

- `spec_completeness_checks`:
- `spec_consistency_checks`:
- `generation_readiness_checks`:
- `html_output_checks`:
- `output_inventory_checks`:
- `runnable_readiness_checks`:
- `runtime_log_checks`:
- `level_acceptance_checks`:
