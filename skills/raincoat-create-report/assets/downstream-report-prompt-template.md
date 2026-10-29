# Downstream Report Prompt Template

Generate the HTML report from the packaged contract only.

## Required Reads

1. `skill-manifest.yaml`
2. `examples/expected-output-inventory.json`
3. `assets/report-outline.md`
4. `assets/html-contract.md`
5. `assets/validation-checklist.md`

Use `assets/base-report.css` and `assets/chart-defaults.js` as the design and
chart runtime assets. For detailed styling rules, read `assets/DESIGN.md`
instead of inventing a new design system.

## Generation Rules

- Keep the validated section order.
- Render every chart, table, and explicit required metric declared in inventory.
- Use only declared formulas, fields, data-source precedence, and attribution evidence.
- Mark judgment-based display metrics as inferred when used.
- Block unsupported analysis instead of guessing.
- Follow declared table schemas, WoW rules, and empty-value policy.
- Emit runtime logs for file discovery, reads, row counts, period detection, section progress, and output paths.
- Do not claim a level higher than `skill-manifest.yaml` supports.

## Output

- Primary artifact: HTML.
- Include title, period metadata, navigation, sections, conclusions, and data notes.
- L1/L2 output must pass `scripts/validate-output-inventory.py`.
