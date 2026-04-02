---
name: gongfang-weekly-report
description: 读取工房交易周报所需的 Excel/CSV 数据文件并生成交互式 HTML 周报。适用于已经确认输入文件结构、需要输出核心数据趋势、重点行业分析、渠道分布和商品影响结论的场景。
---

# Gongfang Weekly Report

## 目的

根据 skill 内置的业务口径和栏目合同，读取指定数据文件，生成最终交互式 HTML 周报。

这个 skill 的定位是“执行工房周报生成”，不是“重新定义口径”或“补需求”。

## 输入

- 一个输入目录，目录中放置本次周报所需 Excel 或 CSV 文件

输入文件命名参考：
[input_inventory.md](./examples/input_inventory.md)

## 工作流

1. 读取 skill 内置的栏目合同、输入合同和行业口径
2. 扫描输入目录中的 Excel 或 CSV 文件
3. 按文件名模式匹配整体数据、行业数据、行业商品明细数据、内容渠道数据
4. 按内置的行业口径和阈值完成聚合、归因与渠道占比分析
5. 按固定栏目顺序生成交互式 HTML
6. 输出 `report.html` 和执行日志

## 输出

- 主产物：`report.html`
- 辅助产物：`run.log`

## 约束

- 禁止修改 skill 中定义的栏目顺序和核心行业口径
- 禁止推断未声明的指标公式或归因逻辑
- 禁止输出非 HTML 格式作为主产物
- 缺少关键输入文件时，应明确报错，而不是伪造结果

## 执行方式

### 方式 1：作为脚本执行

```bash
bash skills/gongfang-weekly-report/scripts/run-report.sh \
  --input-dir /path/to/input \
  --output-dir /path/to/output \
  --run-id gongfang-weekly-2026w14
```

### 方式 2：作为 agent skill 调用

调用这个 skill 时，应明确要求：

- 按 skill 内置合同生成周报
- 输入数据来自指定目录中的 Excel/CSV
- 最终输出一个 `report.html`

## 参考资料

- 输入清单：
  [input_inventory.md](./examples/input_inventory.md)
- HTML 结构要求：
  [html-contract.md](./assets/html-contract.md)
- 周报栏目结构：
  [report-outline.md](./assets/report-outline.md)
