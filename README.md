# Raincoat

Raincoat is an incubator repository for AI agent skills.

## What This Repository Is For

This repository is used to:

- incubate multiple skills in one place
- keep each skill self-contained enough to become its own repository later
- provide lightweight templates, conventions, and export tooling

## Repository Layout

- `skills/`: incubating skills and templates
- `docs/skills/`: conventions, publishing notes, and roadmap
- `tooling/scripts/`: helper scripts for scaffolding and export

## Current Skills

- `trading-weekly`
- `personal-kb`
- `create-report`
- `report-circle-weekly`

See [skills/README.md](/Users/raincai/Documents/GitHub/raincoat/skills/README.md) for the catalog.

## Common Workflows

```bash
./tooling/scripts/new-skill.sh <skill-name>
./tooling/scripts/export-skill.sh <skill-name> <destination-dir>
```

## Design Rules

- one directory under `skills/` equals one skill
- use kebab-case for skill names
- keep skill logic inside the skill directory whenever possible
- only extract shared tooling when reuse is clear
