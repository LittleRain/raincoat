# Harness 设计原则

## 核心判断

这个系统不应该设计成“一个 Agent 自己思考并操作平台”。它应该设计成一个 harness：用确定性的外壳约束不确定的模型能力。

模型负责：

- 从非结构化内容中抽取候选信息。
- 在证据充分时做分类和解释。
- 基于业务指标生成建议草案。

Harness 负责：

- 输入归一化。
- schema 校验。
- 字典解析。
- 工具调用。
- 状态机。
- 权限控制。
- 审批。
- 日志。
- 回放。
- eval。

## 设计原则

### 1. Contract-first

每个 worker 都必须有固定输入、固定输出和失败格式。

禁止：

- worker 直接返回自然语言给下游使用。
- 工具调用前没有 schema 校验。
- 业务字段靠 prompt 临时约定。

要求：

- 所有关键对象使用 `data-model.md` 中的 schema。
- 所有工具写入前生成 dry-run artifact。
- 所有字段转换保留原始值、解析值、置信度和证据。

### 2. Model as proposer, system as decider

模型提出候选，不直接决定生产状态。

模型可以提出：

- 活动候选。
- 活动类型名称。
- 场馆/场地原始名称。
- 去重判断建议。
- 运营动作建议。

系统决定：

- 字典 id 解析。
- payload 是否满足硬性门槛。
- 是否允许调用写入接口。
- 是否进入人工审批。
- 是否记录失败样本。

### 3. Every run creates artifacts

每次运行必须产出可追踪 artifact。

最小 artifact 集：

- `run_manifest`
- `source_items`
- `event_candidates`
- `dictionary_resolution_results`
- `duplicate_match_results`
- `draft_payloads`
- `approval_tasks`
- `recommendations`
- `eval_samples`
- `errors`

这些 artifact 应能回答：

- 输入是什么。
- 模型输出了什么。
- 系统改写了什么。
- 哪一步失败。
- 谁审批了什么。
- 最终写入了什么。

### 4. Replay before automation

任何新 worker 或新规则进入自动执行前，必须先支持 replay。

Replay 输入：

- 历史 `source_item`
- 历史业务指标
- 固定版本的字典缓存
- 固定版本的 prompt
- 固定版本的 schema

Replay 输出：

- 与线上同格式的 artifacts
- 与 golden set 的差异报告
- 是否通过 gate

### 5. Gates, not vibes

每个阶段都需要门禁。

硬门禁：

- JSON schema 校验失败，停止。
- `type`、`provinceId`、`cityId` 为空，停止写入。
- `placeId` 不属于 `venueId`，停止写入。
- 高风险动作未审批，停止。

软门禁：

- 场馆/场地模糊匹配，进入人工审核。
- 时间待定，允许草稿但标记 `projectTimeStatus = 1`。
- 价格待定，允许草稿但标记 `priceStatus = 1`。
- 缺海报，允许草稿但标记缺素材。

### 6. Human feedback is training data

审批不是流程负担，是 Agent 变好的数据来源。当前没有历史样本，因此第一批 eval/golden set 应从 live dry-run 的人工反馈中积累。

每次人工操作都要记录：

- approved
- rejected
- edited
- reason
- corrected_fields
- final_payload
- observed_result

这些记录进入每周复盘，用于更新：

- prompt
- 字典解析规则
- 风险规则
- eval golden set
- Hermes connector

样本积累要求：

- 第 1 周至少沉淀 10 条反馈样本。
- 达到 30 条 golden samples 后，关键规则变更必须 replay。
- 没有 golden set 前，不开放自动发布、自动改价、预算类能力。

### 7. Rollout by capability flag

所有自动化能力都要用 capability flag 打开。

建议 flag：

- `can_collect_sources`
- `can_sync_dictionaries`
- `can_extract_candidates`
- `can_generate_payloads`
- `can_create_unpublished_drafts`
- `can_send_approval_tasks`
- `can_execute_low_risk_actions`

默认只打开读和 dry-run。写入能力必须在对应 eval 通过后打开。

## 推荐 harness 结构

```text
Run Scheduler
  -> Input Normalizer
  -> Artifact Store
  -> Worker Runner
  -> Schema Validator
  -> Gate Engine
  -> Tool Adapter
  -> Approval Queue
  -> Feedback Logger
  -> Replay Runner
  -> Eval Runner
```

## Worker 契约

每个 worker 都应遵守：

```json
{
  "run_id": "run_xxx",
  "worker": "event_extractor",
  "input_refs": [],
  "output_refs": [],
  "status": "success|partial|failed",
  "errors": [],
  "metrics": {},
  "created_at": "2026-04-20T08:00:00+08:00"
}
```

## 生产前检查

上线任何自动写入能力前，必须满足：

- 若目标是未发布草稿写入：至少 10 条 live feedback 样本无硬门禁误放行。
- 若目标是发布、改价、预算类动作：至少 30 条 golden samples replay 通过。
- 关键字段幻觉数为 0。
- `placeId` 跨场馆错误为 0。
- 重复活动误判率 <= 10%。
- 所有写入 payload 可追溯到 source evidence。
- 人工审批链路可用。
- 失败项进入死信队列或人工审核。
