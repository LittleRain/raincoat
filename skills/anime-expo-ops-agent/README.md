# 漫展运营 Agent

这个技能定义由 Hermes 运行的漫展行业运营 Agent 所需的业务规则、数据契约、提示词、工作流和评估标准。适用场景是：你运营一个服务线下漫展的线上平台，平台同时有内容和交易，需要把行业信息转成结构化活动、业务诊断和可执行运营动作。

Hermes 应把这个目录视为业务逻辑的源头。运行时调度、连接器、密钥、审批界面、API 适配器留在 Hermes 内部。

## 主要输出

- 每日行业情报
- 结构化活动候选
- 待审批活动草稿 payload
- 业务指标诊断
- 带证据的运营动作建议

## 核心设计判断

第一版不是做“全自动员工”，而是做“运营副驾驶”。Hermes 负责把行业信息、平台活动、业务指标组织成可审核的动作建议；高风险动作必须由你确认。

更准确地说，这个 Agent 要按 harness 思路设计：模型只是被调度的一个部件，外层必须有输入契约、工具边界、状态记录、质量门禁、人工审批、回放能力和评估集。不要让 prompt 直接变成生产系统。

目标闭环：

```text
行业信号 -> 活动候选 -> 字典解析 -> 查重 -> 未发布草稿 -> 审批 -> 业务指标 -> 动作建议 -> 反馈复盘
```

## Hermes 使用方式

1. 读取 `SKILL.md`。
2. 按 run type 读取对应 reference 文件。
3. 执行 Hermes 自己维护的连接器和工具。
4. 按 `references/data-model.md` 校验输出。
5. 对风险动作生成报告和审批任务，不直接自动执行。

## 关键文档

- 产品策略：`references/product-strategy.md`
- 系统设计：`references/system-design.md`
- Harness 设计原则：`references/harness-design.md`
- 实施计划：`references/implementation-plan.md`
- 数据模型：`references/data-model.md`
- 信息源配置：`references/source-config.md`
- Hermes 交接：`references/hermes-handoff.md`
