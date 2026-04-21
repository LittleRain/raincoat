# 运营可视化与人工反馈

## 目标

Hermes 的每次运行都必须有固定、可直接查看的运营视图。Artifact store 是事实源，飞书多维表格是运营查看、筛选、审核和反馈的工作台。

原则：

- 每个 run 都生成一个 `run_id`。
- 每个关键节点都写入固定表。
- 表格里的每一行都能反查到 artifact 原文。
- 表格可以截断展示长文本，但不能替代 raw artifact。
- 表格不得保存 cookie、token、完整请求 header 或登录态。

## 推荐飞书多维表格结构

建议一个应用对应一个多维表格，按节点分表。

### 1. 运行总览：`runs`

用途：查看每次任务是否跑完、跑了哪些 worker、是否有异常。

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `run_id` | 文本 | Hermes 生成的唯一运行 ID |
| `run_type` | 单选 | `dictionary_sync`、`daily_intel`、`draft_events` 等 |
| `started_at` | 日期时间 | 开始时间 |
| `finished_at` | 日期时间 | 结束时间 |
| `status` | 单选 | `success`、`partial`、`failed` |
| `source_count` | 数字 | 本次采集 source item 数 |
| `candidate_count` | 数字 | 活动候选数 |
| `payload_count` | 数字 | 草稿 payload 数 |
| `blocked_count` | 数字 | 被 gate 阻断数 |
| `error_count` | 数字 | 错误数 |
| `artifact_root` | 链接 | 本次 artifact 根目录或详情页 |
| `report_url` | 链接 | 中文 dry-run 报告 |
| `owner_feedback_status` | 单选 | `待看`、`已看`、`需重跑`、`可进入下轮` |
| `run_mode` | 单选 | `dry_run`、`simulation`、`production` |
| `uses_mock_data` | 复选框 | 是否使用了 mock/fixture/demo 数据 |
| `run_validity` | 单选 | `valid`、`invalid`、`needs_review` |

规则：

- `dry_run` 下 `uses_mock_data = true` 时，`run_validity` 必须为 `invalid`。
- 无效 run 不得进入人工反馈训练、eval 或 golden set。
- 如果真实 connector 失败，应展示失败，不得用 mock 数据填充下游表。

### 2. 原始内容：`source_items`

用途：你每天优先看的表，确认 Hermes 到底抓到了什么。

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `run_id` | 文本 | 关联运行 |
| `source_item_id` | 文本 | 稳定 source item ID |
| `source_type` | 单选 | `weibo`、`xiaohongshu` 等 |
| `source_account` | 文本 | 账号名、uid 或 user_id |
| `source_account_expected` | 文本 | 配置中期望的 uid/user_id |
| `source_account_status` | 单选 | `matched`、`mismatch`、`unknown` |
| `source_scope_status` | 单选 | `valid`、`mismatch`、`unknown` |
| `source_url` | 链接 | 原文 URL |
| `url_status` | 单选 | `openable`、`login_required`、`invalid`、`unknown` |
| `published_at` | 日期时间 | 原发布时间 |
| `collected_at` | 日期时间 | 采集时间 |
| `raw_text_preview` | 多行文本 | 原文前 500-1000 字 |
| `raw_media_count` | 数字 | 图片/视频数量 |
| `engagement_summary` | 文本 | 转评赞藏等摘要 |
| `content_hash` | 文本 | 去重 hash |
| `raw_artifact_url` | 链接 | 完整 raw artifact |
| `collector_status` | 单选 | `success`、`skipped`、`failed` |
| `error_type` | 单选 | `auth_required`、`unsupported_connector`、`source_scope_mismatch`、`invalid_source_url`、`empty_source_text`、空 |
| `人工判断` | 单选 | `是活动`、`不是活动`、`不确定`、空 |
| `人工备注` | 多行文本 | 你的反馈 |

写入规则：

- 采集 worker 完成后立即写入。
- 即使后续抽取失败，也必须能在这里看到原始内容。
- 如果 `source_scope_status != valid`，不得进入 `event_candidates`。
- 如果 uid/user_id 正确但账号名不一致，`source_scope_status` 可以是 `valid`，但 `source_account_status` 必须是 `mismatch`，并写入 `gate_results`。
- 如果 `url_status` 是 `invalid` 或 `login_required`，不得自动抽取，除非人工确认。

### 3. 抽取候选：`event_candidates`

