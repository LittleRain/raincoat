# ACG 信息抓取

DSH 应用：官方赏行业抓取的驾驶舱。这个目录同时装着面板（`client.js` / `lib/`）和三个抓取引擎（`engines/`），不再依赖 workspace 仓库里的 `workflows/kuji-tracking`。

```
apps/acg-capture/
├── index.js / client.js / lib/     # DSH 宿主入口与面板
├── scripts/                       # api-smoke.mjs / ui-smoke.mjs（离线冒烟）
└── engines/                       # 抓取引擎（原 workflows/kuji-tracking）
    ├── scripts/                   # acg_run.py / bag_run.py / vg_run.py、acg/ 公共模块、tests/
    ├── references/                # channels.json / bag-*.json / brand-sources.md ...
    ├── docs/                      # weekly-check.md 等口径文档
    └── skills/                    # 绑定这两个工作流的 Skill
```

运行时数据仍在 `~/.dsh/acg-capture`（runs / locks / cache），与代码位置无关；迁移时不需要搬历史运行记录。
侧边栏「ACG信息抓取」，顶层三个 tab：**官方赏**（抓新品 / 补齐信息 / 抓取渠道 / 流程说明）、**官方福袋**（抓取任务 / 线索 / 流程说明）、**游戏虚拟商品**（抓取任务 / 游戏汇总 / 流程说明）。三个 tab 的「流程说明」是同一套排版，只换内容 —— 各自引擎真实口径的七步、子页分工、常见疑问、词表，最后附可复制的 CLI 命令。

| 子页 | 作用 |
|---|---|
| 抓新品 | 触发 `discover`，看进度与逐条候选；默认窗口 = 上次成功日 −1 天 → 今天（可在「抓取窗口」改成最近 3 / 7 天），只看中国大陆品牌与已确认渠道 |
| 补齐信息 | 触发 `backfill`，看缺口统计、本轮批次、逐盘结论。三类缺口一并派发：缺单抽价、缺子品结构（0 条子品要建行）、缺单套数量；「本轮派发」可选全部缺口 / 20 盘 / 50 盘 |
| 抓取渠道 | 品牌 → 渠道 → 爬取方式的表；试抓、确认、撤回 |
| 流程说明 | 给第一次用的人看的「从抓取到写表」七步、两种任务的区别、常见疑问与词表（静态文案，不读数据）；官方福袋 / 游戏虚拟商品各有一份同排版的说明 |

## 页面结构

三个一级 tab 的「抓取任务」页现在是同一套骨架，换 tab 只换数据，不换位置：

```
抓取配置    标题 + 说明 → 本任务的参数（下拉） → 本轮范围提示 → 写回表格 → 开始
当前状态    台账现在什么样（盘数 / 子品 / 缺口 / 渠道），带「刷新」
运行记录    一行一条，点开看详情
详情        抓取逻辑、阶段轨、计数、逐条结论
```

2026-11-18 之前只有「游戏虚拟商品」有配置项和当前状态，另外两个 tab 只有一个开始按钮，
同一件事在三个页面长得不一样。现在这三块都由同一对组件渲染（`TaskConfig` / `StatusCard`），
`ui-smoke.mjs` 里有「三个任务页骨架一致」的断言守回退。

1. **抓取配置**：每个任务只放后端真的读的参数 —— 抓新品「抓取窗口」（自动 = 上次成功日 −1 天 → 今天）、
   补齐信息「本轮派发」（全部缺口 / 20 盘 / 50 盘）、官方福袋「线索范围」（全部启用 / P0·P1 / P0）、
   游戏虚拟商品「抓取模式 · 游戏窗口 · 取证通道」。配置项记在 localStorage，换页回来还是上次那组；
   「写回表格」不记，每次打开都是 dry-run。运行中也能改，改的是下一次。
2. **当前状态**：抓新品看「表里有多少盘」、补齐信息看「缺口还剩多少」、福袋看「线索与可用渠道」、
   虚拟商品看「游戏覆盖与三类齐全」。数据来自各自的 snapshot 接口，右上「刷新」强制重取。
