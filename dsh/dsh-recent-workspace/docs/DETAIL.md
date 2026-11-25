# 侧栏「最近」分区 · 设计方案

> 目标版本：DSH 0.2.2-rc.5 起，当前对齐 0.2.3-alpha.2（`@deepseek-ai/dsh-client-ui-workspace`）
> 适用界面：Web / 桌面共用侧栏（http://127.0.0.1:3080）
> 状态：设计稿，待拍板（见 §9）

---

## 1. 结论先行

1. **能做，但要动 ui-workspace**：侧栏「工作区」整块是**一个 single slot**（`sidebar.workspaces`），由 ui-workspace 独占，外壳没有任何 section 级扩展点。所以「最近」不是加一块 UI，而是**改渲染这块插件的分组逻辑**（或者换成另一种 UX，见 §6）。
2. **「最近活跃」已经有现成口径**：`SessionSummary.updatedAt = max(createdAt, lastPromptAt)`，`lastPromptAt` 只在**用户发消息 / steering** 时更新（`dsh-api-session-controller/src/list.ts:368-369`、`:52-57`）。这正好等于侧栏现有「最近更新」排序用的值 —— 复用它，心智一致、零新增 Host API。
3. **推荐 A2（薄 fork）+ 同步提上游**：只 fork 2 个渲染文件、其余 `import` 原包源码，新增「最近」合成分组；同一份 diff 提给上游，长期归零维护。备选 C（独立「最近」面板，零 fork、但 UX 不是分区）。
4. **三个必须先拍板的点**：① 最近分区与下方工作区分组**允许同一会话出现两次**（lens 语义）② 上限 **8 行**、超出用「查看全部」跳单列表 ③ **手动排序 / 单列表 / 搜索**三种状态下**整段隐藏**。
   → 以上 4 点已于 2026-11-22 拍板：1 允许、2 8 行够、3 置顶不提前、4 手动排序下隐藏。**新增约束：要做成独立插件，且 web 与 desktop 都要能用**——这条直接改写了方案形态，见 §11。

---

## 2. 目标与非目标

### 目标
- 侧栏「工作区」区内新增一个 `最近` 分区，置顶显示跨工作区的最近会话。
- 按「最近活跃」降序：谁最后被用户提问，谁在最上面。
- 一眼能回到刚才在干的事，不用逐个工作区展开找。

### 非目标（本期不做）
- 不做「今天 / 昨天 / 本周」时间分桶（列为后续）。
- 不做跨会话全文检索入口（已有搜索，且搜索会替换整个列表主体）。
- 不做「最近」的独立页面/标签页。
- 不改 Host 侧会话存储、不改 `updatedAt` 语义。

---

## 3. 现状与硬约束（决定方案形态）

| 事实 | 出处 | 对设计的影响 |
|---|---|---|
| 侧栏 workspace 区是 **single slot** `sidebar.workspaces`，注释写明 declaring is claiming，由 ui-workspace 注册浏览器 | `dsh-client-ui-sidebar/src/client/contract/slots.ts` | 想加「分区」只能改 ui-workspace，没有第二个可挂载点 |
| 分组/排序/搜索/行状态全部属于 ui-workspace | `ui-workspace/README.zh.md` | 同上；这些行为不归外壳管 |
| 分组方式：按工作区 / 按工作区树 / 单列表；排序：最近更新 / 手动 | 同上 | 「最近」需要与这三种状态定好互斥规则 |
| 每工作区「水位线」初始 5 行 + 「展开其余 {n} 个会话」 | `WorkspaceBrowser.tsx:55` `SESSION_WATERMARK_BASE = 5` | 「最近」用自己的水位（8）；它不参与下方分组的水位计算 |
| `updatedAt` = 最后一次用户输入时间 | `list.ts:52-57, 368-369` | 排序键确定；assistant 输出不影响排序 |
| 组头标签来源单一：`row.workspaceId === undefined` 一律显示「未分组」 | `Rows.tsx:288-289` | 合成分组必须带自己的标签，否则会显示成「未分组」 |
| 组渲染与 workspace 身份强耦合（拖拽、右键菜单、新建会话、水位） | `WorkspaceBrowser.tsx:472-660` | 合成分组要显式关掉拖拽，否则会往「recent」这个假账户写手动顺序 |
| 官方明确禁止按 DOM 猜落位：「Do not read another plugin's DOM … choose a slot that already allocates space」 | `dsh-doc/references/ui-plugin.md` | React portal 往侧栏塞块 = 违反指引，只作为反例记录 |
| patch 的 `name` 只能「断言」原插件名，不能改名 | `dsh-doc/references/composition-reference.md` | 换实现只能 `disabled` 原 row + `insert` 新 row |

