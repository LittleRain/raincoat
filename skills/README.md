# Raincoat Skills

Raincoat is the incubator repository for AI agent skills.

## Why This Directory Exists

This repository is used to incubate multiple skills in one place before some of
them are published as standalone open source repositories.

The goals are:

- keep each skill easy to understand and evolve
- keep shared conventions in one place
- make it cheap to export a mature skill into its own Git repository

## Skill Catalog

| Skill | Status | Summary | Publish |
| --- | --- | --- | --- |
| `trading-weekly` | draft | Generate trading business weekly reports | incubating |
| `personal-kb` | draft | Organize and query a personal knowledge base | incubating |
| `create-report` | draft | Generate validated downstream HTML weekly-report skills | internal |
| `report-circle-weekly` | draft | Golden-sample downstream skill for circle weekly HTML reports | internal |

## Directory Layout

- `skills/<skill-name>`: a single incubating skill that should be able to grow
  into its own repository later
- `skills/_templates/basic`: starter template for new skills

## Create A New Skill

Copy `skills/_templates/basic` into `skills/<skill-name>` and then update:

- `SKILL.md`
- `README.md`
- `skill.json`

Use kebab-case for skill directory names.

## Publish A Skill

The intended flow is:

1. build and iterate inside this repository
2. keep the skill self-contained
3. export the skill into its own repository when it becomes stable

See `docs/skills/publishing.md` for publishing rules.
