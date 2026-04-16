# 周报栏目结构

## 页面骨架

```
page
├── hero        → 报告标题 + 周期 badge
├── nav         → 锚点导航（核心数据趋势 / GMV拆解 / 流量拆解）
├── section#s1  → 核心数据趋势
├── section#s2  → GMV 拆解
├── section#s3  → 流量拆解
└── footnote    → 数据说明
```

---

## S1: 核心数据趋势

**数据源**: 整体数据

**指标卡（4张）**:
- GMV（默认色条）— `REPORT_FORMAT.gmv` + 环比
- 买家数（绿色 `.green`）— `REPORT_FORMAT.num` + 环比
- 下单转化率（黄色 `.amber`）— `REPORT_FORMAT.pct` + 环比
- 商品曝光PV（蓝色 `.blue`）— `REPORT_FORMAT.pv` + 环比

**图表（2×2 网格 `.grid-2`）**:
1. GMV 周趋势 — `chartPresets.bar(weekLabels, [{label:'GMV',data:gmvArr}], {yFormat:'gmv'})`
2. 买家数 周趋势 — `chartPresets.bar(weekLabels, [{label:'买家数',data:buyerArr}], {yFormat:'num'})`
3. 下单转化率 周趋势 — `chartPresets.line(weekLabels, [{label:'转化率',data:cvrArr}], {yFormat:'pct'})`
4. 商品曝光PV 周趋势 — `chartPresets.line(weekLabels, [{label:'曝光PV',data:pvArr}], {yFormat:'pv'})`

**结论 (`.conclusion`)**:
- 列出环比波动 >5% 的指标（GMV、订单数、买家数、支付转化率）
- 每条须明确 上涨/下跌/持平 + 环比数值

---

## S2: GMV 拆解

**数据源**: 行业数据(主) + 商家销售明细 + 行业商品明细数据

### 行业趋势总览

**图表（2×2 网格 `.grid-2`）**:
1. GMV by行业 — `chartPresets.line` 多系列折线图，过去4周
2. 买家数 by行业 — 同上
3. 下单转化率 by行业 — 同上，`yFormat:'pct'`
4. 商品曝光PV by行业 — 同上，`yFormat:'pv'`

### 绘画+绘画周边 (`.breakdown-block`)

**指标卡（4张）**: GMV / 买家数 / 转化率 / 曝光PV + 环比

**表格1 — 重点商家 TOP5** (`.table-wrap`):

| 列名 | 本周 | 上周 | 环比 | 格式 |
|------|------|------|------|------|
| 店铺名称 | — | — | — | 文本 |
| GMV | ✓ | ✓ | ✓ | `gmv` |
| GMV占行业占比 | ✓ | — | — | `pct` |
| 买家数 | ✓ | ✓ | ✓ | `num` |
| 下单转化率 | ✓ | ✓ | ✓ | `pct` |
| 商品曝光PV | ✓ | ✓ | ✓ | `pv` |

排序: 本周 GMV 降序，取 TOP5

**表格2 — 重点商品 TOP10** (`.table-wrap`):

| 列名 | 本周 | 上周 | 环比 | 格式 |
|------|------|------|------|------|
| 商品名称 | — | — | — | 文本 |
| GMV | ✓ | ✓ | ✓ | `gmv` |
| 买家数 | ✓ | ✓ | ✓ | `num` |
| 下单转化率 | ✓ | ✓ | ✓ | `pct` |
| 商品曝光PV | ✓ | ✓ | ✓ | `pv` |

排序: 本周 GMV 降序，取 TOP10

**结论 (`.conclusion`)**:
- 环比波动 >5% 的指标
- 是否头部商家变化导致，结合 TOP10 商品分析（买家转化 or 商品流量角度）

### VUP周边 (`.breakdown-block`)

同绘画+绘画周边结构（指标卡 + TOP5 商家表 + TOP10 商品表 + 结论）

---

## S3: 流量拆解

**数据源**: 内容渠道数据(主) + 资源位二级入口数据

### 绘画+绘画周边 (`.breakdown-block`)

#### 内容渠道分析

**组合图表 ×2（`.grid-2`）** — 取 GMV Top2 内容渠道，每个渠道一组:
1. GMV(柱) + GMV占比%(线) — `chartPresets.combo(weekLabels, [...], {yFormat:'gmv', y1Format:'pct'})`
2. 曝光PV(柱) + 曝光PV占比%(线) — `chartPresets.combo(weekLabels, [...], {yFormat:'pv', y1Format:'pct'})`

**表格1 — 内容渠道汇总** (`.table-wrap`):

| 列名 | W1 | W2 | W3 | W4(本周) | 本周占比 | 格式 |
|------|----|----|----|---------|---------|----|
| 内容渠道 | — | — | — | — | — | 文本 |
| GMV | ✓ | ✓ | ✓ | ✓ | ✓ | `gmv` + `pct` |
| 商品曝光PV | ✓ | ✓ | ✓ | ✓ | ✓ | `pv` + `pct` |
| PVCTR | ✓ | ✓ | ✓ | ✓ | — | `pct` |

#### 资源位二级入口分析

**组合图表 ×2（`.grid-2`）** — 取 GMV Top4 资源位二级入口，每个入口一组:
1. GMV(柱) + GMV占比%(线) — `chartPresets.combo`
2. 曝光PV(柱) + 曝光PV占比%(线) — `chartPresets.combo`

**表格2 — 资源位二级入口汇总** (`.table-wrap`):
结构同内容渠道汇总表

**结论 (`.conclusion`)**:
- GMV 环比 >5% 的内容渠道/资源位二级入口
- 从流量曝光、流量转化率、卖家转化率角度归因

### VUP周边 (`.breakdown-block`)

同绘画+绘画周边结构

---

## 关键约定

1. 每个表格的数值列添加 `.num` class 右对齐
2. 环比标签使用 `.tag.tag-up` / `.tag.tag-down` 着色
3. 仅解释环比波动 >5% 的指标
4. 率值一律用百分比展示（禁止小数形式）
5. 金额类带 ¥ 前缀
6. 所有结论必须明确写出 上涨/下跌/持平，禁止只写"变化"
