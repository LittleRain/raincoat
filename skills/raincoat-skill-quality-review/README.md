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

## Requirements and compatibility

- No runtime or third-party package dependencies; this is an instruction-only
  skill.
- The review rubric refers to the `skill-creator` standard. The reviewer needs
  access to the applicable current standard (for example, the installed
  `skill-creator` skill); this directory does not bundle or version that
  standard.
- It can inspect skills targeting different hosts, but must evaluate each
  against that host's schema and the applicable creator rules.
- License is pending maintainer confirmation; this directory does not include
  a separate `LICENSE`.

## 迁移交付状态

当前为 `draft`。本轮完成包内路径与命名整理；许可来源尚未确认，不能正式发布。macOS 的具体检查见仓库迁移验收记录；Windows、其他宿主的原生安装与自动发现未实测。历史上标注 beta 的元数据不作为本轮验收结论。