3. **列表与详情**：一行一条，左边状态徽标，右边是这条运行在干什么（`抓新品 11-16 → 11-17`、`补齐信息 · 本轮补 3 个盘`），
   第二行是结果（`候选 5 · 采纳 2 · 判废 3 · 写入 2`）和元信息（触发方式、开始时间、用时、是否 dry-run），
   第三行是这一轮**在抓什么**：抓新品 `13 个品牌 / 微博 12 · 公众号 3 · 小红书 1　原文 52 条 · 3 组`，
   详情里还会补一行 `DS 搜索 6 次 · 公众号候选 8 条`（公众号渠道先走 DeepSeek 搜索再交 workbuddy），
   补齐信息 `补缺口：全部 N 个盘（子品结构 8 · 价格 7 · 数量 10）　盘A…、盘B… 等`。窗口和范围跟上一轮一样时，右边会多一个
   `↺ 同上一轮`，一眼看出这两轮其实在干同一件事。
   当前查看的那行有品牌色左边框 + 底色 + 「查看中」，键盘 Enter / 空格也能选。默认只列 5 条，可展开全部。
4. **选中运行的详情**：顶部「抓取逻辑」写清这一轮的目的、窗口、渠道构成、分组（补缺口则列全本批盘子），
   下面是阶段轨、采纳/判废/待确认/写入计数、逐条结论表；点列表任何一行会把详情带到眼前。
5. **逐条结论表**多了「写入」列：`已写入表`、`已写入（价格+数量）`、`仅候选（dry-run）`、`未写入`，
   判废/待确认/来源未公布是 `—`。老运行没有逐条标记时，发现类按「采纳数 == 写入数」反推。
   结论列的「说明 / 来源」对**待确认**和**来源未公布**先说一句人话（例如
   `各赏数量：候选里已经有值（10 个赏别），但 lite-gmc.oneone.com.tw 打不开（ConnectionResetError），机器核不了原文`），
   再谈机器原因；这两类不再让人自己猜「要我确认什么」。

6. **逐条结论按状态筛选**：详情里的逐条表上方按本轮结果现算一组胶囊 —— `全部`、`待确认`、`已采纳`、`判废`、`重复`、
   `来源未公布`（只列本轮真的出现过的状态，只有一种结论时不摆这排按钮）。点一下只看这一类，再点回 `全部`；
   筛到空会写「「待确认」下没有条目」。三个 tab（官方赏 / 官方福袋 / 游戏虚拟商品）共用同一套口径，
   选择记在 localStorage，换 tab 回来还是上次那个筛选。

改面板文案后跑一次离线冒烟（不启动宿主，用真实 run.json 验「人可读」与渲染）：

```bash
node apps/acg-capture/scripts/ui-smoke.mjs   # 面板渲染与文案
node apps/acg-capture/scripts/api-smoke.mjs  # 后端路由（含中文 item id 的裁决路径）
```

## 交互约定

- 默认 **dry-run**（不勾选「写回表格」）。勾选后才会把验收通过的条目写进企微表。
  勾选状态不持久化：每次打开面板都回到 dry-run，避免手一滑写表；只有配置项（窗口 / 派发量 / 线索范围 / 通道）记上次的值。
- 执行中每 2.5 秒刷新一次；宿主重启后，残留的 running 会标成「中断」，不会假装在跑。
- **切走再回来会回到原处**：一级 tab、各子页 tab、选中的运行、列表展开状态与滚动位置都存在
  `localStorage['acg-ui-state']`（宿主切面板会卸载组件，不存就全丢）；上次那条运行被清理时退回最新一条。
- 「抓取渠道」里只有 `已确认` 的渠道会被抓新品使用；`待对齐` 只能试抓看证据。

## 人工裁决（反馈入口）

「补齐信息」里状态为「待确认」的条目下面有一行操作：

- **来源 URL**：你人工核对过的官方/授权页（可留空）
- **备注**：采纳依据或判废原因
- **采纳并写入**：把候选值写进这条缺的那一列（价格只写人民币/日元，台币等不写），记录 `decidedBy=human`、来源、时间
- **判废**：只标记，不写表

只有「待确认」有这行操作；**来源未公布**的条目不显示按钮，因为候选里没有任何能写进表的数。

两条硬约束（2026-11-17 复盘后加的）：

- **采纳只写这条缺的字段**。以前缺数量的盘会顺手把候选价格再写一遍，条目变「已采纳」而数量仍是空 —— 假成功。
  现在一个目标字段都写不进去就直接 400 报错、状态不动，并在提示里说清缺的是哪一项。
- 每条只能裁决一次（已裁决的再提交会返回 400 和原因）。裁决不改变验收规则——同类来源打不开的盘，下一轮仍会进待确认。

结论有四种，含义不同：

