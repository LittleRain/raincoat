# Create Report

一个面向公司内部的上游周报生产器 skill，用来把半结构化周报需求转成
稳定的下游周报 skill。

## 它做什么

`create-report` 是周报生成链路的上游层。它读取业务方材料，生成标准化
spec，对 spec 执行校验，然后输出一个可复用的下游 `report-<domain>`
skill 包。下游 skill 的最终目标输出是 HTML 周报。

这个 skill 默认按保守策略工作。字段不全或规则冲突时，它应该阻塞而不是
生成一个看起来完整、实际上不可用的结果。

此外，`create-report` 不只负责“首次生成”，也负责后续的定向调整闭环：

- 记录首次生成与业务预期之间的偏差
- 判断偏差属于需求、spec、模板还是下游 skill
- 只修改必要层级
- 把可复用修正回写到生成器模板和验证规则

## 目录结构

- `SKILL.md`
  - 面向 agent 的工作流说明
- `skill.json`
  - skill 元数据
- `assets/`
  - 标准化、缺口报告、下游 skill 生成与调整所需模板
- `examples/`
  - 圈子业务周报黄金样例
- `scripts/`
  - 用于生成下游周报 skill 包的辅助脚本

## 当前状态

当前状态：`draft`

首个已落地黄金样例是“圈子业务周报”，其完整链路文档位于
`docs/skills/report-creator/examples/`。
