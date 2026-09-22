# 跨 agent 原生开关矩阵

「禁用」优先改 agent 自己的开关，不动文件。声明全写在 `agents.json` 的 `toggle` 段里，`scripts/skillctl.py agents` 会把它打印出来。

## 矩阵

| agent | 粒度 | 写入方式 | 落点 | 值的语义 |
|---|---|---|---|---|
| WorkBuddy | **技能级** | JSON 嵌套键 | `~/.workbuddy/settings.json` → `skillOverrides.<name>` | `"off"` 完全不加载（同时关模型调用、用户显式调用与菜单展示）；`"user-invocable-only"` 仅手动可用；**键不存在 = 启用** |
| WorkBuddy | 插件级 | JSON 嵌套键 | `~/.workbuddy/settings.json` → `enabledPlugins` | `true` / `false` |
| Codex | 插件级 | TOML 段 | `~/.codex/config.toml` → `[plugins."<plugin>@<marketplace>"]` 的 `enabled` | `true` / `false` |
| Claude | 插件级 | 官方 CLI 优先 | `claude plugin disable/enable <plugin>`；兜底 `~/.claude/settings.local.json` → `enabledPlugins` | `true` / `false` |
| AutoClaw | **技能级** | JSON 嵌套键 | `~/.openclaw-autoclaw/openclaw.json` → `skills.entries.<name>.enabled` | `true` / `false` |
| 共享池 `~/.agents` | — | — | 无开关 | 共享池本体只是被各方引用的目录，没有自己的开关 |
| MiniMax | 无原生开关 | 回退文件级 | `<root>/.disabled/` | 目录级隐藏 |
| Bitto | 无原生开关 | 回退文件级 | `<root>/.disabled/` | 目录级隐藏 |

## 键名规则

只有 WorkBuddy 的**技能级**开关按技能名索引，规则是 `frontmatter.name` 优先，缺 `name` 时用目录身份 —— 这条来自客户端源码确认，必须与运行时一致，否则改了不生效。

插件级开关一律按 `<插件>@<市场>` 索引，取不到就回退用目录名。

## 文件级回退只支持两种写法

MiniMax / Bitto 没有原生开关，回退到文件级隐藏。有效性在 Codex 上做过 6 组探针、用 `codex debug prompt-input` 导出模型实际可见的技能清单逐项比对：

| 手法 | 结果 |
|---|---|
| 目录名前加 `.`（移进 `<root>/.disabled/<名字>`） | ✅ 被忽略 |
| `SKILL.md` 改名成 `SKILL.md.disabled` | ✅ 被忽略 |
| 目录名加 `.disabled` 后缀 | ❌ **仍然加载** |

所以回退路径只支持前两种。Bitto / MiniMax 上的对应行为是**未实测**的推断，`agents.json` 里对它们的 `file_level.verified` 保持 `false`。

## 一个 skill 的总状态取最坏值

同一个 skill 在 A 里启用、在 B 里被禁用，页面既不显示「启用」也不显示「禁用」，而是标黄并把每个 agent 的状态单独列出来。

判定「已禁用 / 仅手动可用 / 无开关记录」是读各 agent 自己的配置文件得出的，不是猜的。

## 查与改

```bash
python3 scripts/skillctl.py agents                                # 打印适配表与各 agent 开关机制
python3 scripts/skillctl.py state <skill>                         # 打印某 skill 在各 agent 的状态
python3 scripts/skillctl.py disable <skill> --agent workbuddy      # 干跑，只打印要改哪个键、旧值是什么
python3 scripts/skillctl.py disable <skill> --agent workbuddy --yes
python3 scripts/skillctl.py enable  <skill> --agent workbuddy --yes
```

**改完要重扫。** `state`、`check` 和页面读的都是最近一次 `scan` 写下的快照，不是每次实时读配置文件。所以 `disable --yes` 之后立刻跑 `state` 会看到旧状态 —— 此时工具会提示「开关文件已经比扫描结果新」，照它说的重跑 `scan` 即可（落盘后的提示里也写了这一句）。

## 未证实的三处

- **MiniMax** —— `~/.minimax/config.yaml` 已通读，未发现任何 skill 级或插件级启用开关。
- **Bitto** —— `~/.bitto/settings.json` 已通读，同样没有开关字段。
- **Claude 插件级停用是否会连带影响 `~/.claude/skills/` 下的实体** —— 未逐一实测。当前把 `~/.claude/skills/<name>` 当作一个「skills 目录插件」处理，键名规则与 WorkBuddy 一致（`frontmatter.name` 优先）。

发现新开关时，按 Codex 那一行的格式补进 `agents.json` 的 `toggle` 段即可，不用改代码。
