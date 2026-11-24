# 官方福袋：tab 设计与实施方案

> 状态：**已落地 P0 + P1**（2026-11-17）。两个子 tab（抓取任务 / 线索）、渠道并入线索、结果写企微「官方福袋」表、双源抓取（workbuddy + DeepSeek）、每周一/五定时。
> 遗留 P2：数仓/报告导出、治理侧接入、线索健康提醒的定时化。
> 本文是口径与结构的唯一说明，代码从属实现。

## 0. 决策记录

| # | 决策 | 结论 |
|---|---|---|
| 1 | 台账落地 | 抓取结果写入企微「官方福袋」表（`tab=tvZwq0`），业务可见可审；仓库只存**线索与渠道配置**，台账不双写。 |
| 2 | 判定范围 | 纳入官方等价载体：福袋 / 神秘盒子 / 礼盒 / 惊喜袋 / 盲袋 等。 |
| 3 | 盘面 | **不进入本工作流**。305 行报告只作线索发现来源，不是运行时输入。 |
| 4 | 线索 | 一个 IP 一条；16 条种子（含 P2）。线索与渠道在插件里可查看、可编辑。 |
| 5 | 官方口径 | 天猫/京东品牌官旗店算官方，但只到 C 级（需店铺主体是品牌方），不自动采信。 |
| 6 | 默认范围 | 点「开始抓取」默认跑**全部 active 线索**。 |
| 6.1 | 渠道等级 | **C 级（平台品牌官旗店）双源一致可直接采信**（2026-11-17 修订，不再强制 pending）。 |
| 6.2 | 表列 | 13 列：保留原方案 1–9、12–15（不含发售窗口 / 官方渠道 / 采集方式 / 来源线索 / 最后核验）。 |
| 7 | 抓取方式 | 双源：派 workbuddy + 调 DeepSeek API；引擎负责派发、汇总、验收、写表。 |
| 8 | 定时 | 每周一、五自动执行（11:00，与官方赏 09:30/09:40 错开）。 |

## 1. 第一性原理：这个 tab 维护的是「抓什么」和「抓到了什么」

### 1.1 事实链

1. 官方福袋是**节点性、分散、名称不稳定**的商品：双11 / 周年 / 春节才发；散在米游铺、米游社、天猫官旗、战网商城、lolriotmall…；官方叫「心动福袋」，商家叫「双11惊喜福袋」，LOL 官方叫「神秘盒子」。
2. 所以它不是一次检索能完成的事，而是**对一批目标持续订阅**。目标 = IP × 载体 × 官方渠道 = **线索**。
3. 报告证明了线索确实存在且量很大（305 盘 / 69 店 / 约 14 个 IP 组），但它只是线索的发现来源，跑起来以后不再参与。

### 1.2 三个对象

| 对象 | 回答什么 | 谁维护 | 存在哪 |
|---|---|---|---|
| **线索 Lead** | 要盯哪个 IP、用什么载体词、去哪个官方渠道、多急 | 人在插件里增删改；抓取只回写结果 | `references/bag-leads.json` |
| **渠道 Channel** | 某发行方的某渠道能不能抓、能回答什么、可信到哪级 | 人在插件「线索」子页的渠道库里试抓/确认/撤回 | `references/bag-channels.json` |
| **官方福袋 Bag** | 官方到底发过什么：官方名、档位价、件数、窗口、渠道、证据 | 抓取任务写入 + 人工补录/裁决 | 企微「官方福袋」表（`tvZwq0`） |

### 1.3 为什么线索是「订阅」而不是「待办」

福袋每年节点都会再发，线索抓完不能关。所以线索只有 `active / paused` 两种人工状态；抓取结果写在 `lastResult`（`captured / empty / blocked / error`），**不自动改状态**。「本轮没抓到」是信息：可能官方没发，也可能渠道失效，后者要人来换渠道。

### 1.4 五条约束

1. **官方性由渠道决定，不由商品名决定。** 只有 A（自营商城/官网/小程序）、B（官方社媒）、C（平台品牌官旗，主体须核验）级渠道发布的事实才进表；D（游戏内/线下/需登录）只能人工录入。
2. **台账单位是 SKU × 档位 × 窗口。** 星铁 89/189/289 三档；只记 SKU 名会漏掉「199 档」这种虚构档位。
3. **载体词要能表达等价物。** 线索里维护 `carriers`，台账里用 `载体` + `载体性质` 区分「官方就叫福袋」和「官方叫神秘盒子」。
4. **双源必须独立取证、统一验收。** workbuddy 和 DeepSeek 各自出候选，合并后**同一条证据链只认一次**：必须有可打开的官方 URL + 原文命中，不以「两个模型都这么说」当证据。
5. **空结果要留痕。** 每条线索 × 每轮都要写结论：抓到什么、没抓到、哪个渠道打不开，否则下轮又从头试错。

