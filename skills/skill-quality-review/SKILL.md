---
name: skill-quality-review
description: Use when reviewing a new or updated Codex skill against the skill-creator standard, including SKILL.md frontmatter and body, agents/openai.yaml, bundled resources, trigger quality, progressive disclosure, and validation readiness.
---

# Skill Quality Review

Review the target skill as a reusable Codex skill, not as a generic prompt. Judge it against the `skill-creator` standard: concise metadata, strong triggering, lean SKILL body, appropriate bundled resources, and clear validation evidence.

## Review Target

Review any of these:

- a `SKILL.md`
- a full skill folder
- a proposed skill design
- an updated `agents/openai.yaml`
- a skill that triggers incorrectly, loads too much context, or drifts from its resources

If the user provides only a plan or excerpt, review that artifact and mark missing evidence explicitly.

## Required Workflow

1. Locate the target artifact.
   - If the user gives a path, inspect that path.
   - If the user pastes only `SKILL.md`, review that content.
   - If the user provides only a plan, review the plan and label missing evidence.
2. Inspect the discovery surface first.
   - Check the folder name, `name`, and `description`.
   - Treat `description` as the primary trigger index.
3. Check creator-specific structural rules.
   - Frontmatter should contain only `name` and `description`.
   - `name` should be lowercase hyphen-case.
   - `description` should carry the trigger conditions; do not rely on a body section to explain when to use the skill.
4. Review the body as an operating protocol.
   - Prefer concise procedural guidance over explanation.
   - Check whether the body stays focused on what another Codex instance needs to do the job.
5. Review bundled resources only as needed.
   - Read `agents/openai.yaml` if present.
   - Read `references/`, `scripts/`, or `assets/` only when they are relevant to the review.
   - Flag duplication between SKILL.md and bundled resources.
6. Produce findings first.
   - Prioritize trigger failures, protocol gaps, stale metadata, context bloat, and unsafe defaults.

## Review Rubric

### 1. Trigger and Metadata

Pass criteria:

- Folder name and frontmatter `name` match.
- `name` uses lowercase letters, digits, and hyphens only.
- Frontmatter contains only `name` and `description`.
- `description` explains what the skill does and when it should trigger.
- `description` includes concrete contexts, artifacts, file types, or user intents.
- `description` does not spend tokens narrating the workflow.

Red flags:

- Extra frontmatter fields that the creator standard does not call for.
- Vague descriptions such as "helps with skills".
- Descriptions that omit the trigger boundary and only describe implementation.
- Trigger logic hidden in a body section instead of the frontmatter.

### 2. Scope and Job Definition

Pass criteria:

- The skill solves one stable, reusable job.
- The job is specific enough that another Codex instance can tell when to use it.
- The skill is not a one-off project note or session artifact.
- Project-specific facts are included only if they generalize across repeated uses.

Red flags:

- The skill tries to be a general-purpose assistant.
- Multiple unrelated jobs share one skill.
- The body contains session history or maintenance notes that do not help execution.

### 3. Concision and Progressive Disclosure

Pass criteria:

- SKILL.md stays focused on the core workflow and decision rules.
- Large detail lives in `references/` when needed.
- Deterministic repeated work lives in `scripts/` when needed.
- Output resources live in `assets/` when needed.
- SKILL.md points directly to any important bundled resource.
- The body avoids repeating detailed reference material.

Red flags:

- SKILL.md is a knowledge dump.
- The same information appears in both SKILL.md and a reference file.
- The skill force-loads detail that could live in a resource file.
- Deep or hidden resource paths make discovery fragile.

### 4. Degrees of Freedom

Pass criteria:

- Judgment-heavy work uses principles and review heuristics.
- Semi-structured work uses checklists, templates, or explicit review steps.
- Fragile checks use concrete validation commands or deterministic artifacts.
- Rules are specific where failure would be costly and flexible where judgment is needed.

Red flags:

- A fragile review step is left as vague prose.
- The skill over-specifies judgment-heavy work.
- The body relies on slogans like "be careful" without a verification step.

### 5. Resource Fit

Pass criteria:

- `scripts/` exist only when repeatability or deterministic reliability justifies them.
- `references/` hold detailed material that should not live in SKILL.md.
- `assets/` are output resources, not extra documentation.
- The skill does not add extraneous files such as `README.md`, `INSTALLATION_GUIDE.md`, `QUICK_REFERENCE.md`, or `CHANGELOG.md`.
- `agents/openai.yaml`, if present, matches the current SKILL.md.

Red flags:

- Resources exist without a clear role.
- Assets contain documentation that belongs in `references/`.
- Extra documentation files clutter the skill.
- `agents/openai.yaml` over-promises or has drifted from the skill body.

### 6. Execution Protocol

Pass criteria:

- The workflow tells the reviewer what to inspect, in what order, and what to conclude from missing evidence.
- The skill distinguishes hard failures from improvement opportunities.
- The output contract is explicit.
- The skill says what evidence is required before declaring the reviewed skill acceptable.

Red flags:

- The skill is mostly principles with no sequence.
- The skill has no stop conditions or evidence requirements.
- The skill does not explain how to review partial artifacts.

### 7. Validation Readiness

Pass criteria:

- The reviewed skill can be checked with realistic prompts or artifacts.
- Trigger quality can be tested with positive and negative examples.
- Complex skills define how to validate behavior without leaking answers.
- The review considers whether `agents/openai.yaml` is stale and should be regenerated.

Red flags:

- The review has no way to tell whether the skill actually improved behavior.
- Validation examples simply restate the rule.
- Metadata is never checked against the live skill contents.

## Severity Guide

- **Blocker**: likely to make the skill fail to trigger, trigger broadly, violate creator rules, or mislead future users.
- **High**: likely to waste context, create drift between metadata and behavior, or weaken validation.
- **Medium**: likely to make the skill harder to maintain or extend.
- **Low**: wording or organization polish that does not materially change behavior.

## Output Format

Start with findings.

```markdown
**Findings**
- Blocker/High/Medium/Low: [issue]
  Evidence: [file/section or short excerpt]
  Why it matters: [behavioral risk]
  Fix: [specific edit]

**Scores**
- Trigger and metadata: /10
- Scope clarity: /10
- Concision and disclosure: /10
- Freedom matching: /10
- Resource fit: /10 or N/A
- Execution protocol: /10
- Validation readiness: /10

**Recommended Patch Plan**
1. ...
2. ...

**Open Questions**
- ...
```

If there are no serious issues, say so directly and note any remaining validation gaps.

## Review Reminders

- Prefer findings about trigger quality, protocol quality, and validation quality over style nits.
- Call out creator-specific violations explicitly:
  - extra frontmatter keys
  - body-only trigger guidance
  - unnecessary README-style docs
  - stale `agents/openai.yaml`
  - duplicated knowledge between SKILL.md and bundled resources
- Recommend scripts, references, or assets only when they reduce repeated work or increase reliability.
