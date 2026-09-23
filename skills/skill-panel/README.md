# Skill Panel · 本机 skill 面板

同一台机器上装了多个 agent（WorkBuddy / Codex / Claude / 共享池 / MiniMax / Bitto / AutoClaw），每个都有自己的 `skills/` 目录，外加一个共享池和一大堆软链。这个 skill 回答四个问题：

**我到底有什么 → 哪些副本其实是同一个东西 → 哪些已经坏了 → 怎么把某一个关掉。**

## 定位

**看是只读的，改是要点确认的。** 各 agent 的开关状态是读它们的配置文件得出来的，所以页面上的「已禁用 / 仅手动可用」不是猜测。写操作走两步：先干跑给你看要改哪个文件的哪个键、旧值是什么，加 `--yes` 才落盘；落盘前所有被替换或删除的东西先移进回收站，不真删。

**页面脱离服务也能用** —— 双击产物目录里的 `skill-panel.html`（默认 `~/.skill-panel/skill-panel.html`）打开是只读模式，操作按钮只生成命令让你自己粘到终端。想要「点一下就生效」，跑 `serve`（只绑 `127.0.0.1`，带一次性 token）。

**状态是快照，不是每次实时读的。** `scan` 会把各 agent 的开关状态一并算进 `~/.skill-panel/data/skills.json`，`state`、`check` 和页面展示的都是这份快照。所以改完开关（用 `disable` / `enable`，或自己动手改了配置文件）要**重跑 `scan`** 才会刷新。工具不会让你自己发现这件事：检测到开关文件比快照新时 `state` 会主动提示，`--yes` 落盘后也会提醒一句。

## 依赖

只需要 Python 3.9+，全部用标准库，无第三方依赖。默认的 `agents.json` 里带 macOS 的 App 路径（`/Applications/*.app/...`）；换到别的系统，这些通配符只是匹配不到东西，其余 agent 照常工作。

版本下限是**被测出来的**，不是写在文档里的承诺：别人机器上的 `python3` 很可能就是系统自带的那一个（macOS 至今是 3.9.6），所以 `tests/test_skillctl.py` 里有一条 AST 断言，注解里一旦出现 3.10 才有的 `X | Y`（PEP 604）就直接失败 —— 那种写法会在 import 阶段抛 `TypeError`，整条命令连错误提示都给不出。

## 快速开始

```bash
# 扫描 + 校验 + 生成页面（页面双击即开，离线自包含）
python3 scripts/skillctl.py scan

# 看单个 skill 的校验详情 + 各 agent 的启用状态（带 文件:行号 证据）
python3 scripts/skillctl.py check <skill>
python3 scripts/skillctl.py state <skill>

# 生成安装指令（缺省列出所有尚未持有的 agent）
python3 scripts/skillctl.py install <skill>
python3 scripts/skillctl.py install <skill> --to codex

# 列出 agent 适配表与各自的开关机制
python3 scripts/skillctl.py agents

# 启用 / 禁用 —— 走各 agent 的原生开关，不删内容
python3 scripts/skillctl.py disable <skill> --agent workbuddy          # 干跑，只打印要改什么
python3 scripts/skillctl.py disable <skill> --agent workbuddy --yes    # 真改
python3 scripts/skillctl.py enable  <skill> --agent workbuddy --yes

# 卸载 —— 移进回收站，不真删
python3 scripts/skillctl.py uninstall <skill> --agent codex --yes
python3 scripts/skillctl.py restore                                    # 列出回收站里能还原的东西

# 冲突处理方案包（md 清单 + 默认干跑的 sh 脚本）
python3 scripts/skillctl.py plan --grades auto,semi,manual

# 去重：默认干跑；正文分叉的组要指定留哪份
python3 scripts/skillctl.py resolve --names <组名> --yes
python3 scripts/skillctl.py resolve --names <组名> --canonical <组名>=<绝对路径> --yes

# 反悔：按台账把上一次去重退回去
python3 scripts/skillctl.py undo --yes

# 这一组就是先不动：别再提醒
python3 scripts/skillctl.py dismiss --names <组名> --note "两侧都在用" --yes

# 直连模式：页面上的按钮点一下就生效
python3 scripts/skillctl.py serve --open
```

## 通用代码与本地产物是分开的

这个 skill 目录里只有**通用代码**：引擎、三个声明式配置表、页面模板、测试。所有**本地产物**（扫描快照、仪表盘、方案包、回收站、台账）都落在产物目录里，默认 `~/.skill-panel/`：