### 1.5 语义边界

台账只记「官方发售事实」：不证明商家有授权，也不等于商家伪造。授权与处置不由本 tab 下结论。

## 2. 与「官方赏」的差异

| 维度 | 官方赏（现有） | 官方福袋（新增） |
|---|---|---|
| 驱动 | 品牌 → 新盘（一次性发现） | **线索 → 持续订阅**（IP × 载体 × 渠道，可启停） |
| 真源 | 企微智能表格 | 企微「官方福袋」表（同一文档的另一子表） |
| 主键 | 盘名 | IP + 官方 SKU + 档位 |
| 抓取源 | workbuddy 单源 | **workbuddy + DeepSeek 双源**，引擎汇总 |
| 验收 | 来源可打开 + quote 命中 + Σ(各赏)=抽数 | 渠道等级 + quote 命中（含载体词与价格）+ 档位集合一致 |
| 人工入口 | 待确认裁决 | 待确认裁决 + **线索/渠道编辑** |
| 节奏 | 周一/周五 09:30 抓新品、09:40 补齐 | 每周一/五 11:00 |

复用而不重写：`Run`（run.json + events.jsonl）、`dispatch.submit_workbuddy` / `wait_job`、`dispatch.ds_search`、`parse_candidates`、`fetch_text` / `page_contains`、`is_secondhand`、`norm`、`decide` 人工裁决、插件 Rail / 历史 / 渠道试抓。

## 3. 数据模型

### 3.1 线索（`references/bag-leads.json`）

```jsonc
{
  "id": "lead-genshin",
  "ip": "原神",
  "ipType": "game",                 // game / toy / anime / other
  "publisher": "米哈游",
  "carriers": ["福袋", "心动福袋", "礼盒", "神秘盒子"],
  "keywords": ["双11", "周年", "创世结晶"],
  "channelIds": ["mihoyo-mihuyoupin", "mihoyo-miyoushe", "mihoyo-tmall"],
  "scope": "cn",
  "priority": "P0",                 // P0 / P1 / P2
  "status": "active",               // active / paused
  "windowHint": "双11、周年庆",
  "lastRunId": "r-20261120-095000-bag-discover",
  "lastResult": "captured",         // captured / empty / blocked / error
  "lastHitAt": "2026-11-20",
  "source": "report-20261026",
  "note": "",
  "createdAt": "...", "updatedAt": "..."
}
```

- `id` 稳定可读，改名不改 id；`carriers` 至少 1 个；`channelIds` 必须存在于渠道表（渠道 `dead` 时 UI 标「渠道失效」，保留线索）。
- 只有抓取任务写 `lastRunId / lastResult / lastHitAt`；`status / priority / carriers / channelIds` 只由人改。

### 3.2 渠道（`references/bag-channels.json`）

沿用现有 `channels.json` 形状，加 `publisher / ipScope / tier`：

| tier | 含义 | 能否自动采信 |
|---|---|---|
| A | 品牌自营商城 / 官网商品页 / 官方小程序 | 可以（原文命中即可） |
| B | 官方社媒公告（微博 / 公众号 / 小红书） | 可以，正文须含名称 + 价格 |
| C | 平台品牌官旗店（天猫/京东），主体须为品牌方 | 只能 pending_review |
| D | 游戏内 / 线下 / 需登录 | 不可自动，只能人工录入 |

`canAnswer ∈ [name, price, tier, items, window, limit, channel]`；`status ∈ confirmed / pending / dead`。只有 `confirmed` 且 `tier ≤ C` 参与抓取。

### 3.3 台账 → 企微「官方福袋」表（`tvZwq0`，view `vH3JMF`）

现有表是空白模板（5 个默认字段、5 个空行，2026-11-17 建）。**P0 先把列建好**（`wecom-cli smartsheet fields update/add`），列设计：