| 结论 | 含义 | 要不要人管 |
|---|---|---|
| 已采纳 | 四道门全过（或人工采纳） | 不用 |
| 判废 | 数据本身有问题：二手、原文对不上、Σ 不等于抽数 | 不用 |
| 待确认 | 值找到了，但页面**机器打不开、人打得开**（限流、登录墙、只渲染出外壳） | 要 |
| 来源未公布 | 来源页没有这个数（一番赏预告页只写「全 N 種」的款式数） | 不用，下一轮自动再补 |

口径改了以后，历史运行不用重跑就能按新口径重新归类（离线：不联网、不重派、默认不写表）：

```bash
python3 apps/acg-capture/engines/scripts/acg_run.py --reclassify r-20261117-134023-backfill
```

## 官方福袋

顶层 tab「官方福袋」下两个子页，抓取由 `apps/acg-capture/engines/scripts/bag_run.py` 执行。

| 子页 | 作用 |
|---|---|
| 抓取任务 | 抓取配置（线索范围：全部启用 / P0·P1 / P0）→ 当前状态（线索 / 启用中 / 无渠道 / 可用渠道 / 待对齐渠道 / 已入库福袋）→ 派 workbuddy + 调 DeepSeek → 验收 → 写企微「官方福袋」表；看双源结果、逐条候选与人工裁决、历史 |
| 线索 | 线索表（IP / 类型 / 发行方 / 载体词 / 关节渠道 / 优先级 / 启停）可增删改；同页折叠「渠道库」维护发行方官方渠道（A/B/C/D 级）与试抓 |

口径：

- **线索一条 = 一个 IP**，是订阅不是待办：`status` 只有 active/paused；抓取只回写 `lastRunId / lastResult / lastHitAt`。
- **官方性由渠道决定**：只有 `status=confirmed` 且 `tier ∈ A/B/C` 的渠道参与抓取；A/B 级自营商城/官方社媒、C 级平台品牌官旗店（2026-11-17 起修订：C 级双源一致可直接采纳）；D 级（游戏内/线下）只能人工录入。
- **等价载体纳入**：福袋 / 神秘盒子 / 礼盒 / 惊喜袋 / 盲袋；台账用「载体 + 载体性质」区分「官方原称」与「等价载体」。
- **双源只认证据**：workbuddy 与 DeepSeek 各自出候选，合并后必须有可打开的官方 URL；原文命中 quote 才算采纳。JS 渲染页取不到正文时进「待确认」，不直接判废。
- **线索配置在仓库**：`apps/acg-capture/engines/references/bag-leads.json` / `bag-channels.json`；台账写入企微「官方福袋」子表（`tvZwq0`），不在仓库双写。

定时：每周一、五 11:00（`schedule-eb24af51`），与官方赏（周一/五 09:30 抓新品、09:40 补齐）错开。

## 游戏虚拟商品

第三个一级 tab，两个子页，抓取由 `apps/acg-capture/engines/scripts/vg_run.py` 执行。

| 子页 | 作用 |
|---|---|
| 抓取任务 | 抓取配置（模式：抓取 + 补缺 / 只发现；窗口 30/60/90 天，仅作提示词参考；取证通道）→ 当前状态（已入库游戏 / 三类齐全 / 有缺口 / 可用渠道 / 表内商品）→ 三通道取证（App Store 内购页 / workbuddy / DeepSeek）→ 验收 → 按「游戏+商品名」去重，**只补缺行**；看运行记录、本轮热门游戏与逐条结论 |
| 游戏汇总 | by 游戏展示覆盖：一行一个游戏，代币/月卡/通行证标缺口，点行展开商品明细（价格看备注）；底部折叠区是渠道库（A/B/C/D、试抓、标为已确认） |

口径：

- **不维护游戏库**：台账里的游戏名就是清单；每轮抓行业里有热度的游戏（不限新老），按「游戏 + 商品名」去重，只补表里缺的商品行，已有行不更新。
- **表只留必要字段**：企微 `游戏虚拟商品` 子表（`ty2XMk`）9 列（游戏/商品类型/商品名/购买渠道/证据链接/原文引用/状态/入库日期/备注）；**一个商品名一行**，各面额/渠道价格全写进备注（`60 档 6 元（App Store）`）。
- **三通道**：`store` 拉 App Store 中国区内购页做确定性解析（零模型）；workbuddy 一个 job 翻全部游戏的官网公告；DeepSeek 搜索反查。C 级来源模型单源进待确认，`store` 可单片采纳；**DeepSeek 的非官方来源直接判废**（只留线索，不占待确认）。
- **只写官方价**：首充双倍、赠送、限购写备注；二手/代充/账号交易域名判废。
- 定时：每周二 11:00，抓行业里有热度（发行商名单 / 预约 10 万 / 榜单 Top 50）的游戏并补缺行。

