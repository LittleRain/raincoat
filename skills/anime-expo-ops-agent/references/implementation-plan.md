# 实施计划

## 阶段 0：契约对齐与字典同步

周期：1-2 天。

目标：

- Hermes 能读取本技能。
- 字典同步能跑通。
- 活动发布 payload 契约稳定。
- 活动草稿创建接口未上线不阻塞流程。

要做：

1. 记录活动草稿创建接口未上线，`can_create_unpublished_drafts` 默认关闭。
2. 接入已有活动查询接口，用于去重。
3. Hermes 实现 artifact store，至少能保存 `run_manifest`、worker 输出和 gate 结果。
4. Hermes 实现运营视图同步，优先接飞书多维表格，字段见 `operator-views.md`。
5. Hermes 实现 capability flag，默认只允许 dry-run。
6. Hermes 实现 `dictionary_sync`。
7. 校验省市区 Excel 可读。
8. 场馆 API 分页拉取全量有效场馆。
9. 场地 API 按 `venue_id` 拉取并绑定场馆。

验收：

- 本地缓存能解析活动类型、省份、城市、区县、场馆、场地。
- `dictionary_sync` 首次部署执行成功。
- 每周一 03:00 调度已配置。
- 支持手动刷新。
- 每次同步都有 artifact 和 gate 结果。
- 飞书 `runs` 和 `errors` 表能看到本次同步摘要。
- dry-run 不使用模拟 B 站 API、mock 场馆或 mock 场地。
- 项目搜索接口的登录态由 Hermes secrets 管理，不写入 repo。

## 阶段 1：每日情报 dry-run

周期：3-5 天。

目标：

- 只接两个信息源。
- 只生成结构化结果，不写业务系统。

v0.1 测试源：

- 微博：`https://weibo.com/6596632265/QuYfxs1po`
- 小红书：`http://xiaohongshu.com/user/profile/6333b2ee0000000023024449`

要做：

1. Hermes 实现 `daily_intel` 调度。
2. 按 `source-config.md` 抓取微博指定 uid 最近 20 条动态。
3. 按 `source-config.md` 抓取小红书指定 profile 最近 20 条笔记。
4. 采集并归一化为 `source_item`。
5. 调用活动抽取提示词。
6. 输出 `event_candidate`。
7. 运行字典解析，但不写入。
8. 保存所有 artifacts。
9. 同步飞书多维表格运营视图，至少包含 `runs`、`source_items`、`event_candidates`、`gate_results` 和 `errors`。
10. 生成日报。
11. 通过 live dry-run 收集运营反馈样本。

验收：

- 每天采集 >= 20 条相关信息。
- 每次采集的原始内容都能在飞书 `source_items` 表直接查看。
- `source_items` 中能看到原文链接、正文摘要、来源账号、URL 状态、采集状态和 raw artifact 链接。
- 每个 `event_candidate` 都能通过 `source_item_id` 反查原始内容。
- 报告中 `run_mode = dry_run` 且 `uses_mock_data = false`。
- 如果真实 connector 失败，`event_candidates` 为空或只包含真实 source 支持的候选，不得用示例内容补齐。
- 已积累反馈样本中活动识别 precision >= 80%；golden set 达到 30 条后按完整样本集统计。
- 所有非空字段都有 evidence。
- 不编造时间、场馆、票价。
- replay 输出可复现。
- 第 1 周至少积累 10 条结构化反馈样本。

## 阶段 2：查重与草稿 payload

周期：3-5 天。

目标：

- Hermes 能查已有活动并生成草稿 payload。
- 仍不调用创建接口。

要做：

1. 接入已有活动查询接口。
2. 优先按名称查询；有开展时间时用 `start_min`、`start_max` 缩小范围。
3. 生成 `platform_event_match`。
4. 生成 `platform_event_draft_payload`。
5. 输出 `create_draft`、`merge_review`、`needs_review` 队列。
6. 运行 schema gate、dictionary gate、duplicate gate。
7. 同步飞书 `dictionary_resolution`、`project_search_results`、`draft_payloads` 和 `gate_results` 表。

验收：

- 重复活动误判率 <= 10%。
- `platform_event_draft_payload` 通过本地 schema 校验。
- 冲突字段进入人工审核。
- gate 阻断原因进入 artifact。
- 你能在飞书 `draft_payloads` 表看到每个候选准备写入系统的完整摘要和 payload artifact 链接。

## 阶段 3：未发布草稿入库

周期：1 周。

目标：

- Hermes 可以创建未发布活动草稿。
- 不允许自动发布。

要做：

1. 等活动草稿创建接口上线后，接入活动草稿创建接口。
2. 实现字段映射。
3. 写入后回填平台活动 ID。
4. 失败写入进入错误队列。
5. 给运营人员推送审批任务。
6. 仅在 `can_create_unpublished_drafts` 打开时允许写入。

验收：

- 草稿创建成功率 >= 95%。
- 人工确认一个草稿 <= 30 秒。
- 不发生自动发布。
- 所有失败都有错误记录。
- 所有写入都能从平台 id 反查到 run artifact。

## 阶段 4：业务指标同步

周期：1 周。

目标：

- Hermes 每天同步内容、交易、订单、库存和渠道指标。

要做：

1. 接内容数据。
2. 接交易/订单数据。
3. 接库存/退款数据。
4. 生成 `business_metric_snapshot`。
5. 与 7 日和 28 日基线比较。

验收：

- GMV、订单、退款等关键指标能与业务系统对账。
- 能识别转化异常、库存风险、未上架机会。

## 阶段 5：动作建议与审批闭环

周期：1-2 周。

目标：

- 每天生成可执行动作建议。
- 每条建议能追踪采纳、拒绝和执行结果。

要做：

1. 生成最多 10 条建议。
2. 每条建议包含证据、影响、风险、下一步。
3. 按风险等级进入审批。
4. 记录 approve/reject/edit。
5. 回写执行结果和指标变化。

验收：

- 每天 >= 5 条有证据建议。
- 建议采纳率 >= 30%。
- 有害推荐数量 = 0。

## 阶段 6：周复盘与规则迭代

周期：持续。

目标：

- 让运营反馈沉淀为规则、prompt 和 eval。

要做：

1. 每周输出复盘。
2. 收集 5 条采纳建议、5 条拒绝建议、5 条抽取修正、3 个漏掉机会。
3. 判断失败原因属于业务规则还是 Hermes 实现。
4. 改 `skills/anime-expo-ops-agent` 或 Hermes。
5. 从运营反馈中更新 golden set，并 replay 关键样本。

验收：

- 同类错误逐周下降。
- 规则变化有 git diff。
- 推荐质量能用采纳率和结果指标衡量。
- golden set diff 可追踪。

## 你下一步需要提供

优先级最高：

1. 飞书多维表格 app token、目标表格配置或 Hermes 可用的飞书写入方式。
2. v0.1 live dry-run 后的人工反馈：哪些活动应创建、哪些不应创建、哪些字段需要修正。

随后提供：

3. 活动草稿创建接口上线后的 URL、Method、鉴权、headers、成功返回、失败返回。