| # | 字段 | 类型 | 说明 |
|---|---|---|---|
| 1 | 官方福袋ID | text | `bag-<yyyymmdd>-<ip>-<name>`，判重键之一 |
| 2 | IP | text | 如「崩坏：星穹铁道」 |
| 3 | IP类型 | single_select | 游戏 / 潮玩 / 动漫 / 其他 |
| 4 | 发行方 | text | 米哈游 / 暴雪 / 腾讯… |
| 5 | 官方商品名 | text | 官方全名（含年份/活动） |
| 6 | 载体 | single_select | 福袋 / 神秘盒子 / 礼盒 / 惊喜袋 / 盲袋 / 其他 |
| 7 | 载体性质 | single_select | 官方原称 / 等价载体 |
| 8 | 档位与价格 | text | 「89 元/随机7件；189 元/随机11件」 |
| 9 | 最低官方价 | number | 元，便于排序 |
| 10 | 证据链接 | text | 可打开的官方页面 URL |
| 11 | 原文引用 | text | 含载体词与价格的原文片段（验收依据） |
| 12 | 状态 | single_select | 官方在售 / 已结束 / 存疑 |
| 13 | 置信度 | number | 0–1，A/B=0.95，C=0.85，人工=1 |

写入约定：

- 一行 = 一个官方 SKU；多档合并进「档位与价格」，`最低官方价` 取最小值。
- 判重：`官方福袋ID` 优先；历史行没有 ID 时按 `norm(IP) + norm(官方商品名)` 兜底。
- 表里现有 5 个空行：前 5 条写入复用这些 `record_id`，之后 `add` 新行，不留空行。
- 已结束的窗口不删行，`状态` 改 `已结束`（明年同 IP 换名/换档要靠它对比）。

### 3.4 运行记录

`~/.dsh/acg-capture/runs/r-<ts>-bag-discover/`：`run.json`（状态、计数、逐条结论、**线索快照 + 双源状态**）、`events.jsonl`、`candidates.json`（两源原文）、`jobs/`。run 里必须能回答「这轮每条线索为什么没抓到」。

## 4. 流程

### 4.1 线索怎么来

| 来源 | 说明 |
|---|---|
| 报告种子 | 从 305 行报告聚合出 16 条线索（§4.2），`source=report-20261026` |
| 人工新增 | 插件「线索」里新建 |
| 渠道反推 | 某 publisher 在渠道表里但无线索 → UI 提示建线索 |
| 抓取发现 | 抓到的官方福袋 IP 不在任何线索里（联名/新 IP）→ 进「待建线索」提示，不自动建 |

### 4.2 种子线索（16 条，全部落盘）

| IP | 类型 | 发行方 | 优先级 | 依据 |
|---|---|---|---|---|
| 原神 | 游戏 | 米哈游 | P0 | 75 盘 / 44 店 / GMV 9.8 万；65 官方确认、10 查无 |
| 崩坏：星穹铁道 | 游戏 | 米哈游 | P0 | 69 盘 / GMV 6.4 万；89/189/289 三档 |
| 崩坏3 | 游戏 | 米哈游 | P0 | 53 盘；489 元档 |
| 未定事件簿 | 游戏 | 米哈游 | P0 | 12 盘；59/99 两档 |
| 英雄联盟 | 游戏 | 腾讯 / 拳头 | P1 | 15 盘；官方叫「神秘盒子」→ 等价载体 |
| 守望先锋 | 游戏 | 暴雪 | P1 | 9 盘；官方渠道在、商品查无 → 盯「有没有发」 |
| 第五人格 | 游戏 | 网易 | P1 | 9 盘；官方同期无福袋 → 同理 |
| 初音未来 | 动漫 | 版权方 | P2 | 4 盘未核实 |
| 吉伊卡哇 | 潮玩 | 版权方 | P2 | 5 盘未核实 |
| 万代高达 | 潮玩 | 万代南梦宫 | P2 | 4 盘未核实 |
| 假面骑士 | 动漫 | 东映 | P2 | 5 盘未核实 |
| 魔兽世界 | 游戏 | 暴雪 | P2 | 4 盘未核实；战网渠道可复用 |
| 炉石传说 | 游戏 | 暴雪 | P2 | 1 盘未核实 |
| 恋与制作人 | 游戏 | 叠纸 | P2 | 2 盘未核实 |
| 鸣潮 | 游戏 | 库洛 | P2 | 2 盘未核实 |
| 洛克王国 | 游戏 | 腾讯 | P2 | 通行证/货币非福袋 → 建线索但标「注意非福袋」 |

### 4.3 抓取任务（`bag_run.py --kind discover`）