用途：查看模型从原始内容里抽出了哪些活动。

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `run_id` | 文本 | 关联运行 |
| `candidate_id` | 文本 | 活动候选 ID |
| `source_item_ids` | 文本 | 关联 source item |
| `source_url` | 链接 | 主证据 URL |
| `name` | 文本 | 活动名称 |
| `event_type_name` | 单选/文本 | 活动类型名称 |
| `province` | 文本 | 原始省份 |
| `city` | 文本 | 原始城市 |
| `district` | 文本 | 原始区县 |
| `venue` | 文本 | 原始场馆 |
| `place` | 文本 | 原始场地 |
| `start_date` | 日期时间 | 开始时间 |
| `end_date` | 日期时间 | 结束时间 |
| `ticket_price_min` | 数字 | 最低票价，单位元 |
| `ticket_price_max` | 数字 | 最高票价，单位元 |
| `confidence` | 数字 | 抽取置信度 |
| `evidence_summary` | 多行文本 | 字段证据摘要 |
| `evidence_gate_status` | 单选 | `pass`、`needs_review`、`failed` |
| `candidate_status` | 单选 | `new`、`needs_review`、`rejected`、`approved` |
| `人工判断` | 单选 | `通过`、`拒绝`、`需修改`、空 |
| `修改字段` | 多行文本 | 人工修正后的字段 |
| `拒绝原因` | 单选 | `not_an_event`、`source_scope_mismatch`、`invalid_evidence_url`、`wrong_date`、`wrong_city`、`duplicate`、其他 |

写入规则：

- 只有通过来源完整性门禁的 source item 才能生成候选。
- 每个候选必须展示至少一条证据摘要。
- evidence 不通过时保留行，但 `candidate_status` 必须是 `needs_review` 或 `rejected`。

### 4. 字典解析：`dictionary_resolution`

用途：确认活动类型、省市区、场馆、场地是否被正确转成 ID。

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `run_id` | 文本 | 关联运行 |
| `candidate_id` | 文本 | 活动候选 ID |
| `field` | 单选 | `type`、`province`、`city`、`district`、`venue`、`place` |
| `raw_value` | 文本 | 原始值 |
| `resolved_id` | 文本/数字 | 解析出的 ID |
| `resolved_name` | 文本 | 解析后的名称 |
| `confidence` | 数字 | 解析置信度 |
| `resolution_status` | 单选 | `exact`、`fuzzy`、`missing`、`failed` |
| `candidate_options` | 多行文本 | 多个候选时列出 |
| `gate_result` | 单选 | `pass`、`needs_review`、`failed` |
| `人工确认ID` | 文本 | 人工修正 ID |
| `人工备注` | 多行文本 | 反馈 |

### 5. 已有活动查重：`project_search_results`

用途：看候选活动是否已经在平台存在。

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `run_id` | 文本 | 关联运行 |
| `candidate_id` | 文本 | 活动候选 ID |
| `query_name` | 文本 | 查询名称 |
| `query_start_min` | 日期时间 | 查询时间下限 |
| `query_start_max` | 日期时间 | 查询时间上限 |
| `platform_event_id` | 文本 | 平台活动 ID |
| `platform_event_name` | 文本 | 平台活动名称 |
| `platform_city` | 文本/数字 | 平台城市 |
| `platform_start_time` | 日期时间 | 平台开始时间 |
| `platform_venue_name` | 文本 | 平台场馆名 |
| `match_type` | 单选 | `exact`、`likely`、`possible`、`none` |
| `match_score` | 数字 | 匹配分 |
| `recommended_action` | 单选 | `skip`、`merge_review`、`update_draft`、`create_draft` |
| `raw_artifact_url` | 链接 | 原始搜索结果 |

### 6. 草稿负载：`draft_payloads`

用途：确认如果要创建草稿，最终会传什么字段。

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `run_id` | 文本 | 关联运行 |
| `candidate_id` | 文本 | 活动候选 ID |
| `payload_status` | 单选 | `ready`、`needs_review`、`blocked` |
| `name` | 文本 | 活动名称 |
| `type` | 数字 | 活动类型 ID |
| `provinceId` | 数字 | 省份 ID |
| `cityId` | 数字 | 城市 ID |
| `districtId` | 数字 | 区县 ID |
| `venueId` | 数字 | 场馆 ID |
| `placeId` | 数字 | 场地 ID |
| `venueUndecided` | 数字 | 场馆待定 |
| `startTime` | 日期时间 | 开始时间 |
| `endTime` | 日期时间 | 结束时间 |
| `projectTimeStatus` | 数字 | 时间状态 |
| `priceStatus` | 数字 | 价格状态 |
| `minPrice` | 数字 | 最低价，单位分 |
| `maxPrice` | 数字 | 最高价，单位分 |
| `poster_portrait_url` | 链接 | 竖图 |
| `poster_landscape_url` | 链接 | 横图 |
| `payload_artifact_url` | 链接 | 完整 payload |
| `人工判断` | 单选 | `可创建`、`先不创建`、`需修改`、空 |

