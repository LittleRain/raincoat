# Skills Conventions

## Repository Role

Raincoat is a skills incubator. It is not only a runtime platform.

Each directory under `skills/` should be treated as a future standalone
repository candidate.

## Naming

- use kebab-case for skill directory names
- keep one directory equal to one skill
- prefer short, descriptive names such as `trading-weekly` or `personal-kb`

## Required Files

Each skill should include:

- `SKILL.md`: agent-facing instructions and workflow
- `README.md`: human-facing introduction and usage
- `skill.json`: metadata for cataloging and export
- `scripts/`: code or shell helpers owned by the skill
- `assets/`: prompts, templates, or static resources
- `examples/`: sample inputs and outputs

## Boundary Rules

- keep skills self-contained whenever possible
- do not couple a skill tightly to `apps/`, `tools/`, or `packages/`
- only move shared logic out of a skill after it is clearly reused
- if a skill cannot survive outside this repository, the boundary is too tight

## Evolution Rules

- start simple and avoid heavy per-skill infrastructure
- add tests or CI when a skill reaches repeated use or external publication
- prefer copying a stable pattern into the template over abstracting too early
