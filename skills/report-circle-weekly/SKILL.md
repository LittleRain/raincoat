---
name: report-circle-weekly
description: 按照圈子业务周报需求文档，读取指定 Excel/CSV 数据文件并生成周报 HTML。
---

# Report Circle Weekly

## 目的

根据
[圈子业务周报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/圈子业务周报需求.md)
中定义的业务口径、栏目结构和输出要求，读取指定数据文件，生成最终周报
HTML。

这个 skill 的定位是“执行周报生成”，不是“澄清需求”或“重新设计周报结构”。

## 何时使用

- 已经明确采用
  [圈子业务周报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/圈子业务周报需求.md)
  作为业务需求基准
- 手上已经有本周对应的 Excel 或 CSV 数据文件
- 需要产出一份可直接打开的周报 HTML

## 输入

- 业务需求文档：
  [圈子业务周报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/圈子业务周报需求.md)
- 一个输入目录，目录中放置本次周报所需 Excel 或 CSV 文件
- 可选附件：
  - `头部UPlist.*`

输入文件命名参考：
[input_inventory.md](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-weekly/examples/input_inventory.md)

## 工作流

1. 读取业务需求文档，确认本次周报固定按该文档执行
2. 扫描输入目录中的 Excel 或 CSV 文件
3. 按文件名模式匹配整体数据、行业数据、流量数据、体裁数据及可选附件
4. 按需求文档中的口径完成聚合、分类和归因分析
5. 按需求文档中的栏目顺序生成完整 HTML
6. 输出 `report.html` 和执行日志

## 输出

- 主产物：`report.html`
- 辅助产物：`run.log`

## 约束

- 禁止修改
  [圈子业务周报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/圈子业务周报需求.md)
  中定义的栏目顺序和核心口径
- 禁止在没有数据支持时补充额外归因
- 禁止输出非 HTML 格式作为主产物
- 缺少关键输入文件时，应明确报错或降级，而不是伪造结果

## 执行方式

### 方式 1：作为脚本执行

```bash
bash skills/report-circle-weekly/scripts/run-report.sh \
  --input-dir /path/to/input \
  --output-dir /path/to/output \
  --run-id circle-weekly-2026w12
```

### 方式 2：作为 agent skill 调用

调用这个 skill 时，应明确要求：

- 按业务需求文档生成周报
- 输入数据来自指定目录中的 Excel/CSV
- 最终输出一个 `report.html`

## 参考资料

- 业务需求：
  [圈子业务周报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/圈子业务周报需求.md)
- 输入清单：
  [input_inventory.md](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-weekly/examples/input_inventory.md)
- HTML 结构要求：
  [html-contract.md](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-weekly/assets/html-contract.md)
- 周报栏目结构：
  [report-outline.md](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-weekly/assets/report-outline.md)
