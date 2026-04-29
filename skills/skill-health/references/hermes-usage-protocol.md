# Hermes Skill Usage Protocol

Hermes host integrations that want accurate `skill-health` reports must emit
explicit skill usage events and health warnings.

## Scope

Emit a usage event only when Hermes actually loads a skill into the current
execution context. Do not emit events for:

- skills catalog rendering
- metadata rendering
- candidate recall without load
- mere mention of a skill name in the model output

Valid trigger sources:

- `slash`
- `preloaded`
- `cron`
- `intent_match`

## Usage Event Schema

Append JSONL lines to:

`<HERMES_HOME>/skill_usage.jsonl`

Minimum event shape:

```json
{
  "skill_name": "skill-health",
  "timestamp": "2026-04-29T12:00:00Z",
  "agent": "hermes",
  "session_id": "abc123",
  "profile_name": "default",
  "profile_home": "/Users/you/.hermes",
  "source": "hermes-host",
  "scenario": "audit local skills after repeated routing errors",
  "trigger_source": "intent_match",
  "outcome_signal": "success"
}
```

Compatibility:

- `skill-health` also accepts `skill` or `name` in place of `skill_name`
- `ts` is accepted in place of `timestamp`
- `profile` is accepted in place of `profile_name`
- `hermes_home` is accepted in place of `profile_home`

## Health Event Schema

If the host fails to write usage events, do not block skill execution. Emit a
structured warning to:

`<HERMES_HOME>/skill_usage_health.jsonl`

Minimum warning shape:

```json
{
  "ts": "2026-04-29T12:00:01Z",
  "agent": "hermes",
  "source": "hermes-host",
  "code": "hook_not_enabled",
  "message": "skill_view completed but usage hook was not active"
}
```

Recommended codes:

- `log_path_missing`
- `log_path_unwritable`
- `hook_not_enabled`
- `session_id_missing`
- `json_write_failed`

## Profile Rules

Always resolve paths from `HERMES_HOME`:

- default profile: `~/.hermes`
- named profile: `~/.hermes/profiles/<name>`

Do not hardcode `~/.hermes/...` if `HERMES_HOME` is set.
