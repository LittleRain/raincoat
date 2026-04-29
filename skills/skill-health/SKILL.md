---
name: skill-health
description: Use when auditing installed agent skills, finding unused or stale skills, detecting overlapping skill trigger scenarios, reviewing Hermes/OpenClaw skill usage, or deciding which local skills to keep, merge, rewrite, or archive.
---

# Skill Health

Use the bundled CLI as the source of truth for Hermes inventory, usage import,
and reports. Do not manually infer skill health when the CLI can inspect it.

## Usage

Resolve `SKILL_DIR` from the installed skill location. Do not assume the current
working directory is the raincoat repository root.

First check the local review cadence:

```bash
SKILL_DIR=/path/to/skill-health
"$SKILL_DIR/scripts/skill-health" review-status
```

If `should_prompt` is true, briefly ask whether the user wants to run `doctor`
and mark false positives. If they decline, run:

```bash
"$SKILL_DIR/scripts/skill-health" review-snooze --days 7
```

Use `doctor` for the normal Hermes audit path. It scans the current Hermes
profile skill root, imports explicit host-emitted usage logs, and writes
Markdown plus JSON reports:

```bash
SKILL_DIR=/path/to/skill-health
"$SKILL_DIR/scripts/skill-health" doctor \
  --host hermes \
  --agent hermes \
  --scan-scope local_only \
  --language zh \
  --output-dir ~/.skill-health
```

Hermes paths are profile-aware:

- `HERMES_HOME` if set
- otherwise `~/.hermes`

By default, `skill-health` scans only `<HERMES_HOME>/skills`. It does not mix in
OpenClaw roots or Hermes `skills.external_dirs` unless `--scan-scope
local_plus_external` is explicitly requested.

Use explicit roots when auditing a repo, exported skill folder, or non-standard
installation path:

```bash
SKILL_DIR=/path/to/skill-health
"$SKILL_DIR/scripts/skill-health" doctor \
  --root /path/to/skills \
  --language zh \
  --output-dir ~/.skill-health
```

Use separate steps when debugging host adapters, importing a known JSONL log, or
reusing an existing index:

```bash
SKILL_DIR=/path/to/skill-health
"$SKILL_DIR/scripts/skill-health" scan --root /path/to/skills
"$SKILL_DIR/scripts/skill-health" import --agent hermes --events "$HERMES_HOME/skill_usage.jsonl"
"$SKILL_DIR/scripts/skill-health" report --format md --language zh
```

Hermes host-side skill usage recording must follow the protocol in
`references/hermes-usage-protocol.md`.

For a host-side rollout checklist that an agent can execute, read `README.md`.

Expected outputs:

- `skill-health-report.en.md`
- `skill-health-report.zh.md`
- `skill-health-report.md` using the requested `--language`
- `skill-health-report.json`
- `index.json`, `events.jsonl`, and `usage-status.json` in the state directory
- `feedback.jsonl` when the user confirms or suppresses findings
- `review-state.json` after `doctor`, `review-snooze`, or `review-done`

To record local feedback on a finding:

```bash
"$SKILL_DIR/scripts/skill-health" feedback \
  --finding-id duplicate_candidate:create-report:trade-weekly-report \
  --verdict suppressed \
  --note "Different jobs: creates report skills vs runs reports"
```

Use `--verdict confirmed` when the finding is useful. Use `--verdict suppressed`
when the finding is a false positive. Feedback affects only the matching
`finding_id`.

After the user finishes reviewing findings, run:

```bash
"$SKILL_DIR/scripts/skill-health" review-done
```

## Interpret

- Treat `outcome_signal` as an observable signal, not a true satisfaction score.
- Treat real usage as explicit Hermes/OpenClaw host-emitted skill load events
  only.
- For Hermes, natural invocation counts as usage only if the host actually
  loaded the skill through the same resolver / loader path and emitted a usage
  event.
- If usage logs are unavailable, require a `usage_unavailable` finding. Do not
  treat missing logs as proof that every skill is unused.
- Treat `unused_skill`, `stale_skill`, `duplicate_candidate`, and `weak_trigger`
  as review findings, not cleanup commands.
- Treat feedback as an overlay. Do not rewrite imported `events.jsonl`.
- Suppressed findings are hidden from active findings but still appear in the
  suppressed section for auditability.
- Report Hermes/OpenClaw roots as adapter status. Inferred roots are candidate
  paths, not confirmed host integration.

## Troubleshooting

- If scan coverage looks wrong, inspect `resolved_hermes_home`,
  `effective_roots`, and `scan_scope` in the JSON report before trusting the
  findings.
- If `usage_events` is 0, check `usage_log_path`, `files_checked`,
  `files_missing`, and `usage_logging_status` before assuming the skills were
  unused.
- If Hermes still reports no usage after skills were loaded, check whether the
  gateway / `skill_view` hook is still emitting events into
  `<HERMES_HOME>/skill_usage.jsonl`.
- If `usage_logging_status` is `warning`, check the Hermes host health event
  stream described in `references/hermes-usage-protocol.md`.

## Privacy

Keep raw prompts, local paths, usage logs, reports, and state local unless the
user explicitly asks for sharing or synchronization.

Local state files include:

- `~/.skill-health/events.jsonl`
- `~/.skill-health/index.json`
- `~/.skill-health/usage-status.json`
- `~/.skill-health/feedback.jsonl`
- `~/.skill-health/review-state.json`
- `~/.skill-health/skill-health-report.md`
- `~/.skill-health/skill-health-report.en.md`
- `~/.skill-health/skill-health-report.zh.md`
- `~/.skill-health/skill-health-report.json`

## Respond

1. State report path.
2. Summarize counts: indexed skills, usage events, findings.
3. List the highest-impact findings first:
   - overlapping skills
   - weak triggers
   - long-unused skills
4. Recommend manual next actions only. Never perform cleanup unless the user asks
   for a separate implementation step.

## Verify

Before claiming the audit is complete, verify at least one of:

- `~/.skill-health/skill-health-report.md` exists
- the CLI printed a JSON object with `report_dir`
- the report command produced findings or an explicit zero-findings summary