```
1. 取范围：默认全部 active 线索（可按 P0/P1/P2 或勾选缩小）
2. 派两套 workbuddy 任务（2026-11-18 起，替代原来的「没渠道就跳过」）：
   sweep   全量扫街：不按发行方分组，按线索顺序每 5 条一块（68 条 → 14 个 job），全网搜「IP + 载体词 + 窗口」，输出只要商品名称/内容/IP
   channel 定向渠道：只有绑了 available 渠道的线索，单独派一组只翻 confirmed 渠道，沿用 6 组 / ≤3 条
   全部 job 一把起跑（ACG_MAX_WB_JOBS=40 ≈ 不封顶）；整轮硬预算 ACG_RUN_BUDGET_SECONDS=1500 + 预留 300s 验收，到点取消未完成 job；单 job 等待 = 600s + 180s×条数（封顶 3600s，被剩余预算再压一刀）
3. 三路并发收集：
   Lane W  workbuddy（sweep）：prompt 带 IP、载体词、关键词、窗口，渠道只作优先入口提示
           要求输出 JSON：[{ip, officialName, carrier, tiers[{price,items,quote,source}], window, channels, limit, aliases, mode:"sweep"}]
   Lane W  workbuddy（channel）：prompt 明确「只认这些来源」，渠道带名称+URL+能回答什么，mode:"channel"
   Lane D  DeepSeek：与 workbuddy 同时起跑；每个 lead 一组查询（IP + 载体词 + 年份/节点 + 渠道名），
           走 ds_search.py research（多查询展开）+ --need-content；命中页再 fetch 取正文，候选记 mode:"sweep"
4. 汇总：三份候选合并，键 = norm(IP)+norm(官方商品名)+年份；同键合并档位并记 `lanes` 与 `modes`
   （modes = [sweep] / [channel] / [sweep, channel]，界面上能看出这条是扫街找到的还是定向渠道找到的）
5. 验收（硬规则，两源一视同仁）：
   - source 命中该 publisher 的 confirmed 渠道域名，否则 channel_unverified
   - URL 可打开（HTML 失败则用 ds fetch 取 Markdown 再试），否则 source_unreachable
   - 原文命中 quote，且 quote 同时含载体词与价格，否则 quote_mismatch / carrier_missing
   - 档位可解析且与 quote 一致，否则 tier_conflict
   - 窗口可解析，否则 window_missing
   - 二手/经销商域名 → secondhand_forbidden（只作线索）
   - 与企微表判重：同 SKU 只补新档位/刷新证据，不重复建行
   - 等级：A/B 级 + 双源或证据充分 → accepted（auto）；C 级或单源弱证据 → pending_review
6. 写表：accepted 直接写「官方福袋」表；pending_review 等人工裁决
7. 回写线索：lastRunId / lastResult / lastHitAt（空结果写 empty，不改 status）
8. 报告：run.json 记录每线索结果、两源命中数、写入行数
```

原因码：`source_missing` `source_unreachable` `channel_unverified` `quote_mismatch` `carrier_missing` `tier_missing` `tier_conflict` `window_missing` `publisher_mismatch` `duplicate` `secondhand_forbidden` `lane_empty`。

窗口：默认「上次成功日 − 1 天 → 今天」；首次运行取最近 60 天（覆盖双11 档）。节点期可手动传 `--since`。

### 4.4 双源分工与合并口径

| | workbuddy | DeepSeek |
|---|---|---|
| 角色 | 会翻页面、读官方帖/详情页，适合结构复杂的渠道 | 覆盖广、快，适合全网搜「某 IP 有没有发福袋」 |
| 输入 | 按 publisher 合并的 prompt | 按 lead 的查询组（可展开 3–5 条） |
| 输出 | JSON 候选 | JSON 候选 + 引用来源 |
| 失败降级 | job 失败 → 只记该 lane 失败，不阻断另一源 | 无 Key/超时 → 记 lane 失败 |
| 合并 | 同键合并档位；`采集方式` 记「双源」/单源 | 同左 |
| 冲突 | 同名不同价/不同档：以能打开且 quote 命中的那条为准；都命中则两条都留，状态设「存疑」等人工 | 同左 |

两源都空 → 线索 `lastResult=empty`；只有一源失败 → `partial`，不把失败当「官方没发」。

### 4.5 线索健康（固定提示）

- 无线索渠道数（`channelIds` 为空）：抓不了，先补渠道。
- 引用 `dead` 渠道的线索数：要换渠道。
- 超 30 天未跑线索数：节前提醒。
- 连续 ≥ 3 轮 `empty` 线索：建议降优先级或暂停，由人决定。

## 5. UI：tab 结构

一级 tab「官方福袋」，两个子 tab（按要求）：

