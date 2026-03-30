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

## Export Expectations

The future export script should:

- copy the skill directory into a clean destination
- preserve `SKILL.md`, `README.md`, `skill.json`, `scripts/`, `assets/`, and
  `examples/`
- optionally generate repository boilerplate files

## Versioning

Before standalone publication, the skill can use lightweight incubating
versions. After publication, versions should follow the release policy of the
new repository.
