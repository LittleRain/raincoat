---
name: acg-virtual-goods
description: 游戏虚拟商品的每周调度入口。每周把行业里有热度的游戏（不限新老）抓一遍：热度门槛＝发行商名单 / 预约 10 万 / 畅销榜 Top 50（有 App Store 页不算热度）；三通道取证（App Store 内购页确定性解析 + workbuddy + DeepSeek）后按「游戏 + 商品名」去重，只把表里缺的商品行补进去，不更新已有行。当用户说「跑一轮游戏虚拟商品」「补一下游戏代币/月卡/通行证」「行业热门游戏抓一遍」时使用。
---

# 游戏虚拟商品周更（调度入口）

真正的逻辑在 `apps/acg-capture/engines/scripts/vg_run.py`，这里只写怎么触发、怎么判断结果、出问题看哪里。
**不要手写拉表、比对、写表逻辑。** 口径与表结构见 [`docs/virtual-goods.md`](../../docs/virtual-goods.md)。

## 核心口径（2026-11-18 起）

- **没有游戏订阅库**：企微表 `ty2XMk` 里去重的游戏名就是清单。
- **每轮抓行业热门，不限新老**：热度门槛＝发行商名单 / 预约 10 万 / 畅销榜 Top 50；App Store 页只说明抓得到商品，不算热度。
- **一个商品一行**：去掉「档位」列，各面额/渠道价格全写进备注；判重键＝游戏 + 商品名。
- **只补缺**：只 `add` 表里没有的商品行；已有行不改、不刷价格。

## 命令

```bash
cd /Users/raincai/Documents/GitHub/workspace

# 每周一轮（定时任务用这条）：抓行业热门游戏 → 过门槛 → 补缺行
python3 apps/acg-capture/engines/scripts/vg_run.py --kind discover --write --trigger schedule

# 只看这轮会抓哪些热门游戏（不调模型、不写表）
python3 apps/acg-capture/engines/scripts/vg_run.py --kind discover --discover-only

# 只用一条 lane 排障
python3 apps/acg-capture/engines/scripts/vg_run.py --kind discover --lanes deepseek

# 只看台账派生的游戏清单与缺口
python3 apps/acg-capture/engines/scripts/vg_run.py --snapshot

# 表结构（幂等；会把「上次核验」改名「入库日期」）
python3 apps/acg-capture/engines/scripts/vg_run.py --init-table

# 人工裁决待确认条目
python3 apps/acg-capture/engines/scripts/vg_run.py --decide <runId> --item <itemId> --decision accept --write
```

不加 `--write` 就是 dry-run，只产候选。运行产物在 `~/.dsh/acg-capture/runs/r-<ts>-vg-discover/`，
插件「ACG信息抓取 → 游戏虚拟商品」读的是同一份。

## 怎么判断这一轮该做什么

1. `run.json` 的 `discovery.kept` 是本轮过门槛的热门游戏数；0 说明这轮没发现达标游戏，是**正常结果**。
2. `discovery.droppedGames` 是「为什么没抓」的清单：`threshold_missed`（热度不够）、`no_monetization`（看不出内购）、`duplicate`（候选重复）。想放宽就改 `references/vg-sources.json` 的 `thresholds`。
3. `counts.written` 是补进去的新行数；`duplicate` 是表里已有、被跳过的商品行；`pending` 是待人工确认的条数。

## 验收口径（脚本已内置，不要绕过）

1. 来源必须命中该游戏/发行商/全局渠道域名；二手、代充、账号交易、**以及 DeepSeek 搜到的第三方页**一律判废，只在 run.json 里留作线索，不占待确认。
2. 页面能打开 + 原文命中 `quote`，且 quote 同时含**商品名 + 档位（代币）+ 价格**。
3. 代币折算自洽：面额/价格 ≥ 1，否则进待确认。
4. 商品名归一：`充值1980枚龙晶` / `980枚古老梦华` 一律并成 `龙晶` / `古老梦华`，面额+价格进备注；判重按 `游戏 + 商品名`，命中 → `duplicate`，不写表、不改已有行。
5. 等级：A/B 直接采信；C 级模型单源进待确认；`store` 通道（App Store 内购页）单片采信。
6. 拿不到正文或价格的进「待确认」，不猜价、不写 0。

## 三通道分工

| 通道 | 说明 |
|---|---|
| `store` | 拉候选自带的 `appStore` 页面解析「App内购买」区块，零模型、最稳；只代表 iOS 内购价 |
| `workbuddy` | **一个 job 覆盖全部游戏**，翻官网/公告/充值页，补非 iOS 口径 |
| `DeepSeek` | 每游戏 3–4 组查询，反查公告与漏项 |

## 出问题看哪里

| 现象 | 先看 |
|---|---|
| 表里没有新行 | 是否带 `--write`；`counts.written`；条目是否都是 `duplicate` / `pending_review` |
| 新游戏没被算进来 | `new-games.json` 的 `dropped[].reason`，多半是 `threshold_missed` 或 `not_launched` |
| 某游戏一直「待确认」 | 该条 `reasons`（多为 `channel_unverified` / `price_missing` / `c_tier_single_lane`）；`deepseek_non_official` 是 DS 第三方页被判废，属预期 |
| `store` 通道 0 条 | 发现候选没有 `appStore`，或 App Store 页面没有内购区块（看 `store_error` 事件） |
| App Store 大量 429 | 已按游戏串行 + 1s 间隔；仍有就隔一轮再跑 |
| workbuddy 报 `acc-product-config-v3.json` 不存在 | WorkBuddy 缓存基文件丢了：把 `~/.workbuddy/cache/acc-product-config-v3-*.json` 里最新一份复制成 `~/.workbuddy/cache/acc-product-config-v3.json` 再重试 |
| 游戏汇总里某游戏缺一类 | 表里本来就没有这类商品（如第五人格缺月卡/通行证）；要补就人工加行，不会自动重抓 |