---

## 4. 信息架构与布局

### 4.1 宽态（侧栏展开 ~260–300px）

```
┌─ 工作区 ──────────────  [🔍] [＋] [⋯] ─┐   ← 现有 section 头，不动
│                                        │
│  ▾ 最近                        查看全部 │   ← 新增分区头（16px 图标位 + 标签 + 折叠箭头）
│  ● 帮我把这份文档翻成英文               │
│  ● 组赏策略复盘（27 个盘）              │   ← 行 = 现有 SessionRow，32px
│  ◐ 侧栏最近分区设计                     │
│  ○ 上周那个脚本                         │
│  …（上限 8 行）                         │
│                                        │
│  ▾ Project Alpha              ＋   ⌄   │   ← 现有工作区分组，原样
│     …                                  │
│  ▾ 未分组                              │
└────────────────────────────────────────┘
```

- 「最近」出现在 **「工作区」section 头之下、第一个工作区分组之上**。
- 与下方分组之间：**8px 间距 + 1px 分隔线（`--ds-border-subtle`）**，避免侧栏被切碎又保持层级清晰。
- 行**不做**第二行、不加工作区名后缀：宽度不够会挤。工作区归属放进现有 **hover card**（hover card 本来就有 workspace label / cwd / 创建时间）。
- 状态点、置顶标记、归档样式全部复用现有行，不做新视觉。

### 4.2 窄态（rail，只剩图标）
「最近」随列表一起隐藏，不单独做图标入口。理由：rail 的语义是「我不能展开列表」，此时把最近塞进去会和 rail 的其它 36px 控件抢位置。

### 4.3 行解剖（从左到右）
1. 16px 状态位：running 转圈 / 待处理点 / 完成勾 / 空白会话占位（复用 `SessionStatusDots`）。
2. 标题：单行省略，hover 跑马灯（复用 `useTitleMarquee`）。
3. hover 时才出现的行尾操作区（复用 `sidebar.session.row.hover` 槽，置顶 / 归档按钮自动生效）。

---

## 5. 交互规格

| 交互 | 行为 |
|---|---|
| 单击行 | 打开该会话；若属于别的工作区，等价于现有跨区打开（`uiWorkspace.openSession(id)`） |
| hover | 显示现有 hover card：完整标题、所属工作区、cwd、创建时间、运行/待处理状态 |
| 右键 | 现有会话上下文菜单（重命名、复制链接、归档、分叉…），行为与分组内完全一致 |
| 拖拽 | **禁用**。既不能拖出，也不能作为落点；不写入手动排序 |
| 「查看全部」 | 切到「单列表」分组方式（flat 视图本身就是全部会话按最近更新排序），并把滚动位置带到列表顶部 |
| 折叠箭头 | 折叠/展开「最近」，状态持久化（复用现有分组展开状态存储，key 用 `recent`），默认展开 |
| 键盘 | Tab 可达；↑↓ 在分区内移动、Enter 打开；首尾不穿越到下方分组 |
| 搜索激活 | 整段不渲染（搜索自成列表，不允许两套列表并存） |

### 5.1 与三种视图状态的互斥规则

| 视图状态 | 「最近」 | 理由 |
|---|---|---|
| 分组方式 = 按工作区 | 显示 | 主场景 |
| 分组方式 = 按工作区树 | 显示 | 同上，树形只影响下方分组 |
| 分组方式 = 单列表 | 隐藏 | flat 已经就是「全部按最近排序」，重复即噪音 |
| 排序 = 最近更新 | 显示（自己按时间） | 一致 |
| 排序 = 手动排序 | 隐藏 | 手动排序下用户要的是自己排的序，顶部再插一段时间序会互相打脸 |
| 归档筛选 = 仅显示已归档 | 隐藏 | 「最近」在归档视图里没有意义 |
| 归档筛选 = 全部对话（含已归档） | 显示，已归档行沿用归档视觉 | 与筛选口径保持一致，不做特例 |
| 搜索有内容 | 隐藏 | 搜索替换列表主体 |

---

## 6. 数据口径（这块是设计的核心，最容易扯皮）

