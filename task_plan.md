# 漫展运营 Agent 系统落地计划

## 当前阶段

阶段 0：契约对齐与字典同步机制落地。

## 目标

让 Hermes 读取 `skills/anime-expo-ops-agent` 业务契约，跑通：

```text
行业信号采集 -> 活动结构化 -> 字典解析 -> 查重 -> 未发布草稿 -> 审批 -> 业务指标同步 -> 动作建议 -> 周复盘
```

## 核心文件

- 产品策略：`skills/anime-expo-ops-agent/references/product-strategy.md`
- 系统设计：`skills/anime-expo-ops-agent/references/system-design.md`
- Harness 设计原则：`skills/anime-expo-ops-agent/references/harness-design.md`
- 实施计划：`skills/anime-expo-ops-agent/references/implementation-plan.md`
- 数据模型：`skills/anime-expo-ops-agent/references/data-model.md`
- Hermes 交接：`skills/anime-expo-ops-agent/references/hermes-handoff.md`

## 阶段 0：契约对齐（1-2 天）

状态：in_progress

要做：

1. 对齐活动发布字段和 payload。
2. 写入活动类型枚举。
3. 纳入省市区字典。
4. 定义场馆/场地 API 初始化和每周更新机制。
5. 让 Hermes 先实现 `dictionary_sync`，再进入 `daily_intel`。
6. 先实现 artifact store、gate engine、capability flag，再开放写入能力。
7. 活动草稿创建接口未上线前，只生成和校验 payload，不阻塞查重与 dry-run。

验收：

- 省市区字典可读。
- 场馆 API 能分页拉取全量有效场馆。
- 场地 API 能按 `venue_id` 拉取并绑定场馆。
- 字典同步默认每周一次，支持运营人员手动触发。
- 本地缓存能支持 `venue`、`place` 转 `venueId`、`placeId`。
- 模糊匹配进入人工审核，不自动乱选。
- 每个 run 都能回放，且有 gate 结果。
- 已有活动查询接口可用于去重，登录态只放 Hermes secrets。

## 阶段 1：每日情报 dry-run（3-5 天）

状态：pending

只采集两个指定测试源，输出 `event_candidate` 和草稿 payload，不写业务系统。

测试源：

- 微博：`https://weibo.com/6596632265/QuYfxs1po`
- 小红书：`http://xiaohongshu.com/user/profile/6333b2ee0000000023024449`

验收补充：

- 不要求预先提供 30 条历史样本。
- 第 1 周至少从你的人工反馈中沉淀 10 条结构化反馈样本。
- 反馈样本用于逐步形成 golden set。

## 阶段 2：活动草稿入库（1 周）

状态：pending

只允许创建未发布草稿，不允许自动发布。

## 阶段 5：周复盘与规则迭代（持续）

状态：pending

每周把抽取错误、建议采纳/拒绝、漏掉机会沉淀回规则、prompt 和 eval。

## 阶段 3：业务指标同步（1 周）

状态：pending

同步内容、交易、订单、库存和渠道指标，形成每日业务快照。

## 阶段 4：动作建议与审批闭环（1-2 周）

状态：pending

每天生成带证据的动作建议，按风险等级进入审批，并记录采纳/拒绝/执行结果。
