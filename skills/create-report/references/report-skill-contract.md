# Report Skill Contract

This is the single source of truth for `create-report`. Downstream report skills
must be generated from this contract plus a normalized spec, not from raw prose.

## Required Stages

1. `requirement intake`: provide `assets/weekly-report-requirement-template.md`, require user self-fill, then import the completed markdown through `tools/intake-wizard.html` to generate structured spec output.
   For first-use or ambiguous requirement sessions, this wizard upload path is mandatory and takes priority over chat-based requirement interviews.
   Do not inspect local source data directories before wizard import output exists.
2. `execution design`: convert the requirement into a downstream report skill execution design, including data contracts, formulas, section flow, chart/table splitting, attribution rules, HTML contract, runner plan, and output inventory.
3. `sample test`: run the downstream skill against user-provided test data and produce `report.html`, `run.log`, `validation-report.json`, and inventory validation.
4. `tuning backflow`: fix downstream skill issues found in testing, then decide which lessons should backflow into `create-report`.
5. `packaging`: package the downstream report skill with contract, runner, assets, evidence, manifest, and validation results.

The final output is the downstream report skill. Rendered HTML is evidence that
the downstream skill works.

## Normalized Spec Minimum

The normalized spec must include:

- `report_goal`: report name, domain, audience, decision goals, success definition.
- `time_definition`: reporting period, comparison period, historical window.
- `report_outline`: stable section order and one contract per section.
- `data_contracts`: file patterns, dimensions, metrics, supported sections, required sample coverage.
- `analysis_rules`: metric formulas, attribution evidence, forbidden inferences, ratio fallback rules.
- `output_contract`: HTML sections, chart/table counts, required metrics, narrative requirements, empty-value policy.
- `skill_generation_contract`: skill name, title, target level, required files, evidence paths.

Each report section must declare:

- `section_id`, `title`, `purpose`
- `data_contracts` with primary/fallback precedence
- `charts_count`, `tables_count`, and required metric names
- chart splitting rules when one requirement line expands into multiple charts
- table schema and WoW columns when tables are required
- attribution rules and allowed evidence when conclusions are required
- empty-value policy for display fields and numeric fields

## Execution Design Minimum

Before implementation or packaging, the execution design must declare:

- file discovery strategy and required/optional inputs
- field normalization and alias handling
- metric calculation functions and formatter choices
- section build order and dependencies
- chart/table splitting rules
- attribution evidence boundaries
- runner entrypoint, logging checkpoints, and output paths
- HTML asset policy and browser/rendering expectations

## Level Contract

### L0 Documentation

Allowed when the requirement can be normalized but is not runnable yet.

Must include a normalized spec, expected output inventory, gap notes, HTML
contract, and a runner stub that fails clearly. Must not claim runnable output.

### L1 Runnable MVP

Requires all L0 materials plus real sample data covering at least two comparable
periods, a real runner, generated `report.html`, runtime logs, validation report,
and output inventory validation.

### L2 Publishable

Requires all L1 evidence plus self-contained packaging, no required CDN, no
absolute repo-local paths, regression tests, and browser evidence proving local
`file://` chart rendering.

## Blocking Conditions

Block or downgrade when any of these are unresolved:

- audience, decision goals, section list, section order, or output format
- section-to-dataset mapping
- metric source fields, formulas, or ratio fallback rules
- chart/table counts or chart splitting rules
- table schema or required WoW columns
- attribution evidence boundaries
- time period or comparison period
- data source precedence when multiple contracts can support a section
- sample-backed evidence for L1/L2
- template-first onboarding was skipped and no completed template markdown is available for import

## Allowed Inference

Allowed:

- rewrite prose into contract language
- infer stable `section_id` from explicit section titles
- generalize example filenames into filename patterns
- mark non-core presentation metrics as judgment-based when source fields exist

Not allowed:

- invent metric formulas, category rules, joins, chart fields, or causal claims
- silently switch data sources when the declared primary source is incomplete
- treat judgment metrics as official KPIs

## Validation Evidence

L1/L2 validation must prove:

- generated HTML contains all expected sections, charts, tables, and required metrics
- required conclusion blocks exist and do not include unsupported attribution
- required direction words appear when the spec demands up/down/flat language
- `nan`, `None`, `undefined`, and blank display keys do not leak into user-facing HTML
- logs include file discovery, row counts, period detection, section progress, and output paths

## Tuning Backflow

After sample test failures, classify each fix:

- downstream-only: business-specific category rules, copy, file naming, chart choices, or analysis preferences
- create-report backflow: reusable failure patterns such as missing inventory checks, weak attribution gates, empty-value leaks, chart splitting ambiguity, or evidence packaging gaps
- test-note only: one-off dirty data, temporary sample quirks, or manual corrections that should not become general guidance

Backflow only the reusable method, not the business-specific detail.