```
[官方赏]  [官方福袋]
   ├ 抓新品        ├ 抓取任务
   ├ 补齐信息      └ 线索
   └ 抓取渠道
```

### 5.1 抓取任务

- 顶部统计：active 线索 / 无渠道 / 渠道失效 / 表内条数 / 上次成功日。
- 范围选择：全部 active（默认）/ 按优先级 / 勾选线索；「写表」开关（不勾 = dry-run，只出候选）。
- Rail 6 段：准备 → 分派 → 等待 → 验收 → 写表 → 完成。
- 双源状态条：`workbuddy 3 job（2 完成 / 1 运行）· DeepSeek 16 查询（16 完成，命中 9）`。
- 结果按线索分组：每条线索一行「抓到 N 条 / 无新增 / 渠道打不开 / 单源失败」，展开是候选明细与验收结论；`pending_review` 下方是裁决行（来源 URL + 备注 + 采信并写表 / 判废）。
- 底部：写入行数、跳转企微表链接、本轮 run id。
- 历史：最近 8 轮，标 dry-run / 写表 / 线索数 / 双源命中。

### 5.2 线索

- 顶部：线索总数 / 启用中 / 无渠道 / 可用渠道 / 刷新 / 渠道库 / 新建线索。
- 线索表：IP / 类型 / 发行方 / 载体词 / 关联渠道 / 优先级 / 状态 / 最近结果 / 操作（编辑 / 暂停 / 删除）。
- 「编辑」在**行内展开**编辑面板（对齐官方赏的逐行操作），保存直接写 `bag-leads.json`；删除二次确认。
- 渠道库（同页折叠区）：发行方 / 渠道 / 等级 A–D / 状态 / 能回答 / 操作（试抓 / 编辑 / 确认 / 撤回 / 新建），试抓证据在下一行展开；写 `bag-channels.json`。
- 保存失败必须显式报错（不能假装成功）。

颜色全部走 token；完成后跑 `node tooling/check-theme-colors.mjs` 与 `node runtime/theme-audit-all.mjs`（浅色 + 深色）。

## 6. 存储

| 内容 | 位置 | 说明 |
|---|---|---|
| 线索 | `apps/acg-capture/engines/references/bag-leads.json`（仓库） | 插件可写，进版本管理 |
| 渠道 | `apps/acg-capture/engines/references/bag-channels.json`（仓库） | 与现有 `channels.json` 分离 |
| 台账 | 企微「官方福袋」表 `tvZwq0` | 唯一真源，业务可见 |
| 台账本地缓存 | `~/.dsh/acg-capture/cache/bag-ledger.json` | 只作插件展示与判重加速，过期可重建 |
| 运行产物 | `~/.dsh/acg-capture/runs/r-<ts>-bag-discover/` | 插件只读 |

> 相比 v3 的变化：台账从「仓库 JSON 真源」改为「企微表真源」，因为数据最终要写进表；仓库 JSON 只留线索与渠道，避免双真源。

## 7. 代码落点

| 文件 | 改动 |
|---|---|
| `apps/acg-capture/engines/scripts/bag_run.py` | 新入口：`--kind discover`、`--snapshot`、`--leads`、`--write`、`--lanes`、`--since`、`--decide` |
| `scripts/acg/bag_leads.py` | 线索 CRUD + 校验（引用完整性、载体词非空、id 稳定） |
| `scripts/acg/bag_channels.py` | 渠道读写 + 试抓 + tier/状态校验 |
| `scripts/acg/bag_dispatch.py` | 双源派发：workbuddy 分组 + DeepSeek 查询组 + 两源原始输出落盘 |
| `scripts/acg/bag_accept.py` | 合并去重 + 验收（渠道等级 + quote + 档位 + 窗口 + 判重） |
| `scripts/acg/bag_table.py` | 企微「官方福袋」表读写（沿用 `table.py` 的 `run_wecom` 方式）+ 列初始化 |
| `references/bag-leads.json` | 16 条种子线索 |
| `references/bag-channels.json` | 12~15 条种子渠道（米哈游 / 暴雪 / 腾讯 / 网易 / 万代 / 初音 / 吉伊卡哇 / 假面骑士 / 泡泡玛特…） |
| `apps/acg-capture/client.js` | 一级 tab + 两个子页；线索表编辑态；双源状态条 |
| `apps/acg-capture/lib/store.js` | run id 正则加 `bag-discover`；`BAG_*` 路径；线索/渠道/台账缓存读写 |
| `apps/acg-capture/lib/http.js` | `/acg-capture/api/bag/*`：leads（GET/POST/PUT/DELETE）、channels、runs、ledger、snapshot |
| `apps/acg-capture/engines/README.md` | 加「官方福袋」一节与命令 |
| `apps/acg-capture/engines/skills/official-bag-scan/SKILL.md` | 一句话入口（对齐 `acg-official-scan`） |

