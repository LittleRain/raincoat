# 会话不在本端时的「快捷操作」设计

> 状态：**已实现并实测**（L1/L2/L3，2026-11-14）· 宿主与 API 未改，只动 `client.js`
> 范围：只改 `client.js` 客户端，宿主 `index.js` 与 API 不动。

## 0. 一句话

现在从对话跳到「双端会话」只能看见这一条，但看不见落点、也只能单向跳、
真正要做的事（接管 / 在另一端打开）还得进去点第二下。补三件事：
**在对话里就能动手（L1）· 跳过去看得见（L2）· 跳了能回来、能分享（L3）**。

## 1. 现状核对（已实现，已实测）

代码里已经有：

| 能力 | 位置 |
|---|---|
| `panelFocus`（sessionId 的全局聚焦态） | `client.js:48-61` |
| `openInPanel(sessionId)` = focus + `layout.selectPanel('peer-bridge')` | `client.js:66-75` |
| 会话头徽标旁「双端会话」按钮 + 菜单项「在『双端会话』里看这一条」 | `client.js:363-400`、`client.js:437-450` |
| 面板聚焦：只渲染该行 + 横幅「只看这一条：<标题> · 显示全部」 | `client.js:583-585`、`client.js:631-670` |
| 面板行「切到本端」（release → 在本端打开） | `client.js:715-745` |

2026-11-14 13:5x 两端实测（桌面端 50529 / Web 端 3080 均在线，bundle 都含
`openInPanel`、`panelFocus`）：

- Web 端打开桌面端持有的「插件数据规范与展示问题排查」→ 点「双端会话」→ 面板出现
  「只看这一条：插件数据规范与展示问题排查」；
- 桌面端打开 Web 端持有的「知识库每日摄入策展 · 2026-11-14」→ 同样聚焦成功。

所以「点了没反应」的老毛病已经不存在。但**入口只有一个、跳过去是单向门、
快捷操作要二次点击**，所以仍然会觉得「还得进插件里找」。

## 2. 为什么还是别扭

1. **入口藏**：唯一入口在会话头右上角徽标旁，小；真正让人意识到「我在只读」的
   输入框上方横条（`MirrorDock`，`client.js:466`）反而没有入口。
2. **单向门**：面板占的是 main 槽位，跳过去当前对话就被盖掉；回来得再从列表里找
   那条会话——正好是「每次还要点到插件里去找会话」的体感来源。
3. **要二次点击**：「切到本端」「在对端打开」都只有面板行里有，对话里做不了。
4. **不可寻址**：刷新后 focus 丢失；没有 `#dsh-bridge-session=` 深链，
   不能把「你看这条」直接发给另一端的自己/别人。
5. **没有落点**：聚焦后只过滤，不高亮、不滚动（全文件没有 `scrollIntoView`），
   表窄的时候不容易确认「就是这条」。

## 3. 方案

### L1 对话内直达（最小闭环，先做）

`MirrorDock` 在 `owner.kind === 'peer'` 时渲染两个按钮：

- **主按钮「接管到本端」**：等价面板行的「切到本端」——
  `POST /dsh-bridge/api/release {sessionId, toPid: owner.peer.pid}` →
  成功 `openSessionWithFallback(sessionId)`；失败按 `describeReleaseError` 的 code
  给下一步（busy / frozen / still-held / peer-unreachable / not-held）。
  点击前一句确认：「对端会冻结这条会话，要继续用它得重启那一端」。
- **次按钮「在双端会话里看」**：`openInPanel(sessionId)`（已有）。

`owner.kind === 'frozen'` 时不显示「接管」（接不回来），只给入口 + 一句
「本端重启后才能接回」。

实现要点：把 `client.js:715-745` 内联的 release→open 逻辑抽成
`takeOver(sessionId, peerPid)`，dock 与面板行共用，避免两份错误翻译。

### L2 面板聚焦模式：跳过去要看得见

聚焦帧（`focus` 非空）时：

- 只渲染该行（已有）+ **整行高亮**（左边 3px 品牌色 + `layer2` 背景）+ 首次渲染
  `scrollIntoView({block:'center'})`（ref 在行上，focus 变化时触发一次）。
- 横幅「只看这一条：<标题>」里就地放三个按钮：
  `切到本端` · `在对端打开` · `← 回到刚才的会话`（见 L3）；`显示全部` 保留。
- `Esc` 退出聚焦（已有 Esc 关闭菜单的先例，`client.js:330-336`）。

不自动执行 release：有副作用，必须一次显式点击。

### L3 深链 + 回流（把单向门改成双向）

- **路由**：`#dsh-bridge-session=<sessionId>`。
  `openInPanel` 时 `history.replaceState` 同步 hash；`显示全部`/Esc 清掉。
  页面加载时 `consumeDeepLink()`（`client.js:1048`）多认这一个前缀：
  命中就 `selectPanel('peer-bridge')` + 聚焦，**不重载页面**
  （与现有 `#dsh-bridge-open=` 的"打开会话"语义并列，互不冲突）。