```bash
python3 scripts/skillctl.py scan --out /tmp/sp          # 本次换落点
SKILL_PANEL_OUT=/tmp/sp python3 scripts/skillctl.py scan # 用环境变量换落点
ls ~/.skill-panel/                                       # 默认落点
```

优先级：`--out` > `$SKILL_PANEL_OUT` > `~/.skill-panel/`。`--out` 放子命令前后都可以。

**同一次 scan 之后，所有命令必须用同一个落点**，否则 `check` / `state` 会找不到快照（提示里会写明它找的是哪个路径）。

为什么不写在 skill 目录里：市场式安装（`plugins/cache/<市场>/<插件>/<版本>/skills/…`）会被整目录替换，升级后产物就没了；装到只读位置（App 自带内置库）直接写失败；而且产物含本机路径和命中的凭据原文，本就不该跟代码一起走。

| 落点 | 文件 | 说明 |
|---|---|---|
| `~/.skill-panel/` | `skill-panel.html` | 主产物。自包含单文件，数据内联，双击即开，可直接发人 |
| | `data/skills.json` | 扫描数据。给 CLI 子命令和二次加工用 |
| | `plan-<时间戳>.md` / `.sh` | 冲突处理方案包。md 给人看，sh 给机器跑（默认干跑） |
| | `trash/` | 卸载回收站。只移不删 |
| | `ledger.json` | 写操作台账 |

留在 skill 目录里的，只有一个字都不用改也能跑的东西：

| 文件 | 说明 |
|---|---|
| `agents.json` | **agent 适配表** —— 加减 agent / 根目录 / 开关落点只改这里 |
| `rules.json` | **校验规则表** —— 加规则、调阈值只改这里 |
| `overrides.json` | **人工覆盖表** —— 自动判定不可能全对，这里是你纠正的唯一入口 |
| `assets/dashboard_template.html` | 页面模板。数据由 `scan` 注入成 `skill-panel.html` |

三张配置表是**本 skill 自己的**文件，不是从机器上扫来的状态，所以坏了会**直接报错退出**，不会「当没配过」继续跑：

```text
$ python3 scripts/skillctl.py scan
rules.json（…/rules.json）不是合法 JSON：Expecting value: line 1 column 14 (char 13)
  改回去，或者删掉这个文件让它走内置默认值。
```

（退出码 2，不会继续扫描。）

这条是刻意从严的。拿读别人状态文件那种「坏了就跳过」的兜底来读自己的配置，会造出最坏的一种失败：`rules.json` 里多一个逗号 → 空规则表 → 全场 PASS，输出跟「这台机器真干净」长得一模一样，唯一的信号是 FAIL 数突然归零 —— 而那正是没人会去怀疑的信号。

同理，规则表里写了 `detector` 却没有对应实现的名字也会在启动时被拒（dispatch 是 if/elif 链，拼错的名字会掉进最后的分支拿到空证据，那条规则从此永远不报任何东西，而表里它明明写着）。

## 四个核心概念

### 1. 条目 vs 唯一实体

「条目」= 某个 agent 的某个根下的某个目录。「唯一实体」= 按 `realpath` 归一化后的真实目录。

一个实体可以被多个 agent 引用，引用分两种：

- **实体持有** —— 目录本体就在这个 agent 下
- **软链引用** —— 这个 agent 只有一个软链，实体在别处

**软链是一等公民。** 本机的实际架构就是「`~/.agents/skills` 当共享池 + claude / minimax 软链引用」，所以：

- 迁移默认建议 `ln -s` 而不是复制 —— 复制会持续制造第二份实体
- 校验会报「目标 agent 软链支持未知」，此时指令自动回退为 `cp -R`

### 2. 类型标识（按来源可验证）

| 类型 | 判定依据 |
|---|---|
| **内置** | 位于 agent 的系统内置目录（App bundle / `.system` / `.builtin-skills`）；或虽无安装记录、但 App 内置库中存在同名技能 |
| **市场安装** | 命中 `installed_plugins.json` 的 `installPath`、命中技能目录内的商店安装记录（如 AutoClaw 的 `_store_meta.json`），或位于市场插件缓存 |
| **本地自建** | 其余（用户 skills 目录、共享池、自建 plugins/） |

