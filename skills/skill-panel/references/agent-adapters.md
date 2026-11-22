# Agent 载体形态与接入新 agent

`agents.json` 是声明式的：哪些 agent、各自的 skill 根目录在哪、开关落在哪。本文记录各家的载体形态与踩过的坑，以及接入一个新 agent 的固定顺序。

## 适配表的四个概念

| 字段 | 作用 |
|---|---|
| `path` | 根目录，支持 `~` 展开与 `*` 通配。每一个匹配到的目录算一个 skill 条目 |
| `kind` | 来源类别：`user_skills` / `shared_pool` / `market` / `builtin` / `plugins` |
| `nested` | 子目录名（如 `skills`）。声明后**容器自身与内嵌子目录并列展开**，不做二选一 —— Bitto 实测两种形态都会被装载 |
| `dedupe` | 去重口径（如 `manifest`）。市场缓存里同插件多版本共存时，只认已安装的那个版本 |
| `store_meta` | 技能目录内的商店安装记录文件名（如 AutoClaw 的 `_store_meta.json`），命中即判「市场安装」并附完整商店记录 |

节点级还有 `builtin_libraries`（只作名称索引、不产出实体）、`install_manifests`（安装清单文件）、`excluded`（主动排除并写明原因）。

## AutoClaw：两处载体 + 一处内置库

AutoClaw 自己的 `workspace/AGENTS.md` 写明了官方口径：

> `~/.openclaw-autoclaw/skills/<skill-name>/SKILL.md` — 托管技能目录，放进去即自动发现，无需额外配置。**不要把技能装进 `~/.agents/skills/`（那个目录与其他工具共享）。**

| 载体 | 路径 | kind | 说明 |
|---|---|---|---|
| 托管技能 | `~/.openclaw-autoclaw/skills/` | `user_skills` + `store_meta` | 官方唯一声明可写的目录；43 个技能里 39 个带 `_store_meta.json` |
| 插件技能 | `~/.openclaw-autoclaw/plugin-skills/` | `builtin` | 软链指向 App 嵌入网关运行时，随 App 版本走 |
| 内置库 | `/Applications/AutoClaw.app/Contents/Resources/skills/` | 仅索引 | 44 个，App 随包分发，**不产出实体** |

要点：

- **`_store_meta.json` 是最规整的来源证据。** 逐技能给出 `skillId`(UUID) / `skillKey` / `version` / `installedAt`(epoch ms) / `source: "store"`，比 `installed_plugins.json` 更细。43 个里 39 个命中。这些 `skillId` 可以拿去做跨机器去重的稳定标识，当前版本还没用上。
- **剩下 4 个没有商店记录但仍判「内置」**（`aesthetic-preset-library`、`autoglm-remove-bg`、`infinite-canvas-output`、`yuandian`）—— 依据是它们在内置库中存在同名技能。这正是 `builtin_libraries` 索引的用途。
- **内置库不能当实体扫。** 托管目录里的 42 个技能与内置库同名，实测内容差异只有多出的 `_store_meta.json` 与 `.bundled-hash`（即内置库 + 商店元数据 = 托管副本）。两边都扫会凭空造出 42 组「同名冲突」，把真正的冲突淹没。
- **`plugin-skills/` 是软链**，且被正常装载 —— 这是 AutoClaw 支持软链的直接证据，所以 `supports_symlink: true`。
- **AutoClaw 会往共享池写**，与它自己「不要装进 `~/.agents/skills/`」的告示**相互矛盾**。结果是某个 agent 技能同时存在于托管目录（有版本）与共享池（无版本），构成一条 `same-body-diff-files` 冲突。
- **`agents/`（12 个 agent 定义）与 `workspace/` 不是技能载体**，已列在「主动排除」。`skills/.hot-update-tmp` 是热更新临时目录，隐藏目录天然跳过。
- **`state/openclaw.sqlite` 里的 `installed_plugin_index` / `skill_uploads` 表都是 0 行** —— 注册表不作为安装清单使用，`_store_meta.json` 才是权威来源。

## Bitto：三处载体

| 载体 | 路径 | kind | 形态 |
|---|---|---|---|
| 自建技能 | `~/.bitto/skills/` | `user_skills` | 技能目录自身带 `SKILL.md`；也支持容器 + 内嵌 `skills/`（两种都会被装载） |
| 用户插件 | `~/.bitto/plugins/` | `plugins` | 必须 `skills/<name>/SKILL.md`；插件根有 `plugin.json` 清单 |
| App 内置 | `/Applications/Bitto.app/Contents/resources/builtin-plugins/` | `builtin` | 同用户插件形态；升级 Bitto 会被覆盖，不可改 |

要点：

