# Report Generation Prompt

Generate the report from this package only.

## Required Reads

1. `skill-manifest.yaml`
2. `examples/expected-output-inventory.json`
3. `assets/report-outline.md`
4. `assets/html-contract.md`
5. `assets/validation-checklist.md`

## Rules

- Keep the validated section order.
- Render every required chart, table, and explicit metric.
- Use only declared formulas, fields, and attribution evidence.
- Mark judgment-based metrics as inferred when used.
- Block unsupported analysis instead of guessing.
- Log file discovery, row counts, period detection, section progress, and output paths.
- Validate final HTML with `scripts/validate-output-inventory.py` for L1/L2 claims.
