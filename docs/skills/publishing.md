# Skills Publishing

## Publishing Goal

Skills are incubated inside Raincoat first and can later be exported into their
own Git repositories.

## Ready To Publish Checklist

A skill is a good publishing candidate when:

- the scope is stable enough to explain in one README
- `SKILL.md` is usable without repository-specific tribal knowledge
- scripts and assets live inside the skill directory
- metadata in `skill.json` is complete enough for public release

## Publishing Flow

1. incubate the skill in `skills/<skill-name>`
2. make the directory self-contained
3. export the directory into a standalone repository
4. add repository-level files such as `LICENSE`, `.gitignore`, and CI config
5. publish and maintain the standalone repository separately

## Git Operational Notes

These rules come from a real failure during repository maintenance and should be
treated as the default operating procedure for this repository.

### Use SSH For GitHub Remote Access

- keep `origin` on `git@github.com:LittleRain/raincoat.git`
- do not switch this repository back to HTTPS unless there is a specific reason
- the HTTPS path in this environment can hang or fail when Git invokes
  `credential-osxkeychain`

Observed failure:

```text
fatal: could not read Username for 'https://github.com': Device not configured
```

Practical rule:

- use SSH for `fetch`, `pull`, `push`, branch deletion, and remote inspection

### Verify Before Claiming Push Success

When a push looks stalled, do not assume it completed.

Check with:

```bash
git push origin <branch>
git ls-remote --heads origin <branch>
```

Only treat the push as complete after Git returns a normal success message.

### Worktree Constraint

This repository uses Git worktrees. A branch cannot be deleted while it is
checked out by any worktree.

Practical rule:

- if a branch is attached to the current worktree, detach or move that worktree
  first
- if `main` is checked out in another worktree, perform merges there instead of
  trying to check out `main` in the current directory

Typical flow:

```bash
git worktree list
git -C <main-worktree> merge --no-ff <feature-branch>
git -C <main-worktree> push origin main
git checkout --detach origin/main
git branch -D <feature-branch>
git push origin --delete <feature-branch>
```

## Export Expectations

`tooling/scripts/export-skill.sh [--loose] <skill-name> <destination-dir>` exports
**the files git would commit** for that skill:

- run it from a git work tree. It lists `git ls-files --cached --others
  --exclude-standard` under `skills/<skill-name>`, so anything `.gitignore` covers
  (scan output, generated dashboards, `plan-*` packages, `__pycache__`) is left
  behind, and the count of what was skipped is printed.
- a skill's own `.gitignore` is copied and **appended to**, never overwritten. Put
  a skill's generated-artifact rules in `skills/<skill>/.gitignore` rather than the
  repository root, otherwise they do not travel with the export.
- outside a git work tree the script refuses to run, because it cannot tell
  generated files from source. `--loose` is the explicit escape hatch: a fixed
  build-junk exclude list and a warning, no `.gitignore` semantics.
- repository boilerplate (`.DS_Store`, `dist`, `coverage`, `.env*`) is added to the
  destination `.gitignore`; anything else — `LICENSE`, CI config — is up to step 4.

Known gap: `tooling/tests/<skill>.sh` lives outside the skill directory, so the
repo-level end-to-end test does not travel with the export. Only the skill's own
`tests/` do.

## Versioning

Before standalone publication, the skill can use lightweight incubating
versions. After publication, versions should follow the release policy of the
new repository.