### 6.1 成员（谁进「最近」）
- 进入：全部工作区 + 未分组的会话，`origin !== 'subagent'`。
- 排除：
  - **空白会话**（`blank`）——刚建还没发过消息的会话不进来，否则顶部会出现一行「新会话」。
  - 归档会话（按上面的筛选规则）。
  - subagent 会话（现有列表本来就隐藏）。
- 上限：**8 行**（`RECENT_LIMIT = 8`），超出只显示前 8，其余走「查看全部」。

### 6.2 排序
- 键：`updatedAt` 降序；并列时按 `sessionId` 字典序稳定排序（直接复用 `tree.ts:145 orderByRecency`，不新写比较逻辑）。
- **置顶会话不做提前**：位置纯按时间。理由：置顶在下方分组里已经生效；如果「最近」里又按置顶重排，同一会话在两处位置不同，用户会怀疑列表坏了。
- 实时性：新消息到达 → `updatedAt` 变 → 行跳到第一（等于现有列表的更新机制，不需要额外订阅）。

### 6.3 去重策略（关键决策）
「最近」是**透镜（lens）**，不是搬运：同一条会话在下方所属工作区分组里**仍然存在**。

- 为什么不做「从下方分组里摘掉已出现在最近的会话」：会破坏水位线（每个组的 5 行预算按真实成员算）、拖拽账户归属、手动顺序的一致性，代价远大于收益。
- 代价：侧栏视觉上同一会话可能出现在两处。可接受，Slack / VS Code 的 Recent 都是这个语义；hover card 能解答「这条属于哪个工作区」。
- 「最近」里的行是只读视图：可打开 / 置顶 / 归档 / 重命名 / 分叉，但**不可拖拽**（拖拽只属于分组内的手动排序账户）。

---

## 7. 实现方案对比

### A. fork ui-workspace，在浏览器里合成「最近」分组

**A1 全量 fork**：整包复制（`src/` 共 ~250KB，`rows/WorkspaceBrowser.tsx` 62KB、`rows/Rows.tsx` 34KB、`tree.ts` 25KB、`locales.ts` 56KB），改完重新构建。

**A2 薄 fork（推荐）**：只保留自己的 `index.ts` + `WorkspaceBrowser.tsx` + 一个 `recent.ts`，其余（`Rows.tsx`、`tree.ts`、`stores.ts`、`navigation.ts`、`session-actions`、`locales.ts`、CSS module）**从安装包里的 `src` 直接 import**：

```ts
// 我们的 fork：packages/recent-workspace/src/client/WorkspaceBrowser.tsx
import { SessionNodeItem, ProjectRowItem } from '@deepseek-ai/dsh-client-ui-workspace/src/client/rows/Rows.tsx'
import { orderByRecency } from '@deepseek-ai/dsh-client-ui-workspace/src/client/tree.ts'
import css from '@deepseek-ai/dsh-client-ui-workspace/src/client/rows/WorkspaceBrowser.module.css'
```

真正要写的逻辑只有 ~60–80 行：一个 `deriveRecent()` + 在 `rootGroups` 之前插一段渲染 + 一个 `RECENT_LIMIT`。

**改动点（A2）**

| 文件 | 改动 | 量级 |
|---|---|---|
| `src/client/recent.ts`（新） | `deriveRecent(list, rowState, archivedFilter, limit)`：过滤 blank/subagent/归档 → `orderByRecency` → 取前 N | ~30 行 |
| `src/client/WorkspaceBrowser.tsx`（fork） | ① `const recent = useMemo(...)` ② 在 `rowKeys` 前插 `recent` 组行（`rowKey` 前缀 `recent:`，避免与下方同 id 行撞键）③ `renderGroup` 里对 `key === 'recent'` 关掉 drag / 新建会话 / 工作区菜单 ④ 水位覆盖为 8 | ~60 行 |
| `src/client/WorkspaceBrowser.module.css`（fork，可复用原类名） | 新增 `.recentGroup { margin-block: 8px 8px }` + 分隔线 | ~6 行 |
| `locales.ts`（fork 或复用原文件加键） | `group.recent`=最近/Recent、`recent.viewAll`=查看全部、`recent.aria` | ~6 行 |
| 外壳 patch | 见下 | 5 行 |

**装配（profile patch）**

```yaml
# ~/.dsh/profiles/web/cordis.patch.yml
- id: ui-workspace
  disabled: true            # 原 row 让位
- insert:
    - id: ui-workspace-recent
      name: '@local/dsh-client-ui-workspace-recent'
```

