# Validation Contract

Use this checklist for generated downstream report skills.

## Package Files

- `SKILL.md`
- `skill-manifest.yaml`
- `agents/openai.yaml`
- `assets/html-contract.md`
- `assets/report-outline.md`
- `assets/report-prompt.md`
- `assets/validation-checklist.md`
- `assets/base-report.css`
- `assets/chart-defaults.js`
- `examples/normalized-spec-summary.md`
- `examples/input_inventory.md`
- `examples/expected-output-inventory.json`
- `scripts/run-report.sh`
- `scripts/validate-output-inventory.py`

## L0 Documentation

- normalized spec and expected inventory exist
- runner is a clear failing stub
- blocking gaps are listed
- package does not claim runnable output

## L1 Runnable MVP

- all L0 checks pass
- real samples cover at least two comparable periods
- real runner creates `output/report.html`
- `output/run.log` and `output/validation-report.json` exist
- output inventory validation passes
- HTML is not a placeholder and uses the standard structure
- sample test findings are resolved or explicitly classified as downstream-only, create-report backflow, or test-note only

## L2 Publishable

- all L1 checks pass
- package is self-contained
- no required external CDN
- no absolute repo-local paths
- browser evidence proves local `file://` chart rendering
- regression tests cover missing values, zero denominators, and fallback paths

## Output Inventory Checks

- total section/chart/table counts match `examples/expected-output-inventory.json`
- section-level chart/table counts match
- explicit `required_metrics` appear in rendered HTML
- `judgment_metrics` are optional but must be labeled if used
- user-facing HTML does not contain `nan`, `None`, `undefined`, or empty key labels
- generated package must not contain markdown links to absent files

## Adjustment Backflow

- downstream-only fixes stay in the downstream report skill
- reusable failure patterns update `create-report` contracts, templates, validators, or tests
- one-off dirty data fixes stay in sample test notes
- every backflow change must name the failure mode it prevents
