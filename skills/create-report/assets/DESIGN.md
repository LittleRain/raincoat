# Report Design System

Weekly report HTML 的标准化设计系统。基于 Linear（暗色分层）+ Stripe（数据精度）混合。

## 设计原则

1. **暗色原生** — 亮度分层做层级（bg → surface → card → hover），不用阴影做主要层级区分
2. **数据精度** — 等宽数字 `tnum`，2px 精度间距，所有数值列自动对齐
3. **语义着色** — 上涨绿、下跌红、警告黄、信息蓝，一致且可预测
4. **组件化** — 标准 class 覆盖报告所有场景，禁止自行发明样式

## 色彩体系

### 背景层级（由深到浅）
| Token | Hex | 用途 |
|-------|-----|------|
| `--bg` | `#08090a` | 页面背景 |
| `--surface` | `#0f1011` | Hero、footnote |
| `--card` | `#191a1b` | 卡片、图表容器 |
| `--card-alt` | `#1e1f21` | 卡片悬浮态 |
| `--hover` | `#28282c` | 交互高亮 |

### 文字层级（由亮到暗）
| Token | Hex | 用途 |
|-------|-----|------|
| `--ink` | `#f7f8f8` | 标题、关键数值 |
| `--text-2` | `#d0d6e0` | 正文、结论 |
| `--text-3` | `#8a8f98` | 标签、说明 |
| `--text-4` | `#62666d` | 占位、禁用 |

### 语义色
| Token | Hex | 用途 |
|-------|-----|------|
| `--accent` | `#5e6ad2` | 品牌强调、导航激活 |
| `--up` | `#10b981` | 上涨、正向 |
| `--down` | `#f87171` | 下跌、负向 |
| `--warn` | `#fbbf24` | 警告 |
| `--info` | `#60a5fa` | 信息 |

### 图表调色板（10 色）
```
#5e6ad2  #10b981  #fbbf24  #a78bfa  #f472b6
#22d3ee  #f87171  #6366f1  #fb923c  #14b8a6
```

## 排版

- **字体**: PingFang SC, Noto Sans SC, system-ui
- **等宽**: SF Mono, Fira Code, ui-monospace
- **标题**: 28px/700, letter-spacing -0.5px
- **栏目标题**: 20px/700
- **正文**: 14px/400, line-height 1.5
- **标签**: 11px/600, uppercase, letter-spacing 0.8px
- **指标数值**: 26px/800, tnum
- **表格**: 13px, tnum 自动启用

## 间距系统

8px 基准网格 + 2px 精细步进：

```
2  4  6  8  10  12  14  16  20  24  32  40  48
```

使用 CSS 变量 `--sp-1` 到 `--sp-24`。

## 组件速查

### 页面结构
```html
<div class="page">
  <header class="hero">...</header>
  <nav class="nav">...</nav>
  <section class="section" id="s1">...</section>
  <div class="footnote">...</div>
</div>
```

### 指标卡
```html
<div class="metric-grid">
  <div class="metric-card green">
    <p class="metric-label">GMV</p>
    <p class="metric-value">¥12.3万</p>
    <p class="metric-sub"><span class="delta up">+5.2%</span></p>
  </div>
</div>
```
颜色: `.green` `.red` `.amber` `.blue` 或无（默认 accent）

### 图表
```html
<div class="chart-container">
  <figcaption>图表标题</figcaption>
  <div class="chart-area"><canvas id="c1"></canvas></div>
</div>
```
尺寸: `.chart-area` (280px) / `.chart-area-sm` (200px) / `.chart-area-lg` (360px)

### 双轴组合图（Combo Chart）

最常见的周报图表类型：左轴柱状图（绝对值）+ 右轴折线图（比率）。

**样式规范：**

| 元素 | 规则 |
|------|------|
| 左轴（y）| 柱状图，70% 不透明度填充，圆角 4px，无描边 |
| 右轴（y1）| 折线图，2px 实线，4px 圆点带白边，使用对比色 |
| 右轴网格 | 隐藏（`drawOnChartArea: false`），避免视觉噪音 |
| 右轴标签 | 默认带 % 后缀 |
| 柱状图颜色 | 取调色板前段色（indigo, emerald...） |
| 折线颜色 | 取对比色（amber `#fbbf24`, pink `#f472b6`, cyan `#22d3ee`） |
| 渲染层级 | 折线在柱状图之上（`order: 0` vs `order: 1`） |
| Tooltip | `mode: 'index'`，同时显示所有系列 |
| Tooltip 格式 | 左轴用 `yFormat`，右轴用 `y1Format` 自动格式化 |

**典型场景：**
- PV(柱) + 小店占比%(线): `{ yFormat: 'pv', y1Format: 'pct' }`
- GMV(柱) + 转化率%(线): `{ yFormat: 'gmv', y1Format: 'pct' }`
- 订单数(柱) + GPM(线): `{ yFormat: 'num', y1Format: 'gmv' }` 或业务明确声明的自定义 GPM formatter