**「自动生成」不是来源，是属性** —— 降级为二级标记，只在 frontmatter 有 `agent_created: true` 时打上。实测：全盘 448 个实体里只有 16 个带这个字段（且全在 WorkBuddy），codex / claude / minimax 的 skill 完全没有这个标记，所以它无法承担「主类型」的角色。

### 3. 两级校验

- **FAIL** —— 阻塞跨 agent 迁移，必须先修
- **WARN** —— 质量/健壮性提示，不阻塞

每条结论都带 `文件:行号` 证据。规则全集与阈值见 [`references/validation-rules.md`](references/validation-rules.md)。

以一台 macOS 机器为样例，当前分布是：**FAIL 13 个实体 / WARN 108 / PASS 327**（实体总数 448）。这个数字随机器变化，只作量级参考 —— 你自己的数字以 `scan` 输出为准。

`name-dir-mismatch` 是典型的噪声规则：命中 58 条里，31 条是上游仓库成批加前缀（`gstack-review` → `name: review`）、15 条是有意的中文显示名（`adhoc-query` → `name: 数据查询`）、其余才是真实不一致。**属于噪声就把它的 `enabled` 改成 `false`**（`rules.json` 每条规则都支持 `enabled` 开关，默认 true）。

`疑似凭据硬编码` 规则三次命中全部逐条核实为真阳性，不是模式误命中：两条命中的是**同一个以 base64 形式写在脚本里的 GitLab PAT**，另一条是某个商店技能自带的**飞书 app token**。核对原文请直接跑 `python3 scripts/skillctl.py check <skill>`；本文件不转载凭据内容。

### 4. 黑话对照表

页面上尽量说人话，括号里保留技术术语，鼠标悬停有解释。完整对照：

| 页面上写的 | 技术术语 | 什么意思 |
|---|---|---|
| 注册记录 | entry | 某个 agent 的 skills 目录下实际存在的一条记录。同一 skill 被多个 agent 引用会重复计数，所以这个数总是大于真实副本数 |
| 真实副本 | unique entity | 把快捷方式折算掉之后，磁盘上真实存在的 skill 文件夹数量 |
| 快捷方式 | symlink | 只存了一个指向别处的路径，内容不在这个 agent 目录里。删掉不损失内容 |
| 本体在此 | 实体持有 | 文件真的在这个 agent 的目录里，是内容的正身 |
| 失效的快捷方式 | broken link | 快捷方式指向的目标已被删除或移动 |
| 内容已不一致 | divergent | 两份同名副本的正文已经不一样，合并前必须先决定留哪份 |
| 有一份坏了 | broken | 这一组里有路径已经不存在的副本。被换掉的每一份都只是断链时，工具自己重指即可，不用你选 |
| 有一份只剩快捷方式 | symlink-farm | 副本目录里全是快捷方式、没有自己的文件，它不算一份真副本 |
| 有一份疑似转发壳 | shell | 有一份正文很短、看着像转发壳，它本来就不装内容 |
| 正文各有改动 | fork | 两份都真有内容、各自改过 —— 这才是真正要你拍板的那类 |
| 都先留着 | ignored | 你标过的「这一组就是不动」。不再计入待处理，也能随时恢复提醒 |
| 版本号不一致 | version drift | 同一个上游包的两份副本版本号不同。通常整包升级即可，不必逐文件比 |
| 内容指纹 | body hash | 对正文算出的短哈希，用来判断两份是否逐字一致 |
| 同一来源包 | bundle | 这批副本来自同一个上游包 |
| 保留的那一份 | canonical | 合并时决定留下来的那一份，其余副本改为指向它的快捷方式 |
| 加载 / 拒绝加载 | 装载 / 拒载 | agent 启动时读取 skill 的过程。被拒绝加载的 skill 等于不存在 |
| 技能合集 | container | 一个目录里包含多个子技能，本身没有 SKILL.md，属于容器而非缺陷 |
| 同名异物 | coexist | 两份东西恰好重名但来源互不相干（如各 App 各自自带）。**合并不是正确动作** |
| 仅手动可用 | user-invocable-only | 模型不会自动调用它，但你可以显式点名使用 |

## 各 agent 的原生开关机制

「禁用」优先改 agent 自己的开关，不动文件。机制分技能级与插件级两种粒度，逐 agent 的落点、取值范围与验证结论见 [`references/agent-toggle-matrix.md`](references/agent-toggle-matrix.md)。

