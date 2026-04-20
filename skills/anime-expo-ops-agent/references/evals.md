# 评估

## Harness 评估原则

评估不是事后看报告，而是自动化能力上线前的门禁。每个 worker 都必须支持 replay，并能对同一批 golden samples 输出差异报告。当前没有历史样本，因此 v0.1 不阻塞启动；先用 live dry-run 和人工反馈积累样本。

所有 eval 结果必须记录：

- `run_id`
- `worker`
- `input_sample_id`
- `expected_output`
- `actual_output`
- `diff`
- `pass`
- `failure_reason`

## 抽取评估

每周从 live dry-run 结果和人工反馈中抽样。第 1 周至少沉淀 10 条反馈样本；golden set 达到 30 条后，再要求关键规则变更必须 replay。

目标：

- 活动识别 precision >= 80%。
- 官方来源日期准确率 >= 90%。
- 幻觉必填字段 = 0。

## 字典解析评估

每周抽样检查：

- 省市区解析准确率。
- 场馆解析准确率。
- 场地解析准确率。
- 模糊匹配误选率。

目标：

- `type`、`provinceId`、`cityId` 错误写入次数为 0。
- `placeId` 不得跨 `venueId` 使用。
- 场馆/场地模糊时必须进入人工审核。

## Gate 评估

每周统计 gate 阻断原因：

- schema 校验失败。
- 缺 evidence。
- 字典解析失败。
- 疑似重复。
- capability 未开启。
- 审批缺失。

目标：

- 硬门禁误放行 = 0。
- 中高风险未审批执行 = 0。
- schema gate 阻断项 100% 有错误原因。

## Golden Set

当前没有历史样本，因此第一批 golden set 从你的人工反馈中逐步积累。

启动策略：

- 第 1 周用 live dry-run 输出积累样本。
- 每次人工确认、拒绝、编辑都必须转成 eval sample。
- 每周从反馈中沉淀至少 10 条样本进入 golden set。
- golden set 达到 30 条后，所有关键规则变更都必须 replay。

最终第一批 golden set 至少包含 30 条样本：

- 10 条官方活动公告。
- 10 条用户讨论或搬运内容。
- 5 条容易误判的非活动内容。
- 5 条重复或相似活动。

每条样本至少标注：

- 是否应识别为活动。
- 活动名称。
- 活动类型。
- 省市区。
- 场馆/场地。
- 开始/结束时间。
- 是否应创建草稿。

## 反馈驱动样本

每条反馈样本必须记录：

- `source_item_id`
- 原始内容链接或文本摘要
- Agent 原始输出
- 运营人员修改后的正确输出
- 反馈类型：`approved`、`rejected`、`edited`
- 拒绝或修改原因
- 应更新的位置：`prompt`、`schema`、`dictionary_rule`、`source_connector`、`gate`
- 是否加入 golden set

反馈标签：

- `not_an_event`
- `wrong_event_type`
- `wrong_city`
- `wrong_district`
- `wrong_venue`
- `wrong_place`
- `wrong_date`
- `wrong_price`
- `duplicate_missed`
- `duplicate_false_positive`
- `missing_required_field`
- `hallucinated_field`
- `low_value_recommendation`