- **插件根的 `SKILL.md` 会被 Bitto 拒载。** 实证来自 Bitto 自身日志：`failed to load installed plugin plugin_id="rain-meeting-summary" error=validate installed plugin`。正确形态是 `skills/<name>/SKILL.md`，所以「插件根直接放 SKILL.md」是一条真 FAIL，对应规则 `plugin-root-skill-md`。
- **纯 MCP 插件会被剔除**：只含 `plugin.json` + `mcp.json`、不含任何 skill 的插件（如 `github`）列在页面「适配表」区供审计，不计为「缺 SKILL.md」。
- **`plugin.json` 是可用来源信号**：`author`、`version`、`extensions.bitto.kind`（`skill` / `agent`）。`kind=agent` 的插件还带 `agents/` `commands/` —— **只迁走其中一个 skill 不等于迁走整个插件**，页面会在详情里标出来。Bitto 没有安装清单，所以「市场安装」与「自建」无法自动区分，统一判为 `local` 并保留 `author` 供人工判断。
- **`name` 必须等于父目录名**：装载器会对不一致发警告（日志 `skill load warning ... name "x" does not match parent directory "y"`），技能仍能加载，所以这条规则定级为 `warn`。
- **Bitto 还会读项目级 skills**：日志显示 `project_skills_dir=<cwd>/.bitto/skills`，即 `<工作区>/.bitto/skills`。默认未纳入（与其他 agent 的项目级约定一致）。

## 上游仓库挂载：superpowers

`~/.codex/superpowers` 是 `github.com/obra/superpowers` 的 git clone（带 `.git` 与 `.claude-plugin/marketplace.json`），不是 agent 的 skill 根目录本身。它自带的 `.codex/INSTALL.md` 说明了装法：

```bash
git clone https://github.com/obra/superpowers.git ~/.codex/superpowers
ln -s ~/.codex/superpowers/skills ~/.agents/skills/superpowers
```

即：**实体在 `~/.codex/superpowers/skills`，通过 `~/.agents/skills/superpowers` 软链被各 agent 发现**。所以 `agents.json` 里给 codex 加了一条 `~/.codex/superpowers/skills/*` 的 root（kind `market`），否则这 14 个技能在清册里只体现为一个「容器」。

这条把全局唯一一组**成批版本漂移**暴露出来了：市场缓存的 4.0.3 与 clone 的 5.0.4 各带 14 个同名技能，其中 9 个正文已分叉（`brainstorming` 在 5.0.4 是 8 个文件 / 50KB，在 4.0.3 是 1 个文件 / 2.4KB），另 5 个内容逐字节一致、只是打包口径不同（这 5 个不报「版本漂移」）。**处理建议：整包升到 5.0.4，不要逐文件 merge。**

## 接入一个新 agent（五步）

新装一个 agent 之后照这个顺序做，别跳：

1. **先摸目录，别信文档。** 看 `<agent_home>` 顶层，把像 skill 根的目录全列出来。注意三种形态：`skills/<name>/`、`plugins/<plugin>/skills/<name>/`（两级容器，可能要声明 `nested`）、App bundle 内的内置目录。
2. **找「来源信号」。** 按可用性排序：`installed_plugins.json` > 技能目录内的安装记录（如 `_store_meta.json`，最细）> `plugin.json` 的 `author`/`extensions` > 什么都没有（只能判 `local`）。找到就做成 root 级 `store_meta` 或进 `install_manifests`。
3. **翻它自己的日志和文档。** `<agent_home>/logs/`、`workspace/AGENTS.md` 这类地方往往有官方的装载汇总与校验告警，比任何猜测都硬 —— Bitto 的两条规则、AutoClaw 的托管目录口径都是这么挖出来的。
4. **判断有没有「内置库 + 已安装副本」的投影关系。** 如果 App 内置目录与用户目录大批同名，**内置那份必须进 `builtin_libraries` 只作索引**，否则造假冲突。
5. **加进 `agents.json` → `scan` → 逐条复核新增的 FAIL。** 新增的 FAIL 必须一条条看证据确认真阳性，噪声规则该关就关。

软链支持怎么判：看这个 agent 的 skill 目录下有没有软链、以及它有没有真的装载软链指向的技能。**有实据才写 `true`**；没实据写 `null`，安装指令会自动回退成复制。

## 主动排除的目录（含原因）

被排除的东西都写在 `agents.json` 的 `excluded` 段里，连同原因，方便日后重新评估：

| 目录 | 原因 |
|---|---|
| `~/.qwen/skills`、`~/.iflow/skills` | 各仅 1 条，疑为残留 |
| `~/.minimax/.internal-skills` | 内部构建用，非用户可见 skill |
| `<工作区>/.bitto/skills` | Bitto 的项目级 skills 目录，随项目走 |
| `~/.openclaw-autoclaw/agents/*` | 12 个 agent 定义，不是技能载体 |
| `~/.openclaw-autoclaw/workspace` | 只含运行态文件，非技能目录 |
| `~/.codex/superpowers/{commands,agents,hooks,docs,tests}` | 上游仓库的非技能目录，只取 `skills/` |
| 任意项目级 skills 目录 | 随 git 仓库走，天然跨 agent 可见，无需迁移。要纳入就在 `agents.json` 加根目录，但同名撞车会明显变多 |
