---
name: report-circle-daily
description: 按照圈子业务日报需求文档，读取指定 CSV/Excel 数据并生成日报 HTML。
---

# Report Circle Daily

## 目的

根据业务需求文档中定义的分析课题、栏目结构和输出要求，读取昨日数据文件，生成每日分析 HTML 报告。

这个 skill 的定位是"执行日报生成"，不是"澄清需求"或"重新设计报告结构"。

## 何时使用

- 已经明确采用业务需求文档作为基准
- 手上已经有昨日对应的 CSV 或 Excel 数据文件
- 需要产出一份可直接打开的日报 HTML

## 输入

- 业务需求文档（见“参考资料”）
- 一个输入目录，目录中放置本次日报所需数据文件
- 标准化 spec 摘要：
  [normalized-spec-summary.md](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-daily/examples/normalized-spec-summary.md)

输入文件命名参考：
[input_inventory.md](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-daily/examples/input_inventory.md)

## 工作流

1. 读取业务需求文档，确认本次日报固定按该文档执行
2. 扫描输入目录中的 CSV 或 Excel 文件
3. 按文件名模式匹配绘画圈、模型圈、漫展圈 feed 数据及转化数据
4. 先生成“总览表”，按圈子/路径输出曝光、点击、CTR、互动率并给出场景级结论
5. 分别输出绘画圈、模型圈 Top10 内容表（按曝光排序），并补充副标题、发布时间、链接和数据化结论
6. 输出漫展圈双路径内容表（T3 与票务商详），比较两条路径的内容偏好差异
7. 输出漫展项目转化分析（Top 项目、漏斗承接率、代表性项目原因）
8. 按需求文档中的栏目顺序生成完整 HTML
9. 输出 `report.html` 和执行日志

## 输出

- 主产物：`report.html`
- 辅助产物：`run.log`

## 约束

- 禁止修改业务需求文档中定义的栏目顺序和核心分析课题
- 禁止在没有数据支持时补充额外归因或推测
- 禁止输出非 HTML 格式作为主产物
- 缺少关键输入文件时，应明确报错或降级，而不是伪造结果

## 执行方式

### 方式 1：作为脚本执行

```bash
bash skills/report-circle-daily/scripts/run-report.sh \
  --input-dir /path/to/input \
  --output-dir /path/to/output \
  --run-id circle-daily-2026-04-01
```

### 方式 2：作为 agent skill 调用

调用这个 skill 时，应明确要求：

- 按业务需求文档生成日报
- 输入数据来自指定目录中的 CSV/Excel
- 最终输出一个 `report.html`

## 参考资料

- 业务需求：
  [圈子业务日报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/圈子业务日报需求.md)
- 标准化 Spec：
  [normalized-spec.md](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-daily/examples/normalized-spec.md)
- 标准化 Spec 摘要：
  [normalized-spec-summary.md](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-daily/examples/normalized-spec-summary.md)
- 输入清单：
  [input_inventory.md](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-daily/examples/input_inventory.md)
- HTML 结构要求：
  [html-contract.md](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-daily/assets/html-contract.md)
- 报告栏目结构：
  [report-outline.md](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-daily/assets/report-outline.md)