> 注意：`name` 只能断言不能改名（见 §3），所以必须 disabled + insert，不能只改 name。插入位置与原 row 同组最稳，实测后确认 host 侧服务（workspace controller 注入）无重复提供。

**成本**：半天～1 天，其中**最大不确定项是客户端构建链**——原包的 `lib/client.js` 是 `window.__ModuleLoader__.load({id, factory})` 形式的打包产物，且含 CSS Modules，本机没有 esbuild/vite，需要现搭一套（esbuild + 一个 css-modules 插件把 `.module.css` 编译成类名映射并在 factory 初始化时注入 `<style>`）。**先做这一步的 30 分钟可行性验证，再写 UI 代码**，否则容易卡在构建上。

**维护**：每次 DSH 升级（rc 迭代）rebase 一次，A2 的 diff 只有 ~80 行、集中在 1 个文件，可控。

### B. React portal 往侧栏 DOM 塞一块（不推荐）
- 违反 `ui-plugin.md` 的明确指引（不许按别的插件的 DOM/CSS 猜落位）。
- 侧栏一改（rc 迭代很快）就断，且和 ui-workspace 的滚动容器、`overflow`、虚拟水位互相打架。
- 只记在这里作为反例，不实施。

### C. 独立「最近」面板（零 fork 的替代 UX）
在 `sidebar.panellist`（list 槽，侧栏导航列表）加一个「最近」入口，点开在主区渲染一个「最近会话」面板（按今天/昨天更早分组）。
- 优点：完全不碰 ui-workspace，纯客户端插件，手写 `window.__ModuleLoader__.load` 即可（本机 `@local/jxs-dashboard/client.js` 就是这个形态，**无需构建链**）；升级零 rebase。
- 缺点：**不是「工作区里的分区」**，是一次跳转；离开侧栏上下文后，看会话要先点一下。
- 成本：2–4 小时（面板布局 + 列表 + 打开会话）。

### D. 提给上游，做成 ui-workspace 的一等分组
把「最近」做成 `groupBy` 的第四种模式，或一个常驻置顶分区。上游 diff 很小（就是 A2 那 80 行），但排期不由我们控制。**建议与 A2 并行**：先本地 fork 用起来，同时把 diff 提上去，上游合了就把 fork 删掉。

### 推荐
**A2 落地 + D 同步提案**；如果 30 分钟构建验证失败或不想承担 rebase，退化到 **C**。

---

## 8. 交付物与验证

### 8.1 验证手段（按 ~/.dsh/AGENTS.md：只用无头浏览器）
1. `launchctl kickstart -k gui/$(id -u)/co.dsh.web` 重载 web 实例（不碰桌面 app）。
2. Playwright headless 打开 `http://127.0.0.1:3080`，取侧栏 DOM 文本断言行序（最近 8 行 id 顺序 = `updatedAt` 降序）。
3. 造数据：在会话 A 发一条消息 → 刷新 → 断言 A 跳到第一行。
4. 折叠 → 刷新 → 断言仍折叠。
5. 切「单列表」/「手动排序」/ 搜索 → 断言「最近」不渲染。
6. 归档一条在列表里的会话 → 断言按筛选消失/变归档样式。
7. 窄态（rail）截图断言不崩、不重叠。

### 8.2 验收清单
- [ ] 侧栏出现「最近」，默认展开，最多 8 行，按最近活跃降序。
- [ ] 新发消息后该会话置顶，无需刷新。
- [ ] 点击行打开正确会话；跨工作区会话也能直接打开。
- [ ] 拖拽「最近」行无任何效果，且不产生手动顺序写入。
- [ ] 折叠状态跨刷新保持。
- [ ] 搜索 / 单列表 / 手动排序 / 仅归档 四种状态下不渲染。
- [ ] 空白会话、subagent 会话不出现。
- [ ] 无 layout shift、无滚动跳动、无重复 React key 警告。
- [ ] 键盘 ↑↓ 只在分区内移动，首尾不穿越。
- [ ] 侧栏 rail 折叠态正常。

---

## 9. 待拍板（不确认就开工会有返工风险）

