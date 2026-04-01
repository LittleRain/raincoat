# Report Creator

这个目录用于存放 `create-report` 周报生成器 skill 的产品文档、规格定义、
运行边界、验证规则，以及首个黄金样例的落地材料。

## 文档清单

- `prd.md`
  - 周报生成器 skill 的产品定义
- `spec.md`
  - 中间规格，也就是标准化周报 spec 的最小合同
- `operating-model.md`
  - 运行边界、阻塞条件、追问策略、失败回退
- `validation.md`
  - 验收规则、样例集、稳定性门槛

## 样例

- `examples/circle-weekly-normalized-spec.md`
  - 由 [圈子业务周报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/圈子业务周报需求.md)
    映射出的标准化 spec
- `examples/circle-weekly-generation-run.md`
  - 从原始需求到下游 skill 产物的完整生成记录
- `examples/circle-daily-generation-run.md`
  - 圈子业务日报从原始需求到下游 skill 的生成记录
- `examples/circle-daily-adjustment-retro.md`
  - 日报定向调整复盘（经验、坑位、回归策略）
