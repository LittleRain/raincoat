# Review Output Template

Use this when the requirement cannot safely proceed, or when an existing report
skill needs a targeted adjustment.

## Decision

- `block` / `downgrade-to-L0` / `adjust-existing-skill`
- reason:

## Missing Or Conflicting Inputs

| Area | Missing or conflicting item | Why it blocks generation | Required answer |
|------|-----------------------------|--------------------------|-----------------|

## Impacted Output

- sections:
- charts:
- tables:
- metrics:
- attribution:

## Recommended Next Step

- answer the listed questions, or
- generate L0 documentation only, or
- patch the named downstream skill and rerun validation

## Backflow Decision

| Finding | Fix location | Why |
|---------|--------------|-----|
| | downstream skill / create-report / test notes | |

Use `create-report` only for reusable methods. Keep business-specific logic in
the downstream skill.
