# Raincoat Skills

<p>
  <a href="#english">English</a> | <a href="#中文">中文</a>
</p>

---

## English
<a id="english"></a>

Raincoat is the incubator repository for AI agent skills.

### Why This Directory Exists

This repository is used to incubate multiple skills in one place before some of
them are published as standalone open source repositories.

Goals:

- keep each skill easy to understand and evolve
- keep shared conventions in one place
- make it cheap to export a mature skill into its own Git repository

### Skill Catalog

| Skill | Status | Summary | Publish |
| --- | --- | --- | --- |
| `trade-weekly-report` | beta | Generate trading business weekly HTML reports | incubating |
| `create-report` | draft | Generate validated downstream HTML weekly-report skills | internal |
| `report-circle-weekly` | draft | Golden-sample downstream skill for circle weekly HTML reports | internal |

### Directory Layout

- `skills/<skill-name>`: one incubating skill that can evolve into its own repository
- `skills/_templates/basic`: starter template for new skills

### Create A New Skill

Copy `skills/_templates/basic` into `skills/<skill-name>` and then update:

- `SKILL.md`
- `README.md`
- `skill.json`

Use kebab-case for skill directory names.

### Publish A Skill

Intended flow:

1. build and iterate inside this repository
2. keep the skill self-contained
3. export the skill into its own repository when it becomes stable

See `docs/skills/publishing.md` for publishing rules.

---

## 中文
<a id="中文"></a>

Raincoat 是 AI Agent Skills 的孵化仓库。

### 为什么有这个目录

`skills/` 用于在同一仓库中孵化多个 skill，成熟后再按需拆分为独立开源仓库。

目标：

- 让每个 skill 易于理解和迭代
- 把共享规范集中维护
- 让成熟 skill 可以低成本导出为独立 Git 仓库

### 技能目录

| Skill | 状态 | 简介 | 发布属性 |
| --- | --- | --- | --- |
| `trade-weekly-report` | beta | 生成交易业务周报 HTML | incubating |
| `create-report` | draft | 生成经过校验的下游 HTML 周报 skill | internal |
| `report-circle-weekly` | draft | 圈子周报 HTML 的黄金样例下游 skill | internal |

### 目录结构

- `skills/<skill-name>`：一个可独立演进的 skill 目录
- `skills/_templates/basic`：新 skill 的起始模板

### 新建 Skill

将 `skills/_templates/basic` 拷贝到 `skills/<skill-name>`，然后更新：

- `SKILL.md`
- `README.md`
- `skill.json`

skill 目录名统一使用 kebab-case。

### 发布 Skill

推荐流程：

1. 在本仓库内开发与迭代
2. 保持 skill 自包含
3. 稳定后导出为独立仓库

发布规则见 `docs/skills/publishing.md`。