**代码示例：**
```javascript
reportChart('c1', chartPresets.combo(weekLabels, [
  { label: '整体PV', data: totalPV, yAxisID: 'y' },
  { label: '小店PV', data: shopPV, yAxisID: 'y' },
  { type: 'line', label: '小店占比%', data: shopRatio, yAxisID: 'y1' }
], { yFormat: 'pv', y1Format: 'pct' }));
```

**禁止事项：**
- 禁止左右两轴都用柱状图（视觉混乱）
- 禁止右轴显示网格线
- 禁止折线和柱状图使用相同颜色
- 禁止右轴不标注百分比后缀

### 表格
```html
<div class="table-wrap">
  <table>
    <thead><tr><th>维度</th><th class="num">GMV</th><th class="num">WoW</th></tr></thead>
    <tbody>
      <tr><td>行业A</td><td class="num">¥12.3万</td><td><span class="tag tag-up">+5.2%</span></td></tr>
    </tbody>
  </table>
</div>
```

### 结论框
```html
<div class="conclusion">
  <h4>结论</h4>
  <ul>
    <li><span class="hl">GMV:</span> 小店 ¥12.3万 (+5.2%), 环比上涨。</li>
  </ul>
</div>
```

## 通用指标展示标准

周报中频繁出现的指标，按以下规则展示。下游 skill 禁止偏离。

### 指标分类与格式

| 类别 | 指标 | 格式 | 示例 | formatter |
|------|------|------|------|-----------|
| 金额 | GMV、客单价、ARPU | ¥ + 万/亿自动缩写 | ¥12.3万、¥1.05亿 | `REPORT_FORMAT.gmv` |
| 人数 | DAU、MAU、买家数、新客数 | 万自动缩写，无¥ | 3.4万、12,345 | `REPORT_FORMAT.num` |
| 量级 | 订单数、曝光数(PV)、点击数、UV | 万/亿自动缩写 | 8.2万、1.03亿 | `REPORT_FORMAT.pv` |
| 率值 | 下单转化率、点击转化率(CTR)、复购率 | 百分比，2位小数 | 5.23%、0.87% | `REPORT_FORMAT.pct` |
| 金额效率 | GPM（千次展示 GMV）、ARPU | ¥ + 万/亿自动缩写或业务自定义 | ¥12.3、¥1.05万 | `REPORT_FORMAT.gmv` 或显式自定义 |
| 环比 | 所有 WoW 变化 | 带符号百分比，1位小数 | +5.2%、-3.1% | `REPORT_WOW` |

### 强制规则

1. **率值类指标一律用百分比**，禁止展示小数形式（如 0.05 必须写成 5.00%）
2. **`REPORT_FORMAT.pct` 自动检测小数形式**：值 <1 时自动 ×100（0.0475 → 4.75%）
3. **GPM 是千次展示 GMV（非百分比）**，应使用 `REPORT_FORMAT.gmv` 或自定义格式
4. **数值类指标一律用数值**，禁止写成百分比
5. **金额类前缀 ¥**，其他数值类无前缀
6. **万/亿缩写自动触发**：≥10000 显示 x.x万，≥1亿 显示 x.xx亿
7. **表格中数值列右对齐**，使用 `.num` class
8. **环比变化必须带正负号**：+5.2%、-3.1%，零变化显示 0.0%
9. **环比着色**：正值 `.up`（绿），负值 `.down`（红），零值 `.neutral`（灰）

### 指标卡颜色约定

| 指标类型 | 推荐色条 | class |
|----------|----------|-------|
| 金额类（GMV、收入） | 默认(accent) | `.metric-card` |
| 人数类（DAU、买家） | 绿色 | `.metric-card.green` |
| 量级类（PV、订单） | 蓝色 | `.metric-card.blue` |
| 率值类（转化率、CTR） | 黄色 | `.metric-card.amber` |

### 指标名自动识别

`chart-defaults.js` 中的 `REPORT_FORMAT.auto(metricName, value)` 可根据指标名自动选择格式：
- 含「率」「CTR」「占比」→ `pct`
- 含「GMV」「GPM」「客单价」「金额」「收入」「营收」「ARPU」→ `gmv`
- 含「DAU」「MAU」「买家」「用户」「新客」「商家」→ `num`
- 含「PV」「UV」「曝光」「点击」「订单」「次数」→ `pv`
- 其他 → `num`（兜底）

## 响应式断点

- `900px`: 网格转单列，section-head 改为纵向
- `600px`: 指标卡转双列，导航紧凑化

## 禁止事项

- 禁止引入外部 CSS 框架（Bootstrap, Tailwind 等）
- 禁止使用 `<link>` 加载样式（必须内联）
- 禁止自行定义 CSS 变量替代 base-report.css 中的 token
- 禁止使用 CDN 加载 Chart.js
- 禁止发明不在本文档中的组件 class
