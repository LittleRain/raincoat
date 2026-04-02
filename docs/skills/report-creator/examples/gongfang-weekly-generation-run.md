# 工房业务交易双周报生成记录

## 目标

使用周报生产器 skill 与源需求文档
[工房业务交易双周报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/工房业务交易双周报需求.md)，
生成一个正式的下游周报 skill：
[gongfang-weekly-report](/Users/raincai/Documents/GitHub/raincoat/skills/gongfang-weekly-report)。

## 输入

- 原始业务需求 markdown
- `report-creator` 产品文档和 spec 文档
- 标准化 spec：
  [gongfang-weekly-normalized-spec.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/report-creator/examples/gongfang-weekly-normalized-spec.md)

## 流程

1. 读取原始需求文档
2. 将原始需求映射为标准化 spec
3. 校验：
   - 所有栏目都有数据合同支撑
   - 所有指标都已声明
   - 波动阈值与重点行业口径已明确
   - 最终输出已明确为 HTML
4. 运行 `create-report/scripts/create-report-skill.sh` 生成下游周报 skill 骨架
5. 用工房业务域的栏目、输入文件和执行约束补齐资产与样例
6. 补充最小脚本入口与依赖文件，满足下游 skill 检查清单

## 输出

- 上游生产器 skill：
  [create-report](/Users/raincai/Documents/GitHub/raincoat/skills/create-report)
- 下游周报 skill：
  [gongfang-weekly-report](/Users/raincai/Documents/GitHub/raincoat/skills/gongfang-weekly-report)

## 说明

- 原始需求未显式声明周报读者，当前按内部交易周报惯例补全为 owner、运营、分析同学
- 下游 skill 当前为 `draft`，以结构化执行合同为主，后续可继续补充真实渲染脚本