## 8. 分期与验收

### P0 线索、渠道、表结构（0.5–1 天）

- 16 条线索 + 12~15 条渠道落盘；引擎 `--snapshot`；企微表 18 列建好（复用 5 个空行）。
- 插件一级 tab + 两个子页；线索可编辑并落盘；渠道库可试抓/确认。
- 验收：
  - 改一条线索（载体词、渠道、暂停）→ 刷新后仍在，JSON 正确；
  - 非法引用渠道 / 空载体词 / 改 id 被拒并给原因；
  - `--snapshot` 输出线索健康四项；
  - 企微表列与 §3.3 一致，5 个空行被复用；
  - 单测：线索校验、渠道引用、表判重。

### P1 双源抓取闭环（2–3 天）

- `--kind discover`：workbuddy 分组 + DeepSeek 查询组并发 → 合并 → 验收 → 写表 → 回写线索；插件「抓取任务」+ 裁决。
- 验收：至少一条 P0 线索新增官方 SKU/档位，每条有可打开的官方 URL + quote；C 级候选停在 `pending_review`；单源失败标 `partial` 而不误报「无」；空结果写 `empty`；一次全量（16 线索）在 10 分钟内跑完。

### P2 定时与报告（1–2 天）

- 定时任务：周一/五 11:00，`new_once`，prompt 一条命令 + 5 行汇报（窗口、线索数、双源命中、采信/待确认、写表行数、失败原文）。
- 节前提醒用「超 30 天未跑」；导出 HTML 报告（复刻现有形态）供人看。
- 下游（治理侧读表做子品匹配）**不在本 tab 实现**，另起改动。

### 不回归

- 官方赏三个子页不变；现有 run id 与 `acg_run.py` 命令不受影响；`store.js` 正则放行新旧 kind。

## 9. 定时任务配置（P2 落地）

```
DTSTART;TZID=Asia/Shanghai:20261120T110000
RRULE:FREQ=WEEKLY;BYDAY=MO,FR
```

- `target: new_once`，cwd `workspace`，prompt 只允许跑一条命令，避免定时任务顺手改代码。
- 与现有「官方赏抓新品（MO,FR 09:30）」「官方赏补齐（MO,FR 09:40）」错开。

## 10. 风险与对策

| 风险 | 对策 |
|---|---|
| 双源重复/互相污染 | 同键合并、档位对齐；证据只认 URL + quote，不认「模型共识」 |
| DeepSeek 引用幻觉 | 每条候选必须 URL 可打开 + quote 命中，验证不过一律 pending/判废 |
| 天猫/小程序反爬 | 不破防：走官方社媒/官网公告；天猫只作 C 级人工确认 |
| 「官方」被当授权证明 | 表里只记官方发售事实；授权状态不判 |
| 同名不同档 | 档位硬校验；缺档位集合不允许 auto-accept |
| 线索越加越多没人维护 | 健康指标 + 连续 empty 降级建议；P2 默认 paused |
| 表结构被改 | 写前读字段名校验，缺列显式失败并提示重建 |
| 空结果被当失败 | `lastResult` 分 captured/empty/blocked/error；只有 error/blocked 才需处理 |

## 11. 已确认

1. **企微表列**：13 列（保留 1–9、12–15），已由 `--init-table` 建好。
2. **台账真源**：企微「官方福袋」表（`tvZwq0`），仓库只留线索与渠道，不双写。
3. **C 级渠道**：双源一致 + 原文命中即可直接采信。
4. **定时**：每周一、五 11:00（`schedule-eb24af51-a4b5-4b66-b1bc-7c79c2a829bd`）。

## 12. 已知限制

- DeepSeek 的 Responses API 在本账号上未真正触发 `web_search`（返回无 citations），因此改为「先 Search 取材料、再 Responses 抽取」两步；Search 走 qiaomu 凭据。
- 米游社等 SPA 页面直连拿不到正文，DeepSeek fetch 也只能取到壳；这类原文命中不到时进「待确认」，不判废。
- 原神「心动福袋」官方商品页未写价格，价格只能来自媒体转述 → 该类条目档位可能缺失，进「待确认」等人工补。