### 7. 门禁结果：`gate_results`

用途：看每一步为什么通过或被拦截。

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `run_id` | 文本 | 关联运行 |
| `stage` | 单选 | `source_collection`、`event_extraction`、`dictionary_resolution`、`duplicate_match`、`draft_payload`、`write` |
| `entity_type` | 单选 | `source_item`、`event_candidate`、`payload`、`tool_call` |
| `entity_id` | 文本 | 对应对象 ID |
| `gate_name` | 文本 | gate 名称 |
| `gate_status` | 单选 | `pass`、`needs_review`、`failed` |
| `reason_code` | 文本 | 阻断原因 |
| `reason_detail` | 多行文本 | 具体说明 |
| `created_at` | 日期时间 | 记录时间 |

### 8. 错误队列：`errors`

用途：集中看采集失败、接口失败、解析失败。

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `run_id` | 文本 | 关联运行 |
| `worker` | 文本 | 失败 worker |
| `entity_id` | 文本 | 关联对象 |
| `error_type` | 单选 | `auth_required`、`unsupported_connector`、`source_scope_mismatch`、`invalid_source_url`、`api_error`、`schema_error`、其他 |
| `retryable` | 复选框 | 是否可重试 |
| `message` | 多行文本 | 错误摘要，不能含密钥 |
| `raw_artifact_url` | 链接 | 脱敏后的 raw error |
| `owner_action` | 单选 | `待处理`、`已处理`、`忽略` |

### 9. 人工反馈：`feedback_events`

用途：把你的判断沉淀为训练和 eval 数据。

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `feedback_id` | 文本 | 反馈 ID |
| `run_id` | 文本 | 关联运行 |
| `entity_type` | 单选 | `source_item`、`event_candidate`、`dictionary_resolution`、`draft_payload`、`recommendation` |
| `entity_id` | 文本 | 对象 ID |
| `feedback_type` | 单选 | `approved`、`rejected`、`edited` |
| `feedback_label` | 单选 | `not_an_event`、`wrong_city`、`wrong_date`、`invalid_evidence_url` 等 |
| `corrected_fields` | 多行文本 | JSON 或字段摘要 |
| `reason` | 多行文本 | 反馈原因 |
| `created_by` | 文本 | 反馈人 |
| `created_at` | 日期时间 | 反馈时间 |
| `add_to_golden_set` | 复选框 | 是否加入 golden set |

## 写入顺序

每次 `daily_intel` 必须按以下顺序写表：

1. `runs` 写入 running 状态。
2. 采集完成后写 `source_items` 和 `errors`。
3. 来源完整性门禁后写 `gate_results`。
4. 抽取完成后写 `event_candidates`。
5. 证据 URL 门禁后写 `gate_results`。
6. 字典解析后写 `dictionary_resolution`。
7. 查重后写 `project_search_results`。
8. payload 生成后写 `draft_payloads`。
9. run 结束后更新 `runs` 汇总字段和 `report_url`。

## 查看方式

建议你每天只看三个视图：

- `source_items`：确认抓到的原始内容是否来自目标账号，链接是否能打开。
- `event_candidates`：确认哪些内容被识别成活动，证据是否可信。
- `draft_payloads`：确认准备写入系统的字段是否可用。

出现问题时再看：

- `gate_results`：定位为什么被拦截或为什么误放行。
- `errors`：定位采集器、登录态或 API 问题。
- `dictionary_resolution`：修正城市、场馆、场地 ID。

## Hermes 实现要求

- Hermes 应支持把 artifact 同步到飞书多维表格。
- 飞书写入失败不能影响 artifact 保存，但必须写入 `errors`。
- 表格行需要幂等 upsert，唯一键建议为 `run_id + entity_id + stage`。
- 长文本和 raw JSON 保存在 artifact，飞书只写摘要和 artifact 链接。
- 人工在飞书里的反馈必须被 Hermes 定期读取，转成 `feedback_events` artifact。
- 反馈读取后不得覆盖原始 artifact，只追加新反馈事件。
