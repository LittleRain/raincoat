---
name: gongfang-weekly-report
description: 读取工房交易周报所需的 Excel/CSV 数据文件并生成交互式 HTML 周报。使用标准化设计系统（base-report.css + chart-defaults.js），输出暗色主题、数据精度优先的交互式报告。
---

# Gongfang Weekly Report

## 目的

根据 skill 内置的业务口径和栏目合同，读取指定数据文件，生成最终交互式 HTML 周报。

这个 skill 的定位是"执行工房周报生成"，不是"重新定义口径"或"补需求"。

## 输入

- 一个输入目录，目录中放置本次周报所需 6 个 Excel 或 CSV 文件

**必需文件（6个）：**
- `整体数据*` — 全局汇总数据
- `行业数据*` — 按行业聚合
- `行业商品明细数据*` — 商品级明细，含本周+上周
- `内容渠道数据*` — 按内容渠道（商品/视频/动态/直播）聚合
- `商家销售明细*` — 商家级销售明细（注意：文件名无"数据"后缀）
- `资源位二级入口数据*` — 按资源位二级入口聚合

输入文件命名参考：
[input_inventory.md](./examples/input_inventory.md)

## 工作流

1. 读取 skill 内置的栏目合同、输入合同和行业口径
2. 扫描输入目录中的 Excel 或 CSV 文件
3. 按文件名模式匹配 6 个数据文件
4. 按内置的行业口径和阈值完成聚合、归因与渠道占比分析
5. 按固定栏目顺序生成交互式 HTML
6. 输出 `report.html` 和执行日志

## 输出

- 主产物：`report.html`
- 辅助产物：`run.log`

## 设计系统

本 skill 使用 `create-report` 标准化设计系统：

- **CSS**: `base-report.css` — Linear 暗色分层 + Stripe 数据精度混合体系
- **Chart**: `chart-defaults.js` — Chart.js 4.x 标准配置
- **组件**: `.hero` / `.nav` / `.section` / `.metric-card` / `.chart-container` / `.conclusion` / `.footnote`
- **图表 API**: `chartPresets.combo` / `.line` / `.bar` + `REPORT_FORMAT` + `REPORT_WOW`

### 指标格式规则

| 类别 | 指标 | formatter |
|------|------|-----------|
| 金额 | GMV、GPM | `REPORT_FORMAT.gmv` (¥12.3万) |
| 人数 | 买家数 | `REPORT_FORMAT.num` (3.4万) |
| 量级 | 曝光PV、订单数 | `REPORT_FORMAT.pv` (8.2万) |
| 率值 | 转化率、PVCTR | `REPORT_FORMAT.pct` (5.23%) |
| 环比 | 所有 WoW | `REPORT_WOW` (+5.2%) |

## 约束

- 禁止修改 skill 中定义的栏目顺序和核心行业口径
- 禁止推断未声明的指标公式或归因逻辑
- 禁止输出非 HTML 格式作为主产物
- 缺少关键输入文件时，应明确报错，而不是伪造结果
- 禁止使用 CDN 加载 Chart.js（必须内联）
- 禁止自行发明 CSS class 替代 base-report.css 标准组件
- 禁止使用 `<link>` 加载外部 CSS
- 率值类指标必须用百分比展示，禁止小数形式
- 环比变化必须带正负号，使用语义着色（上涨绿、下跌红）

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

- 输入清单：[input_inventory.md](./examples/input_inventory.md)
- HTML 结构要求：[html-contract.md](./assets/html-contract.md)
- 周报栏目结构：[report-outline.md](./assets/report-outline.md)
- 生成 Prompt：[report-prompt.md](./assets/report-prompt.md)
- 校验清单：[validation-checklist.md](./assets/validation-checklist.md)
- 骨架 HTML 示例：[output-outline.html](./examples/output-outline.html)
