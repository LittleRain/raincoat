# 系统设计

## 总体架构

```text
Hermes Harness
  -> Run Scheduler
  -> Artifact Store
  -> Gate Engine
  -> Replay Runner
  -> Eval Runner
  -> Dictionary Sync Worker
  -> Source Collector Worker
  -> Event Extractor Worker
  -> Duplicate Matcher Worker
  -> Draft Payload Worker
  -> Draft Writer Worker
  -> Business Sync Worker
  -> Recommendation Worker
  -> Approval + Feedback Worker
  -> Weekly Review Worker
```

设计重点：Hermes 不是让 Agent 自由发挥，而是给每个 worker 提供固定输入、固定输出、门禁、日志和回放能力。

## 责任分层

`skills/anime-expo-ops-agent` 负责：

- 业务规则。
- 数据模型。
- 字段契约。
- prompt 合约。
- 风险分级。
- eval 标准。

Hermes 负责：

- 定时任务。
- API 调用。
- 登录态、cookie、token。
- 本地缓存。
- 失败重试。
- 死信队列。
- 审批消息。
- 工具执行。
- artifact 存储。
- 运营视图同步，例如飞书多维表格。
- replay。
- gate 判定。
- capability flag。

业务系统负责：

- 活动最终状态。
- 内容和交易数据。
- 订单、库存、退款数据。
- 用户可见发布状态。

## 数据流

```text
social/web signals
  -> source_item
  -> event_candidate
  -> dictionary_resolution
  -> platform_event_match
  -> platform_event_draft_payload
  -> gate_result
  -> unpublished platform draft
  -> approval task
```

业务分析流：

```text
content/order/event/inventory APIs
  -> business_metric_snapshot
  -> anomaly/opportunity detection
  -> recommendation
  -> approval
  -> execution result
  -> weekly_review
```

## 字典同步设计

Hermes 必须先执行 `dictionary_sync`。

字典来源：

- 活动类型：静态枚举，见 `data-model.md`。
- 省市区：本地 Excel，`assets/city-dictionary.xlsx`。
- 场馆：场馆 API。
- 场地：场地 API，依赖 `venue_id`。

同步频率：

- 首次部署立即全量同步。
- 之后每周一 03:00 同步一次。
- 支持运营人员手动刷新。

缓存要求：

- 保留 raw 响应。
- 保留 `synced_at`。
- 保留新增、更新、失效统计。
- 场地必须绑定 `venue_id`。
- 只使用 `status_text = 有效` 的场馆。

## 活动草稿写入设计

写入前必须完成：

- 活动类型解析：`event_type_name` -> `type`
- 省市区解析：`province/city/district` -> `provinceId/cityId/districtId`
- 场馆解析：`venue` -> `venueId`
- 场地解析：`place` -> `placeId`
- 时间状态生成：`projectTimeStatus`
- 价格状态生成：`priceStatus`
- 票价从元转分
- `performanceDesc` JSON 字符串生成

硬性阻断：

- `type` 为空，不能写入。
- `provinceId` 为空，不能写入。
- `cityId` 为空，不能写入。
- `placeId` 不属于 `venueId`，不能写入。
- payload schema 校验失败，不能写入。

允许带审核写入：

- `venueId` 或 `placeId` 不确定，可设置 `venueUndecided = 1`。
- `districtId` 不确定，进入人工审核，不默认选择。
- 缺海报，进入缺素材提示。
- 时间或价格待定，设置对应状态字段。

## 风险权限

低风险，可在预授权后自动执行：

- 同步字典。
- 采集 source items。
- 生成活动候选。
- 创建未发布草稿。
- 发送日报。

中风险，必须审批：

- 更新活动详情。
- 发布活动。
- 推荐资源位。
- 生成外联模板。

高风险，必须审批且记录理由：

- 改价。
- 花预算。
- 删除内容。
- 降权内容。
- 商务承诺。

## Harness 门禁

每次工具调用前必须经过 gate。

| Gate | 阻断条件 | 输出 |
| --- | --- | --- |
| schema gate | JSON 不合法或缺必填字段 | `failed_schema_validation` |
| evidence gate | 非空关键字段没有 evidence | `missing_evidence` |
| dictionary gate | 必需 id 未解析或关系错误 | `dictionary_resolution_failed` |
| duplicate gate | 疑似重复但未确认 | `duplicate_review_required` |
| risk gate | 中高风险动作未审批 | `approval_required` |
| capability gate | 对应能力开关未开启 | `capability_disabled` |

Gate 输出必须进入 artifact，不能只写日志。

## Artifact 设计

每次 run 至少保存：

- `run_manifest`
- `source_items`
- `event_candidates`
- `dictionary_resolution_results`
- `duplicate_match_results`
- `draft_payloads`
- `gate_results`
- `tool_calls`
- `approval_tasks`
- `recommendations`
- `feedback_events`
- `errors`

artifact 要求：

- 可按 `run_id` 查询。
- 可回放。
- 可对比两个版本输出差异。
- 可追溯到原始 source。

## 运营视图设计

Hermes 必须把关键 artifact 同步成固定运营视图，推荐使用飞书多维表格。详细字段见 `operator-views.md`。

设计分工：

- Artifact store 是事实源，保存完整 JSON、raw 响应、脱敏错误和 replay 输入。
- 飞书多维表格是操作视图，保存摘要、状态、链接和人工反馈字段。
- 飞书写入失败不得影响 artifact 保存，但必须进入 `errors`。
- 人工在飞书里的审核、拒绝、修正必须回写为 `feedback_events` artifact。

每次 `daily_intel` 至少同步以下表：

- `runs`
- `source_items`
- `event_candidates`
- `dictionary_resolution`
- `project_search_results`
- `draft_payloads`
- `gate_results`
- `errors`
- `feedback_events`

## Replay 与 Eval

所有新规则先 replay，再自动化。

Replay 固定：

- 输入样本。
- 字典缓存版本。
- prompt 版本。
- schema 版本。
- Hermes worker 版本。

Eval 输出：

- 字段准确率。
- 字典解析准确率。
- 重复误判率。
- payload schema 通过率。
- gate 阻断原因分布。

只有 eval 通过后，才能打开对应 capability flag。

## 失败处理

每个 worker 都要写入运行记录：

- 输入数量。
- 输出数量。
- 成功数量。
- 失败数量。
- 错误类型。
- 可重试状态。

不要静默失败。失败项应进入死信队列或人工审核队列。
