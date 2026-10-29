# 双周报生成 Prompt

## 目标

基于通过校验的标准化 spec，生成最终 HTML 双周报。

## 样式规则（必须遵守）

### CSS 框架
- 必须在 `<style>` 中内联 `base-report.css` 的完整内容
- 使用 base-report.css 中定义的标准 CSS class，禁止自行发明替代样式
- 设计基于 Linear（暗色分层）+ Stripe（数据精度）混合体系

### 可用组件 class 速查

| 组件 | CSS class | 用途 |
|------|-----------|------|
| 报告头 | `.hero` `.hero-eyebrow` `.hero-meta` `.hero-badge` | 标题区+周期信息 |
| 导航 | `.nav` `.nav a` `.active` | 锚点式 sticky 导航 |
| 栏目 | `.section` `.section-head` `.section-num` `.section-desc` | 分栏 |
| 指标卡 | `.metric-grid` `.metric-card` `.metric-label` `.metric-value` `.metric-sub` `.delta` | KPI 展示 |
| 指标色 | `.metric-card.green/.red/.amber/.blue` | 顶部色条 |
| 网格 | `.grid-2` `.grid-3` `.grid-4` | 列布局 |
| 卡片 | `.card` `.card-title` | 通用容器 |
| 面板 | `.panel` | 带左色条标题的面板 |
| 图表 | `.chart-container` `.chart-area` `.chart-area-sm` `.chart-area-lg` `.pie-area` | 图表容器 |
| 表格 | `.table-wrap` `table` `.num` `.sub-row` | 数据表 |
| 环比标记 | `.tag` `.tag-up` `.tag-down` `.tag-warn` | 表格内环比 |
| 环比文本 | `.delta.up` `.delta.down` `.delta.neutral` | 行内环比 |
| 结论 | `.conclusion` `.hl` | 结论框 |
| 拆解 | `.breakdown-block` `.breakdown-head` | 行业/渠道拆解 |
| 数据说明 | `.footnote` | 底部注释 |
| 颜色文本 | `.text-up` `.text-down` `.text-warn` `.text-muted` `.text-dim` | 语义着色 |

## 图表规则

### 图表运行时
- Chart.js 4.x 必须内联到 HTML（禁止 CDN）
- `chart-defaults.js` 必须在 Chart.js 之后内联
- 使用标准 API：
  - `reportChart(canvasId, config)` — 挂载图表
  - `chartPresets.line(labels, datasets, { yFormat })` — 折线图
  - `chartPresets.bar(labels, datasets, { stacked })` — 柱状图
  - `chartPresets.doughnut(labels, data)` — 环形图
  - `chartPresets.combo(labels, datasets, { yFormat, y1Format })` — 双轴组合图
  - `REPORT_FORMAT.gmv(v)` / `.pv(v)` / `.pct(v)` / `.num(v)` / `.auto(name, v)` — 格式化
  - `REPORT_WOW(current, previous)` — 环比 `{ text, cls, value }`
  - `reportHTML.metricCard(label, value, wow, color)` — 指标卡 HTML
  - `reportHTML.wowTag(wow)` — 环比标签 HTML
  - `REPORT_PALETTE` — 10 色数组

### 双轴组合图规范（本报告最常用）
- 左轴（y）= 柱状图 → 绝对值（PV、GMV）
- 右轴（y1）= 折线图 → 比率（占比%）
- 右轴网格线隐藏
- 折线颜色必须与柱状图颜色对比明显
- 折线渲染在柱状图之上
- Tooltip 使用 index 模式
- 右轴标签带 % 后缀

## 数据规则

- 严格按照标准化 spec 中的栏目顺序输出（S1 → S2 → S3）
- 只使用 spec 中声明过的指标、维度和数据合同
- 对绘画与 VUP周边分别生成独立分析块
- 对环比变化未超过 5% 的指标，不要强行给出异常解释
- 商品归因只允许引用行业商品明细数据中的曝光、转化、买家、GMV 等已声明字段
- 重点商品影响结论必须明确写出上涨、下跌或持平，不能只写"变化"
- 渠道占比分析只允许基于内容渠道数据中的占比和绝对值变化
- 缺少关键文件时阻塞输出，而不是猜测
- 若同一栏目映射到多份数据合同，必须按 spec 声明的主/备优先级取数
- 每条结论都要有数据依据

## 通用指标展示标准

- **率值类**（转化率、PVCTR、占比）→ 一律用百分比 `REPORT_FORMAT.pct`，如 5.23%
- **数值类**（买家数、订单数）→ 一律用数值 `REPORT_FORMAT.num` 或 `.pv`
- **金额类**（GMV）→ 带 ¥ 前缀 `REPORT_FORMAT.gmv`
- 禁止将转化率展示为小数（如 0.05），必须写成百分比（如 5.00%）
- `REPORT_FORMAT.pct` 会自动检测小数形式率值（<1 时自动 ×100），如 0.0475 → 4.75%
- GPM 是千次展示 GMV（非百分比），应使用 `REPORT_FORMAT.gmv` 或自定义格式，不要用 `pct`
- 环比变化必须带正负号（+5.2%、-3.1%），使用 `.delta.up` / `.delta.down` 着色
- 不确定类型时使用 `REPORT_FORMAT.auto(metricName, value)` 自动识别

## 指标卡颜色约定

| 指标类型 | 色条 | class |
|----------|------|-------|
| 金额（GMV） | 默认(accent) | `.metric-card` |
| 人数（买家数） | 绿色 | `.metric-card.green` |
| 量级（曝光PV、订单数） | 蓝色 | `.metric-card.blue` |
| 率值（转化率、PVCTR） | 黄色 | `.metric-card.amber` |

## 输出

- 最终格式：`html`
- 必须包含：标题区（.hero）、导航（.nav）、栏目正文（.section）、数据说明区（.footnote）
- `file://` 直接打开必须可见图表