其中 WorkBuddy 的键名规则是 `frontmatter.name` 优先、缺省用目录名 —— 这条是从客户端源码确认的，不是猜的。

**一个 skill 的「总状态」取最坏值**：只要有一个 agent 把它关了，页面就标黄/标红，并把每个 agent 的状态单独列出来。

文件级禁用（MiniMax / Bitto 的回退路径）实测过有效性：在 Codex 上做了 6 组探针、用 `codex debug prompt-input` 把模型实际看到的技能清单打出来核对 —— `.` 前缀目录会被忽略 ✅、`SKILL.md.disabled` 改名会被忽略 ✅、`.disabled` 后缀目录**仍然加载** ❌。所以回退路径只支持前两种写法。

## 写操作的安全边界

三条硬约束，任何写动作都绕不过：

1. **干跑优先。** 每个写命令默认只打印差量，不落盘。页面上的按钮也是先拉一次干跑结果给你看，再让你点「确认执行」。
2. **不真删。** 卸载 = 移进 `~/.skill-panel/trash/<时间戳>-<agent>/<名称>`。`restore` 能列出来，手动 `mv` 回去即可。
3. **留痕。** 每次真实写操作记进 `~/.skill-panel/ledger.json`（时间、动作、skill、agent、逐条差量）。

`serve` 的令牌边界单独说一句：页面里内联了本次会话的一次性令牌，所以响应**只对本机回环来源**开放跨域读取（`http://127.0.0.1:<port>` / `http://localhost:<port>` / `http://[::1]:<port>` 三种写法回显，其余一律不回显 `Access-Control-Allow-Origin`），并带 `Cache-Control: no-store`。写死在 `*` 上等于把令牌交给用户浏览的任意网页 —— 对方跨域读出令牌后就能带 `apply=true` 触发禁用/卸载。放行与否只看真实监听端口，不依赖任何需要记得挂上的白名单属性。

卸载前会算**影响面**：如果一个实体被别的 agent 用快捷方式引用着，直接删会让那些引用断链，工具会拦下来并告诉你被谁引用；确认要删得加 `--force`，此时它会把连带要清理的快捷方式一并列出来。

内置技能（App 自带）不允许卸载 —— 卸了也会被升级覆盖回来，属于假动作。

## 配置写错会怎么表现

`agents.json` 与 `rules.json` 是给人改的，所以改错必须**当场报错**，不能静默兜底。

`agents.json` 里最要紧的一条：写入方式按 `writer` 分派，而 **JSON 是默认分支** —— 把 `"json_nested"` 拼成 `"json_nestd"`，不报错的话就会按 JSON 去写，改到不知哪个文件的键上。所以 `writer`、`kind`、`granularity`、`value_mode` 取值非法，agent `id` 重复，JSON 级开关缺 `container` / `file`，`toml_section` 缺 `section` / `field`，`cli` 缺 `bin` —— 全部逐条列出问题后以退出码 2 结束。

`rules.json` 同理：`level` 只能是 `fail` / `warn`，`id` 不能重复，`label` 与 `detector` 不能为空。另有一条测试保证每个 `detector` 在 `skillctl.py` 里**真有对应的实现** —— 规则表里写了、代码里没有的规则等于撒谎。

`agents.json` 的四张自说明表（`_agent_spec` / `_root_spec` / `_toggle_spec` / `_top_level_spec`）由测试守着：**用到的键必须都在表里有说明**。建新 agent 的人只会读这张表、不会读代码，所以「代码在用、表里没写」与「表里写了、代码没实现」是同一类缺陷的两面。`overrides.json` 同理 —— 样例里出现的键，代码必须真的读它，否则用户照着填、以为生效了，实际被静默忽略（`note` 就是补上这一条时接通的）。

## 退出码

| 码 | 含义 |
|---|---|
| 0 | 正常完成（`disable` / `uninstall` 的干跑也算正常完成） |
| 1 | 前提不满足：没有扫描产物、找不到这个 skill。**先跑 scan** 属于这一类，所以包装脚本不会把它读成成功 |
| 2 | 参数或配置错：子命令参数缺失、`agents.json` / `rules.json` 校验不过 |

约定是「没有真的做事就不返回 0」，这样 `&&` 链和 CI 能直接依赖退出码。测试里有一条专门钉住无快照时各命令都返回 1。数退出码时别写成 `cmd | head` —— 那拿到的是 `head` 的码。

## 同名冲突：先分诊，再处方

