# 交易业务周报生成记录

## 目标

使用周报生产器 skill 与源需求文档
[交易业务周报需求文档.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/交易业务周报需求文档.md)，
生成一个正式的下游周报 skill：
[trade-weekly-report](/Users/raincai/Documents/GitHub/raincoat/skills/trade-weekly-report)。

## 输入

- 原始业务需求 markdown
- `report-creator` 产品文档和 spec 文档
- 标准化 spec：
  [trade-weekly-normalized-spec.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/report-creator/examples/trade-weekly-normalized-spec.md)
- 历史可运行脚本基础：
  `docs/周报生成器_v3/`

## 流程

1. 读取原始需求文档
2. 将原始需求映射为标准化 spec
3. 校验：
   - 五个栏目都有数据合同支撑
   - 关键比率口径已声明
   - 最终输出明确为 HTML
4. 用 `create-report/scripts/create-report-skill.sh` 生成下游周报 skill 骨架
5. 复用 `docs/周报生成器_v3` 的 Python 生成器和前端模板，补齐 runnable 执行链路
6. 补齐资产、样例、输入合同与 smoke test
7. 用 `docs/周报生成器_v3/docs` 中的真实样本数据执行一次验证

## 输出

- 上游生产器 skill：
  [create-report](/Users/raincai/Documents/GitHub/raincoat/skills/create-report)
- 下游周报 skill：
  [trade-weekly-report](/Users/raincai/Documents/GitHub/raincoat/skills/trade-weekly-report)

## 说明

- 当前下游 skill 目标级别为 `runnable`
- 读者未在原始需求中单独声明，按内部交易经营周报惯例补全为 owner、运营、分析同学