- **回流**：`openInPanel` 前把当前会话 id 写 `sessionStorage['peer-bridge:returnTo']`；
  横幅的「← 回到刚才的会话」= `openSessionWithFallback(returnTo)`，
  main 槽位换回对话，focus 清空。

### L4 可选（成本低，最后考虑）

命令面板/快捷键「双端会话：看当前会话」；若核心没有公开 commands 服务就跳过，
不为此引入 hack。

## 4. 关键流程

**A 想接管（对端持有）**
对话只读条「接管到本端」→ 确认 → release → 成功：本端打开该会话，对端标记「已让出」；
失败：toast 一句人话 + 下一步，会话不动。

**B 想确认对端在写什么**
只读条「在双端会话里看」→ 面板聚焦该行（高亮、居中）→ 行内「在对端打开」新标签
落到对端同一会话（只读）。

**C 点错了**
「← 回到刚才的会话」或 Esc。

## 5. 数据与接口

不改宿主。数据全部来自已有的 `/dsh-bridge/api/overview`：
`peers[].heldIds / runningIds`、`sessions[].held / frozen / updatedAt / title`。

新增的只有客户端本地状态：`panelFocus`（已有）、`sessionStorage.returnTo`、
hash 中的 `dsh-bridge-session`。

## 6. 边界

| 情况 | 行为 |
|---|---|
| 对端离线 | `ownerOf` 不会是 peer，入口不出现；点后才发现离线 → peer-unreachable，会话不动 |
| 已让出（frozen） | 不给「接管」，只给入口 + 「重启本端才能接回」 |
| 非对端持有 | 不显示任何入口 |
| 对端正在跑回合 | 「接管到本端」disabled，title「等这一轮跑完」 |
| `layout` 服务缺失 | 跳转失败 toast「这个界面切不到面板，用左侧『双端会话』」（已有） |
| 窄屏 | dock 按钮换行铺满（`useNarrow` 已有）；面板操作条在主表上方，不挤行内 |

## 7. 落地清单

`client.js`（约 +180 / −40 行）：

1. 抽 `takeOver(sessionId, peerPid)`，面板行与 dock 共用。
2. `MirrorDock`：peer 时加两按钮；frozen 时只加入口 + 说明。
3. `openInPanel`：写 `returnTo`、同步 hash。
4. `PeerBridgePage`：聚焦行高亮 + 一次 `scrollIntoView`；横幅加「回到刚才的会话」。
5. `consumeDeepLink`：认 `#dsh-bridge-session=`，启动时切面板并聚焦。
6. 测试：新增 focus/hash 解析的纯函数用例；现有 22 条不回归。

## 8. 验收（headless 可复现）

1. Web 端打开桌面端持有的会话 → 只读条出现「接管到本端 / 在双端会话里看」。
2. 点「在双端会话里看」→ 面板「只看这一条」+ 行高亮 + 滚动到中间。
3. 面板横幅点「← 回到刚才的会话」→ 回到原会话（输入框在、标题对）。
4. hash 变为 `#dsh-bridge-session=…`；刷新页面仍聚焦该条。
5. 对端离线时入口消失；对端跑回合时「接管到本端」置灰。
6. `node --check client.js`、`node --test test/*.test.js` 全绿。

## 9. 不做

- 不自动接管：release 有副作用，必须显式点击 + 确认。
- 不在对话里做「投递」：一端打的字不会被送到另一端执行（插件定位如此）。
- 不为快捷操作新增宿主接口。

## 10. 实现落点（2026-11-14）

都在 `client.js`：

| 变更 | 位置 |
|---|---|
| `HASH_PANEL = '#dsh-bridge-session='` | 常量区 |
| `writeReturnTo` / `readReturnTo` / `syncPanelHash` / `clearPanelFocus` | `openInPanel` 上方 |
| `openInPanel(sessionId, currentSessionId)`：focus + returnTo + hash + selectPanel | 同上 |
| `takeover(sessionId, peerPid)`：`/release` + 刷新 + 打开，失败抛 `.body` | `MirrorDock` 之前 |
| `MirrorDock`：接管到本端（二次确认、跑回合时置灰）/ 在双端会话里看 / 刷新 / 在另一端打开 | `client.js:466` 起 |
| 面板行「切到本端」复用 `takeover` | 行操作区 |
| `PeerBridgePage`：`focusRowRef` 滚动、`confirmTake` 5s 撤回、Esc 退出、Banner 操作条 | `client.js:690` 起 |
| 聚焦行高亮（窄卡片 / 宽表格两套渲染） | 行容器 `style` |
| `consumeDeepLink` 认 `HASH_PANEL`，保留 hash、40×250ms 重试 | 文件底部 |
| `openSessionWithFallback` 开头清 panelFocus | 文件底部 |

实测（headless，两端）：Web 端（pid 92368）与桌面端（pid 86982）打开对端持有的会话 → dock 三按钮；点「在双端会话里看」→ `#dsh-bridge-session=…` + 横幅 + 行高亮 + 回程；Esc 清聚焦；深链刷新后仍聚焦；`node --check` 通过；`node --test` 28/28。
