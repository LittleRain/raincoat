---
name: create-report
description: Use when turning a business weekly-report requirement, sample report, or report adjustment request into a reusable HTML report skill, especially when chart counts, metric definitions, attribution rules, or input data contracts need to be made reliable.
---

# Create Report

## Purpose

Turn unstable business report requirements into a validated downstream
`report-*` skill. The core job is to normalize intent into a machine-checkable
contract, design the downstream skill execution plan, test it with user data,
and package a reusable downstream report skill.

## Output

The deliverable is a downstream report skill. HTML is test evidence and the
runtime artifact produced by that downstream skill, not the primary output of
`create-report`.

## Use For

- Creating a new HTML weekly or biweekly report skill from requirements.
- Tightening an existing report skill after missing charts, empty fields, weak attribution, or wrong chart splitting.
- Converting free-form `需求.md` into a structured report contract.

Do not use this skill to generate one-off report prose. Use the downstream
report skill when the contract already exists and only the report needs to run.

## Workflow

1. Requirement intake: provide the weekly report template, ask the user to fill it offline, then import the completed markdown into `tools/intake-wizard.html` to generate structured spec artifacts.
2. Execution design: build the downstream report skill contract, including data sources, formulas, section logic, chart/table splitting, attribution rules, HTML contract, runner plan, and output inventory.
3. Sample test: use the user's test data to generate HTML, logs, and validation evidence. This sample test is the proof step before L1/L2 packaging.
4. Tuning Backflow: adjust the downstream report skill from test findings; backflow only reusable methods into `create-report`.
5. Packaging: package the downstream report skill with the validated contract, runner, assets, evidence, and manifest.

## Hard Gates

- Never generate a downstream skill directly from raw business prose or from interview-style Q&A notes.
- Default onboarding path is template-first, then wizard import. Do not replace this with multi-round questioning when the user has a clear requirement scenario.
- HTML is the only supported primary output format.
- Every section must have data contracts, expected charts/tables, required metrics, and attribution evidence rules when conclusions are requested.
- L1/L2 packages require real samples, real runner evidence, generated HTML, logs, and output inventory validation.
- L2 additionally requires standalone packaging and browser evidence that local `file://` rendering works.
- Missing chart/table counts, missing metric formulas, unresolved data-source precedence, or unsupported attribution must block or downgrade to L0.
- The generated package must not reference files that are absent from that package.
- Do not backflow every downstream fix into `create-report`: business-specific rules stay in the downstream skill; reusable failure patterns become create-report guidance; one-off dirty data fixes stay in test notes.

## Resource Map

- Canonical contract: [report-skill-contract.md](./references/report-skill-contract.md)
- User-facing questionnaire: [spec-template.md](./assets/spec-template.md)
- User fill-in template: [weekly-report-requirement-template.md](./assets/weekly-report-requirement-template.md)
- Browser intake wizard: [intake-wizard.html](./tools/intake-wizard.html)
- Validation rules: [validation-contract.md](./assets/validation-contract.md)
- Gap and adjustment output: [review-output-template.md](./assets/review-output-template.md)
- Downstream prompt rules: [downstream-report-prompt-template.md](./assets/downstream-report-prompt-template.md)
- Design assets: [DESIGN.md](./assets/DESIGN.md), [base-report.css](./assets/base-report.css), [chart-defaults.js](./assets/chart-defaults.js)
- Generators and validators: `scripts/create-report-skill.sh`, `scripts/build-output-inventory.py`, `scripts/validate-output-inventory.py`
