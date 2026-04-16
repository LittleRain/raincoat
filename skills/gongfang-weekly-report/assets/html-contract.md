# HTML 输出合同

## 结构合同

单文件 `report.html`，结构固定：

```
page
├── hero (报告标题 + 周期信息)
├── nav (锚点式 sticky 导航)
├── section#s1 — 核心数据趋势
├── section#s2 — GMV 拆解
├── section#s3 — 流量拆解
└── footnote (数据说明)
```

### 固定栏目（禁止增删或调序）

| section_id | 标题 | 数据合同 |
|------------|------|----------|
| s1 | 核心数据趋势 | 整体数据 |
| s2 | GMV 拆解 | 行业数据 + 行业商品明细数据 + 商家销售明细 |
| s3 | 流量拆解 | 内容渠道数据 + 资源位二级入口数据 |

## 样式合同

- 必须在 `<style>` 中内联 `base-report.css` 的**完整内容**
- 使用 base-report.css 中定义的标准 CSS class（参见下方组件映射）
- 设计基于 Linear（暗色分层）+ Stripe（数据精度）混合体系
- 禁止自行发明 CSS class 或变量替代标准组件
- 禁止使用 `<link>` 加载外部样式

### 组件到 HTML 映射

| 组件 | CSS class | HTML 结构 |
|------|-----------|-----------|
| 报告头 | `.hero` `.hero-eyebrow` `.hero-meta` `.hero-badge` | `<header class="hero">` |
| 导航 | `.nav` `.nav a` `.active` | `<nav class="nav">` |
| 栏目 | `.section` `.section-head` `.section-num` `.section-desc` | `<section class="section">` |
| 指标卡 | `.metric-grid` `.metric-card` `.metric-label` `.metric-value` `.metric-sub` `.delta` | `<div class="metric-grid">` |
| 指标卡色条 | `.metric-card.green/.red/.amber/.blue` | 顶部 3px 色条 |
| 图表容器 | `.chart-container` `.chart-area` `.chart-area-sm` `.chart-area-lg` | `<div class="chart-container">` |
| 表格 | `.table-wrap` `table` `th.num` `td.num` `.tag` `.tag-up` `.tag-down` | `<div class="table-wrap">` |
| 结论 | `.conclusion` `.hl` | `<div class="conclusion">` |
| 拆解块 | `.breakdown-block` `.breakdown-head` | `<div class="breakdown-block">` |
| 数据说明 | `.footnote` | `<div class="footnote">` |
| 网格 | `.grid-2` `.grid-3` `.grid-4` | `<div class="grid-2">` |
| 环比文本 | `.delta.up` `.delta.down` `.delta.neutral` | `<span class="delta up">` |
| 面板 | `.panel` | `<div class="panel">` |

## 图表合同

- Chart.js 4.x 必须内联到 HTML（禁止 CDN）
- `chart-defaults.js` 必须在 Chart.js 之后内联
- 使用标准 API：
  - `reportChart(canvasId, config)` — 挂载图表
  - `chartPresets.line(labels, datasets, { yFormat })` — 折线图
  - `chartPresets.bar(labels, datasets, { stacked })` — 柱状图
  - `chartPresets.doughnut(labels, data)` — 环形图
  - `chartPresets.combo(labels, datasets, { yFormat, y1Format })` — 双轴组合图
  - `REPORT_FORMAT.gmv(v)` / `.pv(v)` / `.pct(v)` / `.num(v)` / `.auto(name, v)` — 格式化
  - `REPORT_WOW(current, previous)` — 环比计算 → `{ text, cls, value }`
  - `reportHTML.metricCard(label, value, wow, color)` — 指标卡 HTML
  - `reportHTML.wowTag(wow)` — 环比标签 HTML
  - `REPORT_PALETTE` — 10 色数组

### 双轴组合图规范（本报告最常用）

| 元素 | 规则 |
|------|------|
| 左轴 (y) | 柱状图，展示绝对值（GMV、PV） |
| 右轴 (y1) | 折线图，展示比率（占比%） |
| 右轴网格线 | 隐藏 (`drawOnChartArea: false`) |
| 柱状图颜色 | PALETTE 前段色（indigo, emerald...），70% 不透明度 |
| 折线颜色 | 对比色（amber `#fbbf24`, pink `#f472b6`, cyan `#22d3ee`） |
| 渲染层级 | 折线在柱状图之上 (`order: 0` vs `order: 1`) |
| Tooltip | `mode: 'index'`，同时显示所有系列 |
| 右轴标签 | 默认带 % 后缀 |

## 数据合同

### 周次列（"周五-周四周"）
数据已是**周粒度聚合**，列值为周数（如 11、12、13），无需二次聚合。

### 6 份数据文件

| 文件模式 | 关键维度 | 支撑栏目 |
|---------|---------|---------|
| 整体数据* | 周 | S1 |
| 行业数据* | 周 + 后台一级类目名称 | S2 |
| 行业商品明细数据* | 周 + 商品名称 + 店铺名称 + 后台一级类目名称 | S2 |
| 商家销售明细* | 周 + 后台一级类目名称 + 店铺名称 | S2 |
| 内容渠道数据* | 周 + 后台一级类目名称 + 内容类型 | S3 |
| 资源位二级入口数据* | 周 + 后台一级类目名称 + 内容类型 + 资源位二级入口 | S3 |

### 通用字段

所有文件共有：商品曝光PV、PVCTR、商详UV、支付订单数、支付订单买家数、GMV（不减退款）、商详支付转化率-UV、GPM

### 指标格式规则

| 类别 | 指标 | formatter | 示例 |
|------|------|-----------|------|
| 金额 | GMV | `REPORT_FORMAT.gmv` | ¥12.3万 |
| 人数 | 买家数 | `REPORT_FORMAT.num` | 3.4万 |
| 量级 | 曝光PV、订单数 | `REPORT_FORMAT.pv` | 8.2万 |
| 率值 | 转化率、PVCTR、占比 | `REPORT_FORMAT.pct` | 5.23% |
| 环比 | 所有 WoW | `REPORT_WOW` | +5.2% |

**强制规则**:
- 率值一律百分比，禁止展示小数形式（0.05 必须写成 5.00%）
- 环比带正负号 +5.2% / -3.1%，着色：正值 `.up` 绿、负值 `.down` 红、零 `.neutral` 灰
- 表格数值列右对齐 `.num`

### 表格单元格格式

每个指标列：`值 (环比%)`，环比着色 `.tag-up` / `.tag-down`，无数据显示 `-`
