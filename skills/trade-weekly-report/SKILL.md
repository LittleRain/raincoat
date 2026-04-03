---
name: trade-weekly-report
description: 按照交易业务周报合同，读取指定 Excel/CSV 数据文件并生成交互式周报 HTML。适用于已经准备好整体、行业、流量、体裁及可选明细文件，需要产出完整交易业务周报的场景。
---

# Trade Weekly Report

## 目的

根据 skill 内置的业务口径、栏目合同和输入合同，读取指定数据文件，生成最终交互式 HTML 周报。

这个 skill 的定位是“执行交易业务周报生成”，不是“补需求”或“重定义分析口径”。

## 输入

- 一个输入目录，目录中放置本次周报所需 Excel 或 CSV 文件
- 输入文件命名与字段要求见：
  [input_inventory.md](./examples/input_inventory.md)

## 工作流

1. 读取 skill 内置的栏目合同、输入合同和行业分类口径
2. 扫描输入目录中的 Excel 或 CSV 文件
3. 按文件名模式匹配整体、行业、流量、体裁、可选明细和头部 UP 文件
4. 基于周五到周四的周口径完成聚合、分类和归因分析
5. 按固定栏目顺序生成交互式 HTML
6. 输出 `report.html` 和执行日志

## 输出

- 主产物：`report.html`
- 辅助产物：`run.log`

## 约束

- 禁止修改 skill 中定义的栏目顺序和核心行业口径
- 禁止推断未声明的指标公式或归因逻辑
- 禁止输出非 HTML 格式作为主产物
- 缺少核心输入文件时，应明确报错或降级，而不是伪造结果

## 执行方式

### 方式 1：作为脚本执行

```bash
bash skills/trade-weekly-report/scripts/run-report.sh \
  --input-dir /path/to/input \
  --output-dir /path/to/output \
  --run-id trade-weekly-2026w14
```

### 方式 2：作为 agent skill 调用

调用这个 skill 时，应明确要求：

- 按 trade-weekly-report 的内置合同生成周报
- 输入数据来自指定目录中的 Excel/CSV
- 最终输出一个 `report.html`

## 参考资料

- [input_inventory.md](./examples/input_inventory.md)
- [html-contract.md](./assets/html-contract.md)
- [report-outline.md](./assets/report-outline.md)
