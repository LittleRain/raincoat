# 圈子业务周报生成记录

## 目标

使用周报生产器 skill 与源需求文档
[交易业务周报需求文档.md](/Users/raincai/Documents/GitHub/squirrel/docs/交易业务周报需求文档.md)，
生成一个正式的下游周报 skill：
[report-circle-weekly](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-weekly)。

## 输入

- 原始业务需求 markdown
- `report-creator` 产品文档和 spec 文档
- 标准化 spec：
  [circle-weekly-normalized-spec.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/report-creator/examples/circle-weekly-normalized-spec.md)

## 流程

1. 读取原始需求文档
2. 将原始需求映射为标准化 spec
3. 校验：
   - 所有栏目都有数据合同支撑
   - 所有指标都已声明
   - 最终输出已明确为 HTML
4. 生成下游周报 skill 包
5. 接入历史 Python 生成器和 HTML 模板，补齐脚本执行能力
6. 用圈子业务域的实际结构补齐资产、样例和约束
7. 执行仓库级校验

## 输出

- 上游生产器 skill：
  [create-report](/Users/raincai/Documents/GitHub/raincoat/skills/create-report)
- 下游周报 skill：
  [report-circle-weekly](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-weekly)

## 验证

- `report-circle-weekly` 已包含 required files、assets、examples、scripts
- `report-circle-weekly/scripts/run-report.sh` 已支持
  `--input-dir --output-dir --run-id` contract
- `lint-skills.sh` 已通过
- 所有产品文档引用均已收敛到 `docs/skills/report-creator/`