1. **允许同一会话在「最近」和下方分组里各出现一次吗？**（推荐：允许，lens 语义）
2. **上限 8 行够吗？**（可选 5 / 8 / 12；8 = 一屏可扫、不挤压下方分组）
3. **置顶会话在「最近」里要不要提前？**（推荐：不提前，纯时间）
4. **手动排序下隐藏「最近」**能接受吗？（推荐：隐藏）
5. **落地形态**：A2 薄 fork（真分区，需搭构建链 + 升级 rebase）/ C 独立面板（零 fork，非分区）。

---

## 10. 后续可迭代（不在 MVP）
- 时间分桶：今天 / 昨天 / 本周 / 更早。
- 「最近」行右侧显示所属工作区名（宽屏 ≥320px 时）。
- 让 Host 在 `SessionSummary` 上补一个 `lastActivityAt`（含 assistant 输出与工具活动），支持「真的在活跃」而不是「最近提问」。
- 智能去重：若某工作区分组恰好展开且已包含该会话，则在「最近」里淡出该行。

---

## 11. 最终形态：可分发插件 + 侧栏内联分区（2026-11-22 定稿）

### 11.1 两个要求怎么同时满足

你要的是**侧栏工作区里的真分区**；「做独立的插件」按你的澄清是**能在别的设备安装**。这两件事不冲突，冲突的只是「独立插件」的另一种读法（不碰官方包）。结论：

> 把「替代 ui-workspace」这件事本身打包成一个 **bundle 插件**。装到别的设备 = 装这个 bundle，**不需要改那台设备的任何官方代码**，也不需要它装 node 或构建工具。

代价是接受一个上游耦合点（拼接官方 client bundle 的 4 处锚点），换掉它就得放弃内联形态。收益是：别人的设备只要「装插件 → 重启」，行为和你这边完全一致。

### 11.2 包与仓库布局

```
plugins/dsh-recent-workspace/
  package.json            # dsh.bundle.patch + dsh.client{platform:web}
  cordis.patch.yml        # disabled: ui-workspace 行 + 插入自己
  src/recent.js           # deriveRecent / withRecent 纯函数（可单测）
  scripts/build.mjs       # 读本机安装的 ui-workspace/lib/client.js，按锚点拼接，产出 lib/client.js
  scripts/compat.mjs      # 只校验 4 个锚点是否存在（DSH 升级后先跑）
  lib/client.js           # 构建产物，**提交进仓库**（安装方零构建）
  index.js                # 宿主半边空壳（对齐上游：apply(){}）
  locale/*.json  icon.svg  docs/DETAIL.md
```

### 11.3 构建方式：锚点拼接，而不是重新编译（关键决策）

实测上游 `@deepseek-ai/dsh-client-ui-workspace/lib/client.js`（197659B）**未压缩、可读**，且只有 5 个外部依赖：

```
require("react") / require("react/jsx-runtime") / require("@deepseek-ai/cordis")
require("@deepseek-ai/dsh-client-store") / require("@deepseek-ai/dsh-client-ui-primitives")
```

CSS Module 已被编译成 JS 对象（`lib/` 下**没有** .css 文件）。所以：

- 不需要 TSX 构建链、不需要 CSS 插件、不需要重写 197KB 组件；
- `build.mjs` 只做 4 处字符串拼接，每处带**锚点断言**，找不到就 fail 并打印锚点名；
- 目标设备只拿产物，不跑 node。

对比另一条路（vendor 上游 `src/` 再用 esbuild 重编译）：多 25 万字节源码 + CSS Module 管线，唯一好处是「不怕格式化变化」，而锚点断言本来就能在构建期捕获这种变化。故选拼接。

### 11.4 要动的 4 处（附上游 TSX 行号，便于提 PR）

| # | 位置（TSX） | 现状 | 改法 | 拼接锚点（bundle 内可 grep） |
|---|---|---|---|---|
| S1 | `WorkspaceBrowser.tsx:373-377` | `const groups=useMemo(()=>deriveGroups(list,workspaces,rowState,statuses,{expandedGroups,ungroupedOrder:ungroupedSessionIds}),[...])` | 拆成 `baseGroups` + `withRecent(baseGroups,…)` 插入合成组 | `deriveGroups(list,workspaces,rowState,statuses,{expandedGroups` |
| S2 | `Rows.tsx:288-289` | `row.workspaceId===void 0?t('group.ungrouped'):row.label` | **不用改**：合成组用非 `undefined` 的 `workspaceId:'__recent__'` + 自带 `label:'最近'` | `row.workspaceId===void 0?t(` |
| S3 | 水位线（`SESSION_WATERMARK_BASE=5`, `WorkspaceBrowser.tsx:55`） | 每组默认露 5 行 | 给 `__recent__` 的 baseline 用 8 | `??SESSION_WATERMARK_BASE` |
| S4 | 默认展开集合（`:386` 附近） | `[...workspaces.map(w=>w.workspaceId),``]` | 把 `__recent__` 加进默认展开 | `workspaces.map(workspace=>workspace.workspaceId),\`\`` |

