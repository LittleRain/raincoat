---
name: __SKILL_NAME__
description: Use when generating or updating the __SKILL_TITLE__ HTML report from packaged contracts, declared input files, and validated output inventory.
---

# __SKILL_TITLE__

Current level: __SKILL_LEVEL_LABEL__

## Purpose

Generate the HTML report using this package's normalized contract. This skill
executes a fixed report contract; it does not redefine metric formulas, section
order, data mappings, or attribution rules.

## Inputs

- data files declared in [input_inventory.md](./examples/input_inventory.md)
- package level and evidence in [skill-manifest.yaml](./skill-manifest.yaml)
- expected output counts in [expected-output-inventory.json](./examples/expected-output-inventory.json)

## Workflow

1. Confirm the package level in `skill-manifest.yaml`.
2. Read the report outline, HTML contract, and expected output inventory.
3. Map input files to declared data contracts.
4. Build each section in the validated order.
5. Generate conclusions using only declared evidence.
6. Validate the rendered HTML before claiming L1 or L2 output.

## Constraints

- output HTML only
- do not change section order
- do not infer undeclared formulas, joins, or attribution
- do not claim a level higher than the manifest supports
- do not depend on external CDN/network for delivered charts

## References

- [skill-manifest.yaml](./skill-manifest.yaml)
- [input_inventory.md](./examples/input_inventory.md)
- [expected-output-inventory.json](./examples/expected-output-inventory.json)
- [html-contract.md](./assets/html-contract.md)
- [report-outline.md](./assets/report-outline.md)
- [report-prompt.md](./assets/report-prompt.md)
- [validation-checklist.md](./assets/validation-checklist.md)