同名冲突先按两个维度分诊：

- **性质**：真重复（同一份东西的多个副本）vs 同名异物（恰好重名，来源互不相干）
- **存活**：两边都启用 / 一方已停用 / 全部已停用

样例机器上最近一次扫描：36 组同名冲突（真重复 16 / 同名异物 20），两组都还在生效的 21 组、有一方已停用的 15 组。16 组真重复**全部**落在「正文已分叉」这一档 —— 这一档一个都不该由脚本替你决定，所以它是决策卡片的主要服务对象（数量随装机情况变化，这里只是说明量级）。

处方按「能不能替你做决定」分三级：

| 级别 | 判定条件 | 怎么处理 |
|---|---|---|
| **脚本可自动** | 正文逐字一致（`identical`），或只有元数据级差异（`meta-only`） | 页面「一键去重」可用，也能批量；CLI 是 `resolve` |
| **半自动** | 正文一致但文件集不同（`same-body-diff-files`） | 页面可一键；批量默认带上，用批量栏的「含半自动」开关可以把它摘出去；CLI 得显式加 `--semi` |
| **需人工** | 正文已真实分叉（`divergent`） | 页面给「选正本」卡片（候选 + 推荐理由），选定后才出现「执行」；CLI 必须 `--canonical 组名=路径` 才动手 |

「需人工」不等于「都得你从头查」：先看这一组的**形态**（`shape`），三种形态根本不该让人做取舍。

| 形态 | 页面上写的 | 该怎么办 |
|---|---|---|
| `broken` | 有一份坏了 | 被替换的每一份都只是断链时（`auto_repairable`）直接重建指向即可，不用你选；页面只给一个按钮 |
| `symlink-farm` | 有一份只剩快捷方式 | 那个副本目录里全是快捷方式、没有自己的文件，它不算一份真副本 —— 是链接关系的问题，不是内容分叉 |
| `shell` | 有一份疑似转发壳 | 壳里没有真内容，所以它不进候选；留另一份即可，换掉壳不会丢东西 |
| `fork` | 正文各有改动 | 这才是要你拍板的，也是卡片真正服务的场景 |

去重做三件事：指定一份作正本、其余副本换成指向它的快捷方式、**原副本先移进回收站**（不删除，可还原）。和其它写操作同一套规矩 —— 先干跑给你看差量，点「确认执行」才落盘，台账留痕。半自动组之所以曾经只让单组点，是怕批量一口气把「该有人看一眼的文件差异」全省掉；但它和「可自动」的实际差别只在附加文件，而被换掉的副本是**整目录**移入回收站，独有文件随时能捞回来 —— 所以现在批量默认带上它，干跑预览里逐组标出级别、并给出该组自己的 `diff` 命令，按钮也会写明「含 N 组半自动」，不想带就摘掉批量栏那个勾。

两条路等价，走哪条都行：

    # 页面：起直连服务，在页面上点「一键去重」（先给干跑差量，确认后才落盘）
    python3 scripts/skillctl.py serve --open

    # CLI：默认干跑，--yes 才真执行
    python3 scripts/skillctl.py resolve --names eli5          # 预览
    python3 scripts/skillctl.py resolve --names eli5 --yes    # 执行

想额外留一份给人复核的纸质清单，再走 `plan`：它产出 `plan-<时间戳>.md`（留哪份、为什么、会影响谁）和 `plan-<时间戳>.sh`（默认 `DRY_RUN=1`，一个字节都不动）。页面里给出的可复制命令是 `cd <skill>/scripts && python3 skillctl.py …`（入口目录由 `ENTRY_DIR` 注入，有回归测试守着能真跑）；本文件与 `SKILL.md` 的命令从 skill 根写起，两者等价。

正本挑选的评分顺序：跨 agent 共享池（天然被多方引用）> 不在 App 包内（改它不会被升级覆盖）> 已被其他快捷方式引用 > 实体本体。评分并列时按路径长度兜底 —— 这个兜底是任意的，**并列时会挑到别的 agent 的副本**（例：`~/.workbuddy/skills/eli5` 与 `~/.codex/skills/eli5` 逐字一致，正本会选路径更短的那份）。不满意就自己指定：CLI 用 `resolve --names 组名 --canonical 组名=/绝对路径 --yes`，页面在卡片上点选即可（`overrides.json` 目前**没有**指定正本的字段，指定只对这一次操作生效，所以落盘后重扫会把新正本算成当前状态）。注意这个评分只在「逐字一致」的组里挑得比较硬气 —— 正文分叉的组评分不参与决策，必须由你指定。

