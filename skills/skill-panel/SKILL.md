---
name: skill-panel
description: Use when the user wants to see, audit or clean up all the skills installed across the local agents (WorkBuddy, Codex, Claude, the shared ~/.agents pool, MiniMax, Bitto, AutoClaw) — inventorying the estate, finding duplicate or conflicting copies of the same skill, checking whether a skill would survive a move to another agent, enabling/disabling/uninstalling a skill through its agent's native toggle switch, or generating a local dashboard of everything installed. Also use it when a skill behaves differently in two agents and you need to know which copy each one actually loads.
---

# Skill Panel

One machine, many agents, each with its own `skills/` directory — plus a shared
pool and a lot of symlinks. This skill answers "what do I actually have, which
copies are the same thing, which ones are broken, and how do I turn one off".

`scripts/skillctl.py` is the single source of truth. Run it. Do not re-implement
its scanning, hashing or validation in shell — the interesting part is the
de-duplication and the evidence, not the directory walk.

## Requirements

- Python 3.9+ (standard library only, no third-party packages)
- No other dependency. The default `agents.json` lists macOS paths for
  app-bundled skills; on another OS those globs simply match nothing and every
  other agent still works.
- `state`, `disable` and `enable` read and write *other agents'* config files.
  That is the point of the tool, and it is also why every write defaults to a
  dry run.

## Workflow

1. **Scan.** `scripts/skillctl.py scan` walks every configured agent root,
   validates, and writes both the JSON data and the dashboard.
2. **Look.** Open the generated `skill-panel.html` (self-contained, no server) or
   ask for a specific skill with `check` / `state`.
3. **Decide.** `install` produces a migration command; `plan` produces a
   conflict-resolution package; `resolve` deduplicates directly. For a group
   whose bodies really diverge, the page offers a pick-a-canonical card;
   `resolve --canonical <group>=<path>` does the same thing from the CLI.
   A group with no right answer can be silenced with `dismiss`, and any
   `resolve` can be walked back with `undo`.
4. **Act, if asked.** `disable` / `enable` / `uninstall` / `resolve` are the only
   operations that touch skill content, and they require `--yes` to write. The
   page's buttons drive the same implementations over loopback.

```bash
python3 scripts/skillctl.py scan                 # inventory + validate + generate the page
python3 scripts/skillctl.py check <skill>        # validation detail, with file:line evidence
python3 scripts/skillctl.py state <skill>        # per-agent enable/disable state
python3 scripts/skillctl.py install <skill> [--to <agent>]
python3 scripts/skillctl.py agents               # the adapter table and each native toggle
python3 scripts/skillctl.py plan [--names a,b] [--grades auto,semi,manual]
python3 scripts/skillctl.py resolve [--names a,b] [--semi] [--yes]
python3 scripts/skillctl.py resolve --names x --canonical x=/abs/path --yes
python3 scripts/skillctl.py undo [--at <timestamp-prefix>] --yes
python3 scripts/skillctl.py dismiss --names x [--note "why"] --yes
python3 scripts/skillctl.py restore              # list the trash
python3 scripts/skillctl.py serve --open         # loopback-only, lets the page's buttons act
```

Every command reads and writes `~/.skill-panel/` and never this skill directory.
`--out <dir>` or `$SKILL_PANEL_OUT` moves that root; the CLI prints the resolved
paths, and `check` / `state` name the snapshot path when one is missing. If a
command says there is no scan, check that both commands resolved the same root.

## Read-only by default

`scan`, `check`, `state`, `install`, `agents` and `plan` never modify anything.
The write commands are `disable`, `enable`, `uninstall`, `resolve`, `undo` and
`dismiss` — and each of them:

- prints the exact diff (file, key, old value) and writes nothing unless `--yes`
  is passed;
- moves whatever it replaces or deletes into `~/.skill-panel/trash/` first, so
  nothing is destroyed;
- appends to `~/.skill-panel/ledger.json`.

`dismiss` is the one exception to "moves things": it only writes an `ignore`
flag into `overrides.json`, so its dry run prints the config line rather than a
file diff.

Prefer the agent's own native toggle over touching files. `agents.json` declares,
per agent, where that toggle lives and which values mean what; `agents` prints it.
Only MiniMax and Bitto fall back to file-level hiding, because no native switch
was found for them.

## Never

- Never delete a skill directory to "disable" it when the agent has a native
  switch — use the switch.
- Never pass `--yes` on the user's behalf. The dry run is the confirmation step.
- Never uninstall an app-bundled skill: the next app upgrade restores it, so the
  operation is a no-op that only creates confusion.
- Never trust a FAIL count without reading its evidence. `overrides.json` exists
  because automated judgement is not always right.
- Never let the tool pick the canonical copy for a group whose bodies really
  diverge. `resolve` on a `divergent` group needs an explicit `--canonical`, and
  the page shows candidate cards instead of a plain button, because which body
  is "right" is the user's call.
- Never assume a `divergent` group needs a human. Check its `shape`: a dangling
  link may be repaired automatically, and a `symlink-farm` or `shell` group is a
  relink problem rather than a merge problem.

## Outputs

Everything below lands in the artifact root — `~/.skill-panel/` by default, or
whatever `--out` / `$SKILL_PANEL_OUT` says. Nothing is written into the skill
directory, which stays pure code so it survives a read-only or
replaced-on-upgrade install.

| Path | What |
|---|---|
| `<root>/skill-panel.html` | generated dashboard, self-contained, double-click to open |
| `<root>/data/skills.json` | the scan, for the CLI and for further processing |
| `<root>/plan-<timestamp>.md` / `.sh` | conflict-resolution package (the `.sh` is dry-run by default) |
| `<root>/trash/` | uninstall destination — moved, never deleted |
| `<root>/ledger.json` | write-operation audit trail |

The dashboard can be previewed in a browser. When the user should see it, present
the generated `skill-panel.html` rather than pasting scan output into chat.

## Configuration

Three declarative tables sit at the skill root. They are data, not code — extend
them instead of patching `skillctl.py`:

- `agents.json` — which agents exist, which directories are their skill roots,
  and where each one's native toggle lives.
- `rules.json` — the validation rules and their thresholds.
- `overrides.json` — manual corrections to automated judgements.

These three are *this skill's own* files, not state scanned off the machine, so
a broken one is a hard error: if `rules.json` fails to parse, `scan` prints the
path and the JSON error and exits 2. It must not fall back to an empty rule
table — that would report every skill as clean, and an all-green scan on a
machine nobody cleaned is worse than a crash.

`references/agent-adapters.md` has the five-step recipe for wiring up a new
agent plus the per-agent quirks (AutoClaw's two carriers, Bitto's three, the
`superpowers` upstream clone). `references/agent-toggle-matrix.md` is the
cross-agent toggle matrix. `references/validation-rules.md` documents every rule.
