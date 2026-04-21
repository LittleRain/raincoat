# Skill Quality Review

Review newly written or updated agent skills before relying on them.

## What It Does

This skill gives an agent a structured review protocol for `SKILL.md` files,
skill folders, trigger descriptions, bundled references, scripts, assets, and
skill authoring plans.

It focuses on behavioral risk: whether the skill triggers correctly, stays in
scope, uses progressive disclosure, matches the right degree of freedom, has a
clear execution protocol, and can prove its output with evidence.

## Directory Layout

- `SKILL.md`: agent-facing review workflow and rubric
- `skill.json`: repository catalog metadata
- `agents/openai.yaml`: OpenAI agent UI metadata

## Notes

The skill is intentionally host-neutral. When reviewing a skill, identify the
target host schema first and avoid treating one platform's frontmatter format as
universal.
