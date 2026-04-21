---
name: skill-quality-review
description: Use when reviewing newly written or updated agent skills, SKILL.md files, skill folders, skill trigger descriptions, bundled references, scripts, assets, or skill authoring plans before relying on them.
---

# Skill Quality Review

## Core Principle

A good skill is not a long prompt. It is a compact operating protocol that helps an agent load the right context, follow the right process, use deterministic tools where appropriate, and prove the result with evidence.

## Review Scope

Use this review for:

- A new or edited `SKILL.md`
- A skill directory with `references/`, `scripts/`, `assets/`, `agents/openai.yaml`, hooks, MCP files, or plugin metadata
- A proposed skill design before implementation
- A skill that triggers too often, too rarely, or produces inconsistent behavior
- A complex workflow skill that needs pressure testing

Do not require every skill to have scripts, references, assets, MCP, or hooks. Extra structure is justified only when it removes repeated work, reduces ambiguity, or improves reliability.

## Required Workflow

1. Locate the target skill artifact.
   - If the user gave a path, inspect that path.
   - If the user pasted only `SKILL.md`, review that content.
   - If the user only described a planned skill, review the plan and clearly label missing evidence.

2. Inspect the discovery surface first.
   - Check `name`, `description`, and any host-specific trigger metadata before reading the body deeply.
   - Treat `description` as a trigger index, not a workflow summary.
   - Identify the host schema when possible, such as Codex, Claude, a plugin system, or a project-local resolver.
   - Do not penalize valid host-specific fields such as `triggers`, `tools`, `version`, or `mutating` just because another host would not use them.
   - If the host schema is unknown, review behaviorally and label schema assumptions.

3. Review the body as an execution protocol.
   - Check whether it guides decisions under pressure.
   - Check whether it avoids restating obvious model knowledge.
   - Check whether it explains important constraints and tradeoffs.

4. Check reachability evidence when the host has a resolver, dispatcher, or skill loader.
   - Look for positive trigger examples that route to this skill.
   - Look for negative trigger examples that do not route to this skill when a neighboring skill is a better match.
   - If reachability cannot be tested, label it as unproven rather than assuming it works.

5. Review bundled resources if present.
   - Read only files directly needed to assess the skill.
   - Do not require resource directories when a single-file skill is enough.
   - Flag deeply nested references that make discovery fragile.

6. Produce findings first.
   - Prioritize behavior risks over style preferences.
   - Give concrete fixes, not generic advice.
   - Separate blockers from improvements.

## Review Rubric

### 1. Trigger Quality

Pass criteria:

- `name` is lowercase, short, and uses only letters, digits, and hyphens.
- `description` starts with `Use when...`, or the frontmatter provides an equivalent trigger index such as `triggers`, `keywords`, or host-specific routing metadata.
- `description` describes triggering conditions, symptoms, file types, tools, or user intents.
- `description` does not summarize the skill workflow.
- Important synonyms are included without becoming noisy.
- The skill has clear positive and negative trigger examples when the boundary is non-obvious.
- Host-specific routing fields, if present, are consistent with the description and body.

Red flags:

- Description says what the skill will do step by step.
- The skill has neither a trigger-oriented description nor an equivalent host-specific trigger field.
- Description is too vague, such as "For skills" or "Helps with development".
- Description uses first person.
- The skill name is a noun bucket like `helper`, `assistant`, or `tools`.
- The trigger overlaps heavily with another skill without explaining the boundary.

### 2. Scope and Job Definition

Pass criteria:

- The skill solves one stable, reusable job.
- It states when to use and when not to use the skill.
- It is not a one-off session narrative.
- Project-specific rules live in project docs unless they generalize across projects.
- The skill does not try to be a general-purpose assistant.
- Universal requirements are separated from conditional requirements, such as scripts, integration tests, evals, assets, or resolver entries.

Red flags:

- Multiple unrelated jobs share one skill.
- The body contains historical notes like "in the 2026-04-20 session we learned...".
- It includes generic best practices that the base model already knows.
- A host-specific completeness checklist is treated as universal without explaining when each gate applies.

### 3. Progressive Disclosure

Pass criteria:

- `SKILL.md` contains the core workflow, decision rules, safety rules, and resource map.
- Large details live in directly linked `references/` files.
- Repeated deterministic operations live in `scripts/`.
- Output templates, icons, fonts, examples, and boilerplate live in `assets/`.
- References are one level deep from `SKILL.md`.
- Long reference files have a table of contents or searchable headings.

Red flags:

- `SKILL.md` is a knowledge dump.
- The skill force-loads large files when a link or instruction would do.
- Reference content is duplicated in multiple files.
- Important references exist but are not mentioned from `SKILL.md`.

### 4. Degrees of Freedom

