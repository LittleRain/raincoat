# Raincoat

<p>
  <a href="#english">English</a> | <a href="#中文">中文</a>
</p>

---

## English
<a id="english"></a>

Raincoat is an incubator repository for AI agent skills.

### What This Repository Is For

This repository is used to:

- incubate multiple skills in one place
- keep each skill self-contained enough to become its own repository later
- provide lightweight templates, conventions, and export tooling

### Repository Layout

- `skills/`: incubating skills and templates
- `docs/skills/`: conventions, publishing notes, and roadmap
- `tooling/scripts/`: helper scripts for scaffolding and export

### Current Skills

- `trade-weekly-report`
- `create-report`
- `report-circle-weekly`

See [skills/README.md](/Users/raincai/Documents/GitHub/raincoat/skills/README.md) for the catalog.

### Common Workflows

```bash
./tooling/scripts/new-skill.sh <skill-name>
./tooling/scripts/export-skill.sh <skill-name> <destination-dir>
python3 tools/wecom_archive.py --draft /path/to/wecom_doc_decoded_draft.md --structured /path/to/wecom_doc_structured_tables.md --out-dir /tmp
node tools/wecom_capture_opendoc.js --url "https://doc.weixin.qq.com/doc/w3_xxx?scode=xxx" --out-dir /tmp
```

### Design Rules

- one directory under `skills/` equals one skill
- use kebab-case for skill names
- keep skill logic inside the skill directory whenever possible
- only extract shared tooling when reuse is clear

---

## 中文
<a id="中文"></a>

Raincoat 是一个用于孵化 AI Agent Skills 的仓库。

### 仓库用途

本仓库用于：

- 在一个仓库中孵化多个 skill
- 保持每个 skill 足够自包含，后续可独立拆仓
- 提供轻量模板、规范和导出工具

### 目录结构

- `skills/`：skill 与模板
- `docs/skills/`：规范、发布说明和路线图
- `tooling/scripts/`：脚手架与导出辅助脚本

### 当前技能

- `trade-weekly-report`
- `create-report`
- `report-circle-weekly`

完整目录见 [skills/README.md](/Users/raincai/Documents/GitHub/raincoat/skills/README.md)。

### 常用流程

```bash
./tooling/scripts/new-skill.sh <skill-name>
./tooling/scripts/export-skill.sh <skill-name> <destination-dir>
python3 tools/wecom_archive.py --draft /path/to/wecom_doc_decoded_draft.md --structured /path/to/wecom_doc_structured_tables.md --out-dir /tmp
node tools/wecom_capture_opendoc.js --url "https://doc.weixin.qq.com/doc/w3_xxx?scode=xxx" --out-dir /tmp
```

### 设计规则

- `skills/` 下一个目录对应一个 skill
- skill 名称统一使用 kebab-case
- 尽量把 skill 逻辑放在 skill 目录内部
- 只有复用价值明确时才抽取共享工具