## 后端

插件不实现抓取，只负责调度与展示，全部调用
[`apps/acg-capture/engines/scripts/acg_run.py`](../../apps/acg-capture/engines/scripts/acg_run.py)：

```
POST /acg-capture/api/runs              {kind, write, batch}          # discover 可带 since（抓取窗口）
GET  /acg-capture/api/runs?kind=
GET  /acg-capture/api/runs/:id
GET  /acg-capture/api/runs/:id/events?after=
POST /acg-capture/api/runs/:id/stop
GET  /acg-capture/api/snapshot
GET  /acg-capture/api/channels
PUT  /acg-capture/api/channels/:id      {status, channel, type, url, note}
POST /acg-capture/api/channels/:id/probe

# 官方福袋
GET  /acg-capture/api/bag/snapshot
GET  /acg-capture/api/bag/leads
POST /acg-capture/api/bag/leads                {id, ip, ipType, publisher, carriers[], channelIds[], priority, status, ...}
DELETE /acg-capture/api/bag/leads/:id
PUT  /acg-capture/api/bag/leads/:id/status     {status}
GET  /acg-capture/api/bag/channels
POST /acg-capture/api/bag/channels             {id, publisher, channel, tier, url, status, ...}
DELETE /acg-capture/api/bag/channels/:id
POST /acg-capture/api/bag/channels/:id/probe
GET  /acg-capture/api/bag/runs
POST /acg-capture/api/bag/runs                 {write, leads, lanes}    # leads = 逗号分隔的线索 id（面板的「线索范围」）
GET  /acg-capture/api/bag/runs/:id
POST /acg-capture/api/bag/runs/:id/stop
POST /acg-capture/api/bag/runs/:id/items/:itemId/decide   {decision, note, source, write}
GET  /acg-capture/api/bag/ledger

# 游戏虚拟商品
GET  /acg-capture/api/vg/snapshot           # 台账派生的游戏清单 + 覆盖缺口 + 渠道
GET  /acg-capture/api/vg/summary            # 与 snapshot 同源，游戏汇总页用
GET  /acg-capture/api/vg/ledger             # 表内商品缓存（snapshot 时刷新）
GET  /acg-capture/api/vg/channels           # 渠道库
POST /acg-capture/api/vg/channels           {id, publisher, channel, tier, url, status, ...}
DELETE /acg-capture/api/vg/channels/:id
POST /acg-capture/api/vg/channels/:id/probe
GET  /acg-capture/api/vg/runs
POST /acg-capture/api/vg/runs               {write, mode: discover, windowDays, lanes}
GET  /acg-capture/api/vg/runs/:id
POST /acg-capture/api/vg/runs/:id/stop
POST /acg-capture/api/vg/runs/:id/items/:itemId/decide   {decision, note, source, write}
```

运行产物在 `~/.dsh/acg-capture/runs/<runId>/`（`run.json` + `events.jsonl`），插件只读不写；渠道表在仓库 `apps/acg-capture/engines/references/channels.json`。

> 踩坑记录（2026-11-17）：福袋的 item id 形如 `bag-20261117-原神-2026年-双11心`，带中文；
> 客户端拼进 URL 后是 percent-encoded。裁决路由最初只写了 `[A-Za-z0-9_-]+`，导致路径匹配不上、
> 返回 404「未知路由」，前端表现为「采纳并写表」报错。现在路由用 `([^/]+)` + `decodeURIComponent`，
> `api-smoke.mjs` 会守住这条。

## 排障

- `workbuddy` 提交报 `No such file or directory: ~/.workbuddy/cache/acc-product-config-v3.json`：WorkBuddy 的缓存基文件缺失，
  把 `~/.workbuddy/cache/acc-product-config-v3-*.json` 里最新一份复制成基名文件即可（2026-11-18 实测恢复）。
- App Store 429：store 通道已做游戏间 1s 间隔与 6s 退避重试；仍失败进待确认。

## 安装

本地插件用 link 方式挂在 profile 里（`dsh.profile.bundles` 加 `@local/acg-capture`），web/desktop 两个 profile 各一份。改完 `client.js` 刷新页面即可；改 `index.js` / `lib/*.js`（宿主侧路由）需要重启宿主——桌面 app 会中断会话，验证时可只重启 web 实例：`launchctl kickstart -k gui/$(id -u)/co.dsh.web`。