三态隐藏（手动排序 / 单列表 / 搜索中）与「最近」不置顶、8 行截断、去重，**全部放在 `withRecent` 内部**（return baseGroups 即可），不改上游。预计总 diff 90–140 行，其中 60–90 行是我们的新逻辑。

### 11.5 安装与分发（"别的设备也能安装"）

1. **本机**：`plugin_manager install_bundle`，`target` 传**包目录的绝对路径**——它自己写 profile 的 `package.json` 和 patch，不要手写（dsh-doc 明令）。也可在 GUI **Plugins > Add plugin** 选目录。
2. **别的设备**，按推荐顺序：
   - a. **拷目录 / git clone → Plugins > Add plugin**（最省事，无需 node_modules、无需构建）；
   - b. `npm pack` 出 tarball → `install_bundle` 传 tarball 路径（适合内网分发）；
   - c. 发布 npm（公开或私有 scope）→ `install_bundle` 传 `dsh-recent-workspace@1.0.0`（适合多设备长期更新，但要占名字）。
3. **桌面端**：同一套逻辑，装进 `~/.dsh/profiles/desktop` 一次即可；web 与 desktop 共用同一个 web 客户端，`platform:'web'` 两边都覆盖。
4. **版本对齐**：产物里记录拼接时的上游版本（当前 `0.2.2-rc.5`）。DSH 升级后先跑 `scripts/compat.mjs`；锚点缺失 → 必须重新 build + 发版。`package.json` 声明 `engines.dsh` 范围。

### 11.6 风险与回退

- **上游大改**（SessionTree 重组、锚点消失）：compat 脚本在升级当天报错，不会静默坏在目标设备上；重做 = 改 4 处拼接。
- **装完侧栏空白** = 我方 fork 注册失败；回退 = 卸掉 bundle（或 patch 改 `disabled: false` 恢复官方行），10 秒。
- **官方将来自己做「最近」**：把本节 §11.4 的 diff 提上游，合了就删掉我们这个包（§7-D）。

---

## 12. 开工清单（确认后按此执行）

1. 建包骨架 + `build.mjs`/`compat.mjs`，先让 0.2.2-rc.5 上能产出一个可加载的 `lib/client.js`。
2. `src/recent.js` 纯函数 + 无浏览器单测：活跃时间口径、8 行截断、三态隐藏、与工作区分组允许重复、置顶不提前。
3. `install_bundle` → 新会话里验证；用无头浏览器取 DOM/截图作为证据。
4. 细节：空态、折叠交互、`查看全部`（跳到单列表）、hover 操作与工作区行的互斥。
5. 写 `docs/DETAIL.md`，并给出目标设备的安装命令。
6. 可选并行：把 §11.4 的 4 处 diff 整理成上游 PR。

**两件小事待你点头**：① 包名用 `dsh-recent-workspace` 还是别的；② 分发先走「拷目录」还是一步到位发 npm。

---

## 13. 落地结果（2026-11-22 已上线 web 实例）

### 13.1 实际交付

- 代码仓库：`/Users/raincai/Documents/GitHub/raincoat/dsh/dsh-recent-workspace`（`link:` 装进 profile，非拷贝）。
- 已注册 profile：`web`（即时生效，已实测）、`desktop`（下次启动桌面 app 生效，未实测——AGENTS.md 禁止为验证重启桌面实例）。
- 与本文件 §11/§12 的偏差，以本节为准：
  - `scripts/compat.mjs` 没有单独存在，合并成 `node scripts/build.mjs --check`（只校验锚点、不写文件）。
  - `src/recent.js` 变成 `src/recent.prelude.js`：不加导入、不导出，直接注入 bundle 模块作用域，以便复用上游的 `mainSessionId / sessionVisible / sessionNode`，不必重新实现过滤与运行态判断。
  - 没有单独的无浏览器单测；改用无头浏览器对真实 DOM 验收（见 13.3）。理由：逻辑依赖上游运行时快照形状，纯函数单测只能测到拼装层。
  - `package.json` 没写 `engines.dsh`（该字段在 DSH 0.2.2 没有读取方，写了是假承诺）；上游版本记录在 `lib/build-meta.json`。
  - 分发先走「拷目录 + `scripts/install-profile.mjs`」，没发 npm。

