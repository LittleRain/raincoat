---
name: anime-expo-ops-agent
description: 当运营漫展、二次元、同人展、cosplay 或 IP 活动线上平台，需要 Agent 采集行业信号、结构化活动数据、生成活动草稿、同步业务指标并给出运营动作建议时使用。
---

# 漫展运营 Agent

## 目标

这个技能定义漫展行业运营 Agent 的业务执行契约。Hermes 或其他编排器应该读取这个技能，按引用的工作流执行任务，并把调度、连接器、密钥、重试、审批界面等运行时细节留在 Hermes 内部。

## 责任边界

这个技能是以下内容的业务源头：

- 活动发布字段与数据模型
- 活动类型、省市区、场馆、场地字典解析规则
- 情报采集、活动抽取、草稿创建、业务分析、审核工作流
- 提示词合约与输出 schema
- 活动抽取、字典解析和动作建议的评估标准

Hermes 负责：

- 调度、超时和重试
- 社交平台、数据库、API、webhook 等连接器代码
- cookie、token、API key、环境变量等密钥
- 字典同步任务和本地缓存
- 运行状态、游标状态、失败恢复
- 执行权限和审批界面

## Run Types

- `dictionary_sync`：初始化和每周更新字典，包括场馆、场地、省市区。
- `daily_intel`：采集行业信号并产出活动候选。
- `draft_events`：校验后创建或更新活动草稿。
- `business_sync`：规范化内容、交易、订单等业务指标。
- `recommend_actions`：生成运营动作建议。
- `weekly_review`：总结表现、学习结果和下周动作。

## 安全规则

- 未经明确审批，不得发布、改价、推广、降权或删除平台内容。
- 没有证据时，不得推断缺失的日期、场馆、场地、票价或地区。
- `type`、`provinceId`、`cityId` 解析失败，不得调用发布接口。
- `venueId` 或 `placeId` 解析失败，可以设置 `venueUndecided = 1`，但必须进入人工审核。
- `districtId` 解析失败，不要默认选择中心城区，进入人工审核。
- 每条推荐都必须包含证据、预期影响、风险等级和可回滚下一步动作。

## 参考文件

- 产品策略：[references/product-strategy.md](references/product-strategy.md)
- 系统设计：[references/system-design.md](references/system-design.md)
- Harness 设计原则：[references/harness-design.md](references/harness-design.md)
- 实施计划：[references/implementation-plan.md](references/implementation-plan.md)
- 数据模型：[references/data-model.md](references/data-model.md)
- 信息源配置：[references/source-config.md](references/source-config.md)
- 工作流：[references/workflows.md](references/workflows.md)
- 提示词合约：[references/prompts.md](references/prompts.md)
- 评估方案：[references/evals.md](references/evals.md)
- Hermes 交接：[references/hermes-handoff.md](references/hermes-handoff.md)