### 正文分叉：给你的不是按钮，是一张卡片

分叉组以前只能看不能点，等于把「你去看一眼文件再自己决定怎么动」留给了人。现在页面给一张卡片：

- **能选的候选**只有**可用**的那几份。护栏挡掉五类：路径不存在（链断了）、目录里没有真实文件（空壳 / 软链农场）、来自技能商店（升级时会被整个换掉）、App 内置（升级 App 会被覆盖）、已被停用。它们不会消失，而是列在候选下方并写明「用不了」的原因，让你看得见为什么少了几份。其中「已停用」只是**不进推荐**：如果你确实想以那份为准，CLI 上明确指定仍然放行。前四类不开口子 —— 那几种指定下去就是把内容弄丢。

- **推荐**排在最前并带徽章，理由写在卡片上，取自三个因子：最近被动过、版本号（带来源）、现在谁在用（被多少快捷方式引用）。三者指向不同副本时会明说分歧，不假装有共识；候选行里的「归谁管」（类型 + 来源目录）只是背景信息，不参与排序。
- 每份候选只讲这几件事，**刻意不给 diff** —— 这一步要的是「留哪份」，不是读代码。真要逐字比，`plan` 产出的清单里有该组自己的 `diff` 命令。
- **只有选定之后**才出现「执行」，执行仍走干跑 → 差量 → 确认。落盘后原副本照例整目录进回收站。
- 断链形态如果满足「被换掉的每一份都只是断链」（`auto_repairable`），卡片只给一个修复按钮，不需要你选 —— 没有内容会被替换，只是把指错的链接重新指对。

同一条路在 CLI 上是 `--canonical`：

    python3 scripts/skillctl.py resolve --names my-skill --canonical my-skill=/abs/path/SKILL.md --yes

### 做错了就退回去：撤销上一次去重

`undo` 按台账把最近一次 `resolve` 反着做一遍：删掉原位留下的快捷方式、把回收站里的目录搬回原位。三处刻意的保守 —— 回收站里那份已经不在就不动原位（否则两头都没有）、原位不是「指向该正本的快捷方式」就不碰（可能是你后来自己改的）、缺落点就跳过并告警。断链修复那类操作只重新指链接、没搬过任何东西，撤销时会被标成「不还原」而不是硬凑一个动作。

    python3 scripts/skillctl.py undo                # 干跑
    python3 scripts/skillctl.py undo --yes          # 执行
    python3 scripts/skillctl.py undo --at 20260922  # 指定某一批

页面顶栏有「撤销上次去重」，走同一份实现。台账里每条 `undo` 都留痕，所以连着撤两次会退到上一批，而不是重复撤同一批。

### 没有正确答案的组：都先留着

有些组就是没有正解 —— 两份都还在正常用，或者你权衡之后决定先不动。以前没有出口，这些组会永远留在「待处理」里，数字一直红着，久之就没人看了。现在可以标「都先留着」：

    python3 scripts/skillctl.py dismiss --names my-skill --note "两侧都在用" --yes
    python3 scripts/skillctl.py dismiss --names my-skill --undo --yes   # 恢复提醒

标记写进 `overrides.json` 的 `by_conflict`，重扫后这一组不再计入待处理，页面挪到「已确认先留着」分区并给出「恢复提醒」。组名打错会被拒绝 —— 名字对不上就等于写进一条永远匹配不上的配置，静默失效比报错更贵。


## 降噪设计（重要）

校验结果只在你信它的时候才有价值。以下每条都是为了压假阳性：