Pass criteria:

- Judgment-heavy tasks use principles, decision rules, and examples.
- Semi-structured tasks use templates, checklists, or pseudocode.
- Fragile or repetitive tasks use scripts, schemas, validators, or fixed commands.
- Hard rules explain why they exist and what to do instead.

Red flags:

- A fragile operation is described only in prose.
- A judgment-heavy workflow is over-scripted.
- The skill uses many `ALWAYS` or `NEVER` statements without rationale or boundaries.
- The skill asks the agent to "be careful" instead of giving a verifiable process.

### 5. Execution Protocol

Pass criteria:

- The workflow has concrete steps.
- Decision branches say what to read, run, ask, or stop on.
- The skill prevents common agent shortcuts and rationalizations.
- It includes failure modes if the task is discipline-heavy.
- It defines what evidence is required before claiming success.
- If the host has a resolver, dispatcher, or skill loader, the workflow explains how to verify that the skill is reachable.

Red flags:

- The skill is mostly motivational language.
- It tells the agent to think deeply but gives no operational next step.
- It has no stop conditions.
- It has no output contract.
- The skill is well written but has no evidence that the host can discover or invoke it.

### 6. Resource and Script Quality

Pass criteria:

- Scripts are included only when they improve repeatability or reliability.
- Scripts have clear inputs, outputs, exit codes, and readable errors.
- Destructive scripts default to dry-run or require explicit confirmation.
- Constants and defaults are named or explained.
- Assets are files meant to be copied or used, not extra documentation.
- `agents/openai.yaml`, if present, matches the skill and uses a default prompt that mentions `$skill-name`.

Red flags:

- Scripts silently swallow errors.
- Scripts require hidden environment setup.
- Scripts perform network, deletion, mutation, or production actions without clear safety rules.
- Assets contain documentation that belongs in `references/`.
- UI metadata over-promises compared with the skill body.

### 7. Validation and Pressure Testing

Pass criteria:

- The skill has concrete test prompts or realistic usage examples.
- There are positive and negative trigger tests.
- If validators, conformance tests, resolver checks, or scripts exist, review evidence prefers actual command output over manual inspection.
- If validation commands cannot be run, the review states why and treats validation as unproven.
- Complex discipline skills have pressure scenarios: time pressure, authority, sunk cost, or "this is simple" temptation.
- Evaluation looks at the transcript, not only the final answer.
- Revisions generalize from failures instead of overfitting one test.

Red flags:

- The skill has never been tried against a realistic task.
- Test prompts reveal the expected answer.
- The skill passes only because the test restates the rule.
- The review claims validation passed without command output, transcript evidence, or a stated reason validation was not run.
- There is no way to tell whether the skill improved behavior.

## Severity Guide

- **Blocker**: likely to make the skill not trigger, trigger incorrectly, skip the body, perform unsafe actions, or fail its core job.
- **High**: likely to cause inconsistent behavior, wasted context, missed verification, or bad resource selection.
- **Medium**: makes the skill harder to maintain, test, or adapt.
- **Low**: wording, organization, or polish that does not change core behavior.

## Output Format

Start with findings. Use this structure:

```markdown
**Findings**
- Blocker/High/Medium/Low: [issue]
  Evidence: [file/section or quoted short excerpt]
  Why it matters: [behavioral risk]
  Fix: [specific edit]

**Scores**
- Trigger quality: /10
- Scope clarity: /10
- Progressive disclosure: /10
- Freedom matching: /10
- Execution protocol: /10
- Resource/script quality: /10 or N/A
- Validation readiness: /10

**Recommended Patch Plan**
1. ...
2. ...

**Open Questions**
- ...
```

If there are no serious issues, say so clearly and list remaining test gaps.

## Quick Fix Patterns

Bad description:

```yaml
description: Use for skill review - checks description, structure, scripts, references, assets, and validation.
```

Better description:

```yaml
description: Use when reviewing newly written or updated agent skills, SKILL.md files, skill folders, trigger descriptions, bundled references, scripts, assets, or skill authoring plans.
```

Also acceptable when the host supports explicit trigger metadata:

```yaml
description: Turn raw features or scripts into complete agent-visible skills.
triggers:
  - "skillify this"
  - "is this a skill?"
  - "make this proper"
```

Bad prose rule:

```markdown
Always be very careful before deleting files.
```

Better operational rule:

```markdown
Before deleting files, show the exact paths and request approval. Prefer a dry-run command when the tool supports it because accidental deletion is irreversible.
```

Bad resource map:

```markdown
There are some docs in references.
```

Better resource map:

```markdown
- `references/aws.md`: read when deploying to AWS.
- `references/gcp.md`: read when deploying to GCP.
- `scripts/validate_config.py`: run before accepting generated config.
```
