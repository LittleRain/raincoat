# 下游周报 Prompt 模板

## 目标

基于通过校验的标准化 spec，生成最终 HTML 周报。

## 样式规则（必须遵守）

### CSS 框架
- 必须在 `<style>` 中内联 `create-report/assets/base-report.css` 的完整内容
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

### 图表运行时
- Chart.js 4.x 必须内联到 HTML（禁止 CDN）
- `chart-defaults.js` 必须在 Chart.js 之后内联
- 使用标准 API：
  - `reportChart(canvasId, config)` — 挂载图表
  - `chartPresets.line(labels, datasets, { yFormat: 'gmv' })` — 折线图
  - `chartPresets.bar(labels, datasets, { stacked: true })` — 柱状图
  - `chartPresets.doughnut(labels, data)` — 环形图
  - `chartPresets.combo(labels, datasets, { yFormat: 'pv', y1Format: 'pct' })` — 双轴组合图
  - `REPORT_FORMAT.gmv(v)` / `.pv(v)` / `.pct(v)` / `.num(v)` / `.auto(name, v)` — 格式化
  - `REPORT_WOW(current, previous)` — 环比 `{ text, cls, value }`
  - `reportHTML.metricCard(label, value, wow, color)` — 指标卡 HTML
  - `reportHTML.wowTag(wow)` — 环比标签 HTML
  - `REPORT_PALETTE` — 10 色数组，用于多系列图表

### 通用指标展示标准
- **率值类**（转化率、CTR、占比）→ 一律用百分比 `REPORT_FORMAT.pct`，如 5.23%
- `REPORT_FORMAT.pct` 自动检测小数形式率值（<1 时自动 ×100），如 0.0475 → 4.75%
- **GPM** 是千次展示 GMV（非百分比），应使用 `REPORT_FORMAT.gmv` 或自定义格式
- **数值类**（DAU、买家数、订单数、PV、UV）→ 一律用数值 `REPORT_FORMAT.num` 或 `.pv`
- **金额类**（GMV、客单价）→ 带 ¥ 前缀 `REPORT_FORMAT.gmv`
- 禁止将转化率展示为小数（如 0.05），必须写成百分比（如 5.00%）
- 禁止将数值类指标写成百分比
- 环比变化必须带正负号（+5.2%、-3.1%），使用 `.delta.up` / `.delta.down` 着色
- 不确定类型时使用 `REPORT_FORMAT.auto(metricName, value)` 自动识别

### 双轴组合图规范
双轴图是周报最常见的图表类型，必须遵守以下规则：
- 左轴（y）= 柱状图，展示绝对值（PV、GMV、订单数）
- 右轴（y1）= 折线图，展示比率（占比%、转化率%）
- 右轴网格线必须隐藏
- 折线颜色必须与柱状图颜色有明显对比
- 折线渲染在柱状图之上
- Tooltip 使用 index 模式，同时展示所有系列
- 右轴标签默认带 % 后缀

## 数据规则

- 生成前必须读取下游 `skill-manifest.yaml`
- `L0` 只能输出文档、outline 或 gap report，禁止声称 runnable
- `L1` 必须有真实样本、真实 runner、真实 HTML、运行日志和验证证据
- `L2` 必须额外具备自包含依赖、`file://` 浏览器验证和回归测试证据
- 禁止声明高于证据支持的等级
- 严格按照标准化 spec 中的栏目顺序输出
- 只使用 spec 中声明过的指标、维度和数据合同
- 若同一栏目映射到多份数据合同，必须按 spec 声明的主/备优先级取数
- 对不具备支撑的数据分析要求，必须阻塞而不是猜测
- 每条结论都要有数据依据
- 若 spec 已声明表格 schema，必须严格按 schema 输出，不能临时改列
- 若 spec 已声明某些字段要展示 WoW，必须逐列展示
- 若 spec 已声明比率指标回退规则（如 CTR），必须按主口径与回退口径执行，不能擅自改公式
- 若 spec 已声明"全空周期列隐藏"，则表格中全空周期列不得渲染
- 若 spec 已声明 narrative schema，必须显式写出上涨 / 下跌 / 持平，不能只写"变化"
- 若 spec 已声明 runtime logging rules，必须输出文件匹配、读取状态、关键处理阶段日志
- 日志必须随处理过程实时输出，不能只在任务完成后一次性打印
- 若当前 skill 为 `L0`，不得把占位输出表述成可运行结果

## 输出

- 最终格式：`html`
- 必须包含：标题区（.hero）、导航（.nav）、栏目正文（.section）、数据说明区（.footnote）
- `file://` 直接打开必须可见图表