1. **frontmatter 块标量解析** —— `description: >` 是多行描述，不是单字符 `>`。不支持它会让「description 过短」瞬间产生上百个假阳性。
2. **占位符识别** —— `/Users/.../`、`/Users/name/`、`<plugin_root>/x.py`、`${CLAUDE_PLUGIN_ROOT}` 全是文档示例，不是死路径。
3. **命令上下文闸门** —— `scripts/rotate_pdf.py` 出现在散文里（"A `scripts/rotate_pdf.py` helper would be helpful"）不算引用，只有出现在 `python3 / node / bash / ./` 这类命令上下文里才算。
4. **文档目录降级** —— 命中全部落在 `references/` `docs/` `examples/` 的，自动从 FAIL 降为 WARN。`SKILL.md` 里的死路径会让 agent 照着跑并失败；资料摘录里的不会。
5. **技能集合识别** —— 自身没有 SKILL.md 但内部有多个子技能的目录（如 `superpowers`）是容器，不是缺陷。
6. **非 skill 载体剔除** —— 只有 `plugin.json` + `mcp.json` 的 MCP 插件不是 skill，剔除并列在页面「适配表」区供审计。
7. **版本去重** —— 市场缓存里同一插件常有多个版本共存（`finance-data/1.5.0` + `1.6.0`），按 `installed_plugins.json` 只认已安装的那个版本。
8. **容器并列展开** —— 声明 `nested` 的载体（如 Bitto 的 `plugins/`）既收容器自己的 `SKILL.md`，也收内嵌 `skills/` 下的子技能，**不做二选一**。
9. **内置库只索引不扫描** —— App 随包分发的技能库（`builtin_libraries`）会被投影成用户目录里的「已安装副本」，两边都扫会凭空产生成批假冲突（AutoClaw 是 42 组）。只建名称索引，用作来源证据。
10. **成批冲突归组** —— 同一上游包被复制到不同 agent 造成的同名冲突（如 `superpowers` 的 14 个技能）归成一组，避免刷屏；组内成员单列但带 `上游 xxx` 标记。
11. **版本漂移单独标注** —— 只有「内容真的不同」才算漂移。内容逐字节一致的两份，版本号差异只是打包口径，不报漂移。
12. **断链与空壳不算「另一份正文」** —— 断掉的快捷方式、指向别处的壳文件都不是可比较的内容副本。把它们算进去会凭空造出「疑似分叉」：一份软链农场里的链接互相指，正文看起来就各不相同，实际只是链接关系错乱。这类先按形态单独归类（`broken` / `symlink-farm` / `shell`），再决定要不要交人工。

## 目录

```
skill-panel/                       # 通用代码，跟着仓库走
├── SKILL.md                       # agent 读的操作说明
├── README.md                      # 本文件
├── skill.json                     # 元数据
├── agents.json                    # agent 适配表（含各 agent 的 toggle 落点声明）
├── rules.json                     # 校验规则表
├── overrides.json                 # 人工覆盖表（校验豁免 + 冲突组「都先留着」）
├── .gitignore                     # 兜底：万一有人把 --out 指回这里
├── scripts/skillctl.py            # 引擎（扫描 / 校验 / 状态 / 安装 / 写操作 / 直连服务），纯标准库
├── assets/dashboard_template.html # 页面模板，`/*__SKILL_DATA__*/null` 是数据注入点
├── references/
│   ├── agent-toggle-matrix.md     # 跨 agent 原生开关矩阵与验证结论
│   ├── agent-adapters.md          # 各 agent 载体形态 + 接入新 agent 的五步
│   └── validation-rules.md        # 校验规则逐条说明
├── tests/test_skillctl.py         # 单元测试
└── examples/                      # 怎么扩展三张配置表（不改代码）

~/.skill-panel/                    # 本地产物，不进任何仓库（--out / $SKILL_PANEL_OUT 可改）
├── skill-panel.html               # 自包含仪表盘（只读模式双击即开）
├── data/skills.json               # 扫描数据
├── plan-<时间戳>.md / .sh          # 冲突处理方案包
├── trash/<时间戳>-<agent>/        # 卸载的东西放这儿，不真删
└── ledger.json                    # 每次真实写操作的留痕
```

仓库级测试在 `tooling/tests/skill-panel.sh`：它自建一棵 fixture 技能树（含一对逐字一致的副本、一对已分叉的副本、一条共享池软链、三类必现 FAIL），所以不依赖本机上装了哪些 agent。

测试会把 `HOME` 整个换成临时目录再跑，因此既不动你真实的 agent 配置，也不会往你真实的 `~/.skill-panel/ledger.json` 里灌测试记录。这条隔离本身也有断言兜着——漏掉就会直接报「写操作没有落到隔离的 HOME 下」，而不是静默污染。

这个仓库级脚本**不随导出走**（`tooling/` 在技能目录之外），所以独立仓库里只剩单元测试。单元测试不要求目录名等于技能名——它只在仓库的 `skills/` 布局下才强制这一点，导出后目录叫什么都行（有一条测试专门钉住这个回退）。

