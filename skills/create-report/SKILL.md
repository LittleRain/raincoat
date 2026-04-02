---
name: create-report
description: 当需要从业务周报需求文档创建、更新或校验一个下游 HTML 周报 skill 时使用。适用于把半结构化周报需求整理成标准化 spec，判断应生成 documentation-only 还是 runnable skill，校验真实样本数据是否足以支撑执行，并输出可复用的 report-domain skill 包。
---

# Create Report

## 目的

为公司内部团队生成稳定可复用的周报 skill。

这个 skill 会读取业务方提供的半结构化周报需求材料，先整理出标准化
spec，再执行校验，最后生成或更新一个下游 `report-<domain>` skill 包。

## 何时使用

- 团队已经有周报需求文档，但还没有稳定 skill
- 周报需求需要先被澄清和结构化
- 最终周报输出必须是 HTML
- 目标是创建或更新一个可复用的下游周报 skill

## 输入

- 一份原始周报需求 markdown
- 可选附件或附件说明
- `docs/skills/report-creator/` 目录下的产品文档和规范文档（按需读取，不全量加载）

## 工作流

1. 读取原始需求并抽取已知业务事实
2. 只读取 `spec.md` 与 `operating-model.md`，按标准 spec 合同重组需求
3. 判断本次目标是 `documentation-only` 还是 `runnable` 下游 skill
4. 识别缺失字段、缺失样本和阻塞冲突
5. 若未通过门槛，则输出缺口报告并停止
6. 若通过门槛，则校验标准化 spec
7. 优先执行 `scripts/create-report-skill.sh` 生成下游 skill 骨架，再做定向补充
8. 若目标是 `runnable`，必须补齐真实执行脚本、依赖和最小回归测试
9. 检查生成后的 skill 包是否具备必需文件、资产和对应级别的验证证据
10. 若首次生成结果不符合预期，输出定向调整建议，而不是建议整体重做

## 低 Token 执行模式

- 禁止一次性读取 `docs/skills/report-creator/` 全目录
- 默认只读：
  - `docs/skills/report-creator/spec.md`
  - `docs/skills/report-creator/operating-model.md`
- 仅在以下场景追加读取：
  - 需要发布门槛细节时：`validation.md`
  - 需要产品背景或范围边界时：`prd.md`
  - 需要对照历史案例时：`examples/*`
- 下游 skill 的 `examples/normalized-spec.md` 应使用“引用 + 摘要”，不要粘贴完整长 spec

## 约束

- 禁止直接从原始业务 prose 生成下游 skill
- 禁止猜测指标定义、分类口径或图表字段
- 禁止生成非 HTML 的下游输出合同
- 栏目与数据映射不完整时，禁止继续
- 若未提供最小真实样本数据，禁止把下游 skill 标记或表述为 `runnable`
- 若声明 `runnable`，禁止只生成 placeholder HTML、占位脚本或仅文档型骨架
- 表格 schema、结论 schema、关键指标的 WoW 展示方式未明确时，禁止擅自发明输出细节
- 当生成结果偏离预期时，应优先定位偏差层级，再做定向修正

## 参考资料

- [Spec 合同](/Users/raincai/Documents/GitHub/raincoat/docs/skills/report-creator/spec.md)
- [运行模型](/Users/raincai/Documents/GitHub/raincoat/docs/skills/report-creator/operating-model.md)
- [文档索引](/Users/raincai/Documents/GitHub/raincoat/docs/skills/report-creator/README.md)