### 13.2 构建与锚点

- 上游 `@deepseek-ai/dsh-client-ui-workspace@0.2.2-rc.5` 的 `lib/client.js` 205018B，未压缩、只 5 个外部 require，`lib/` 下无 `.css`（CSS Module 已编译成对象）——所以不需要 TSX 工具链，`scripts/build.mjs` 直接读本机安装包里的这份 bundle 做字符串拼接。
- **16 处 splice，8 个锚点**：prelude、SessionTree props、groups 派生、水位线、折叠、行标题、SessionTree 调用参数、locale 字典（zh/en/ja/es/fr/de/ru/pt 各补一条 `recent.section`）。
- 产物 207482B，锚点全部命中；任一锚点匹配数 ≠ 1 直接抛错、不落盘。
- 注意：bash 里的 `grep`/`node` 读不到 `app.asar` 内的文件内容（`fs` 能），`build.mjs` 里用 `readThroughAsar()` 兜底；校验存在性不能靠 `fs.existsSync`（asar 内恒为 false），要改成「尝试读取 package.json」。

### 13.3 验收记录（无头浏览器，`http://127.0.0.1:3080`）

| 检查项 | 结果 |
| --- | --- |
| 「最近」出现在工作区列表最顶部 | ✅ 侧栏 22 个 treeitem，第 1 项 = `Recent`（UI 语言英文，locale 补丁生效） |
| 8 行上限 | ✅ 恰好 8 行，无「展开其余」溢出（水位线对该分区设成 8） |
| 按活跃降序 | ✅ 50min → 3h/3h/3h → 5h/5h → 6h/6h |
| 置顶不提前 | ✅ 置顶会话未插队 |
| 与工作区分组允许重复 | ✅ 同一会话在「最近」和所属工作区各一次 |
| 折叠 | ✅ 点标题 22 → 14 项，再点恢复；状态写进 `dsh.workspace.view.v5` 的 `groupExpansion.__recent__` |
| 手动排序隐藏 | ✅ 切「Order by: Manual」后整段消失（13 项，首项 Default workspace） |
| 单列表隐藏 | ✅ 「In one list」293 项，无 Recent |
| 按工作区树隐藏 | ✅ 「Workspace Tree」14 项，无 Recent（原设计想两边都显示，落地时按「分区属于工作区视图」收口，见 13.4） |
| 搜索态隐藏 | ✅ 搜索结果走独立 tree，无 Recent |
| 归档三态 | ✅ 「Archived only」时「最近」展示的就是已归档会话；「Hide archived」恢复 |
| 行能力复用 | ✅ hover 出现 `Archive session` / `Pin session` / `Session actions`，与工作区行一致 |
| 控制台错误 | ✅ 无 |

### 13.4 落地时改掉的设计细节

- **树模式不显示**：原 §5.1 设想「按工作区」和「按工作区树」都显示。实际上树模式下会话按工作区嵌套渲染，顶部插一个无归属分区会出现「分区里有行、下面树里又有一份」的层级歧义，且 `nestWorkspaces` 路径会忽略无 `workspaceId` 的分区。收口为：**只在「按工作区」分组 + 「最近更新」排序 + 非搜索态显示**。三种隐藏态（树 / 单列表 / 手动排序）在 README 里明写，避免被当成 bug。
- **8 行是硬上限**：不参与「水位线 5 + 展开其余」，超出直接不显示，避免「最近」变成第二个全量列表。
- **折叠状态持久化**：借用了上游 `groupExpansion` 存储，`__recent__` 作为一个伪 workspaceId 记账，不需要新增存储键。
- **卡片/空态**：会话总数不足 8 或全部归档时，分区整体不渲染（不出现空标题）。

### 13.5 升级 DSH 之后的标准动作

```bash
node scripts/build.mjs --check   # 锚点全中 → 直接 build；报错 → 按报错里的 find: 串去新 bundle 里定位
node scripts/build.mjs
```

`--check` 失败是预期内的正常信号，不是插件坏了：它保证升级当天就能发现「该修锚点了」，而不是让目标设备上静默降级成官方侧栏。