```bash
bash tooling/tests/skill-panel.sh                        # 端到端（CLI + 落盘终态）
bash tooling/tests/skill-panel-ui.sh                     # 真实 Chromium 走一遍页面交互
python3 -m unittest discover -s skills/skill-panel/tests # 单元测试
```

浏览器测试单独一个脚本：交互全在页面里，shell 断言只能验到写没写盘，验不到「选正本之后卡片被折回去了」「点到的是不是另一个组的按钮」「请求里到点带没带 `canonical_map`」这类事。它自建 fixture 与临时 `HOME`（同端到端脚本），跑完打印每条断言与截图位置；**没装 playwright 或没有浏览器缓存时直接跳过并说明原因，不算失败**，所以不装 Node 也能跑其余测试。

## 已知空白 / 待确认

- **产物落点可配，但不会跟着 skill 走。** 默认 `~/.skill-panel/`，`--out` / `$SKILL_PANEL_OUT` 可改。代价是：落点不同就等于换了一套快照与台账，A 机器扫的快照拿到 B 机器用之前得先确认落点一致；`check` / `state` 的报错里会写清它找的是哪个路径。
- **旧版本的产物不会自动清理。** 升级前产物写在 skill 目录下（`data/skills.json`、`skill-panel.html`、`plan-*`）。新版本读的是新落点，旧文件留在原地既不报错也没人读，只会在 `scan` 结尾提示一句。确认新落点正常后自行删除。
- **本机绝对路径规则只认 `/Users/` 与 `/home/`**（本机用户名取自 `$HOME` 的目录名）。在 Windows 上这条规则静默不生效 —— `C:\Users\…` 之类的死路径不会被报出来，其余功能不受影响。
- **Bitto 是否支持软链：未知。** Bitto 自身用软链管理运行时版本，说明技术栈软链友好；但 skill / plugin 目录下未观测到任何软链。安装指令自动回退为复制。确认后改 `agents.json` 的 `supports_symlink`。
- **AutoClaw 是否读项目级目录：未知。** 官方 `AGENTS.md` 只声明了托管目录一个，未发现项目级证据，默认按无处理。
- **`~/.qwen/skills`、`~/.iflow/skills` 各有 1 条，默认未纳入**（疑为残留）。要纳入就加进 `agents.json`。
- **项目级 skill 未纳入。** 项目级 skill 随 git 仓库走，天然跨 agent 可见，本不需要迁移。要纳入就在 `agents.json` 加根目录，但同名撞车会明显变多。
- **`description 过短` 规则实测命中很少** —— 该规则在真实数据上区分度低，主要靠块标量修复后才变得干净。
- **AutoClaw 的 `_store_meta.json` 里有 `skillId`（UUID）**，可以拿它做跨机器去重的稳定标识；当前版本还没用上，只作为来源证据展示。
- **MiniMax / Bitto 的开关机制未证实。** 翻遍两家的配置目录没找到开关字段，暂时按「无原生开关」处理、回退到文件级隐藏。若后续发现原生开关，按 Codex 那一行的格式补进 `agents.json` 的 `toggle` 段即可。
- **Claude 的插件级停用会不会连带影响 `~/.claude/skills/` 下的实体，未逐一实测。** 当前把 `~/.claude/skills/<name>` 当作一个「skills 目录插件」处理，键名规则与 WorkBuddy 一致（`frontmatter.name` 优先）。
- **⚠️ 生成的 `skill-panel.html` 会原样印出命中的凭据** —— 那是它的功能（「凭据硬编码」规则要把证据摆给人看），但也意味着**分享这个 html 等于分享凭据**。它落在产物目录里（默认 `~/.skill-panel/`）不进仓库；要外发前先确认没有 FAIL 级的凭据命中，或者直接跑 `check <skill>` 看单条。
- **`secret-literal` 的允许词表是整行生效的。** `allow_patterns` 里的 `\bsample\b`、`\bexample\b`、`\bfake\b` 等只要出现在该行任意位置，整行就不再报——变量名叫 `sample` 就足以豁免。这是为扫陌生仓库而做的放宽（别人的代码里满屏 `your_token`），代价是这类词会给真凭据让路。**不要把这份放宽词表用在自己文件的审计上**：`tests/test_skillctl.py` 里的自检走 patterns-only 路径，且样本按需拼接、不留字面量。是否收紧这条规则（改成只在取值位置豁免）待定，收紧会改变全盘扫描结果，需要重新过一遍基线。
