---
name: acg-official-scan
description: 官方赏行业扫描的调度入口。两条命令：补齐企微表里缺单抽价、缺子品结构（含单套数量）的赏盘；抓上次成功日之后中国大陆品牌新发售的赏盘。执行由 workbuddy 完成，验收（来源/原文/Σ/去重/二手拦截）由 scripts/acg_run.py 机检后自动写表，结果在 DSH「ACG信息抓取」插件里可见。当用户说「跑一轮官方赏」「补一下抽赏价格/数量」「看看有没有新赏盘」时使用。
---

# 官方赏巡检（调度入口）

真正的逻辑在 `scripts/acg_run.py`，这里只写怎么触发、怎么验收、出问题看哪里。**不要在对话里重写拉表、比对、写表逻辑。**

## 两条命令

```bash
cd /Users/raincai/Documents/GitHub/workspace

# 1) 补齐：缺单抽价的盘 + 缺子品结构的盘（没有子品行要建行）+ 缺单套数量的行
#    默认 workbuddy + DeepSeek 双通道；DeepSeek 没配 key 或超时只降级，不影响写表
python3 apps/acg-capture/engines/scripts/acg_run.py --kind backfill --write
python3 apps/acg-capture/engines/scripts/acg_run.py --kind backfill --lanes deepseek --write   # 只走 DeepSeek

# 2) 抓新品：上次成功日 −1 天 → 今天，只看中国大陆品牌
python3 apps/acg-capture/engines/scripts/acg_run.py --kind discover --write

# 排障：只抓渠道原文、不派 Agent；超时后回收 job 结果
python3 apps/acg-capture/engines/scripts/acg_run.py --kind discover --no-agent
python3 apps/acg-capture/engines/scripts/acg_run.py --resume <runId> --write

# 只看缺口、不建运行（排障用）
python3 apps/acg-capture/engines/scripts/acg_run.py --snapshot
```

- `--write` 才会写表；不加就是 dry-run，只产候选。
- `--batch N` 控制单轮最多派几个盘，**默认 999 = 全部缺口一次派完**（一个 job 装整批，不是一盘一个 job）；等 Agent 的超时按盘数放大（90 秒/盘，封顶 1 小时）。盘多时建议切 4–6 个一批，单 job 塞 20 个盘会拖到超时。
- `--lanes` 控制补齐通道，默认 `workbuddy,deepseek`：workbuddy 翻官方页面，DeepSeek 搜索补代理整箱页/日台新闻/公众号正文；两边候选按盘名互补合并后**过同一套验收**，口径不放松。
- 抓新品会先用 ego-browser（登录态）抓微博 / 小红书原文，再按 `--groups`（默认 3）分组派 Agent；
  `--wait` 是等 Agent 的秒数上限（默认 1200），超时记 `partial`，用 `--resume <runId>` 回收。
- 单轮跑完的状态、逐条结论、判废原因都在 `~/.dsh/acg-capture/runs/<runId>/`，插件页读的是同一份。

## 验收口径（脚本已内置，不要绕过）

1. 来源必须能打开；原文必须命中 `quote`；数字必须与 quote 一致。
   来源不限官方站点（小红书 / 微博 / 公众号 / 新闻站都可以，二手交易平台仍拦）；
   `quote` 逐字不中时按 2-gram 覆盖率兜底（≥0.6），但数字与 Σ 不放松。
2. 子品数量必须 `Σ(各赏，不含 LAST) == 整套抽数`。
3. 千岛 / 闲鱼 / 抖音 / 拆卡聚合站等二手来源直接判废；只允许当线索，不采数字。
4. 表里已有的盘按名称归一化去重，不重复建行。
5. 判定不了的进「待确认」，不写表、不猜。
6. 产品类型见 `references/product-types.json`：`inScope` 直接入库，`confirm` 里的边界类型（盲盒 / 手办 / 毛绒…）
   停在 `pending_review`（`product_type_confirm`），**要在对话里向用户确认后再写**。

## 渠道

品牌 → 渠道 → 爬取方式在 [`references/channels.json`](../../references/channels.json)。**只有 `status=confirmed` 的渠道会被抓新品使用**；`pending` 只能在插件「抓取渠道」里试抓对齐，`dead` 不再使用。

抓取方式按 `type` 分工：`weibo` / `xhs` 由 ego-browser 用登录态直接抓原文；`wechat`（公众号）没有列表页，
先调 DeepSeek 搜索 API 找 `mp.weixin.qq.com` 文章，再交给 workbuddy 判定，验收时用浏览器渲染正文核对。

## 出问题看哪里

| 现象 | 先看 |
|---|---|
| 报告「没有已确认渠道」 | 插件「抓取渠道」里把品牌渠道标为已确认 |
| 某盘一直是「待确认」 | `runs/<id>/run.json` 里该条的 `reasons` |
| 写入数为 0 | 确认命令带 `--write`，且该条 `status=accepted` |
| 运行中断 | `run.json` 的 `error`；宿主重启会把 running 标成 interrupted |
| 跑完 `agent_timeout` / 写入 0 | 先 `--resume <runId>` 回收；还不行再整轮重跑 |
| 「渠道原文：0 条」 | ego-browser 是否可用、微博/小红书登录态是否失效（`--kind discover --no-agent` 单独验） |
