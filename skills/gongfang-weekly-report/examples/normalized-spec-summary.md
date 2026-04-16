# 工房交易双周周报 — 标准化 Spec 摘要

## report_goal

- **report_name**: 工房业务交易双周周报
- **domain**: 工房交易（内容电商 — 用户开店 + 平台提供交易工具和流量）
- **audience**: 交易业务负责人、运营、数据分析师
- **decision_goals**: 识别 GMV 及核心效率指标的周波动原因，定位到具体行业、渠道、商家或商品
- **success_definition**: 每个 section 有数据支撑的结论，说明波动方向和归因

## business_context

- **business_summary**: 用户在平台上个人开店，平台提供交易工具和流量帮助成交
- **重点品类**: 绘画、VUP周边、知识&服务、手工
- **重点流量渠道**: 商品（feed流）、视频（内容带货）、动态（图文带货）、直播（直播间带货）
- **分析分组**: 绘画、VUP周边分别独立分析

## terminology

| 术语 | 定义 | 来源字段 |
|------|------|----------|
| 核心成交体裁/内容渠道 | 商品、视频、动态、直播、其他 | 内容类型 |
| 行业 | 绘画、VUP周边等 | 后台一级类目名称 |
| 周 | 每周五到周四为一个完整周 | 周五-周四周 |
| GMV | 不减退款的成交金额 | GMV（不减退款）|
| 下单转化率 | 支付订单数 / 商详UV | 商详支付转化率-UV |
| PVCTR | 商详UV / 商品曝光PV | PVCTR |
| GPM | GMV / 商品曝光PV × 1000 | GPM |

## time_definition

- **reporting_granularity**: 周
- **周期定义**: 周五~周四，如第12周 = 3月13日~3月19日
- **comparison**: 本周 vs 上周环比
- **historical_window**: 图表展示过去4周趋势

## report_outline

### S1: 核心数据趋势
- **purpose**: 总览交易规模的周度变化
- **metrics**: GMV、买家数、下单转化率、商品曝光PV
- **outputs**: 4张趋势图（GMV柱状图、买家数柱状图、转化率折线图、曝光PV折线图）+ 波动结论
- **data_contract**: 整体数据
- **结论规则**: 仅解释环比波动 >5% 的指标（GMV、订单数、买家数、支付转化率）

### S2: GMV 拆解
- **purpose**: 了解每个行业的交易规模变化趋势，归因 GMV 波动
- **metrics**: GMV、买家数、下单转化率、商品曝光PV
- **dimensions**: 行业（绘画、VUP周边）
- **outputs**:
  - 行业趋势折线图 ×4（GMV / 买家数 / 转化率 / 曝光PV by行业，过去4周）
  - 绘画: 指标卡 + TOP5 商家表 + TOP10 商品表 + 波动归因结论
  - VUP周边: 指标卡 + TOP5 商家表 + TOP10 商品表 + 波动归因结论
- **data_contracts**: 行业数据(主)、商家销售明细、行业商品明细数据
- **表格 schema**:
  - 商家 TOP5: 店铺名称 | GMV | GMV占比 | 买家数 | 下单转化率 | 商品曝光PV（2周 + 每指标环比）
  - 商品 TOP10: 商品名称 | GMV | 买家数 | 下单转化率 | 商品曝光PV（2周 + 每指标环比）
- **结论规则**: 分析>5%波动指标，结合 TOP 商家/商品表数据做头部商家归因

### S3: 流量拆解
- **purpose**: 了解各渠道的流量转化趋势，归因流量波动
- **dimensions**: 内容渠道、资源位二级入口（绘画、VUP周边分别独立分析）
- **outputs（每个行业分组）**:
  - 内容渠道组合图 ×2: GMV Top2 渠道的 GMV(柱)+占比%(线)、曝光PV(柱)+占比%(线)
  - 内容渠道汇总表: 每个渠道的 GMV(4周) / GMV占比(本周) / 曝光PV(4周) / 曝光PV占比(本周) / PVCTR(4周)
  - 资源位二级入口组合图 ×2: GMV Top4 入口的 GMV(柱)+占比%(线)、曝光PV(柱)+占比%(线)
  - 资源位二级入口汇总表: 同内容渠道表结构
- **data_contracts**: 内容渠道数据(主)、资源位二级入口数据
- **结论规则**: 分析 GMV 环比>5% 的渠道/入口，从流量曝光、流量转化率、卖家转化率角度归因

## data_contracts

| contract_id | 文件模式 | 维度 | 核心指标 | 支撑栏目 |
|-------------|---------|------|---------|---------|
| 整体数据 | 整体数据* | 周 | GMV/买家数/转化率/曝光PV/PVCTR/GPM | S1 |
| 行业数据 | 行业数据* | 周+行业 | 同上 | S2 |
| 行业商品明细数据 | 行业商品明细数据* | 周+商品+店铺+行业 | 同上 | S2 |
| 内容渠道数据 | 内容渠道数据* | 周+行业+内容类型 | 同上 | S3 |
| 商家销售明细 | 商家销售明细* | 周+行业+店铺 | 同上 | S2 |
| 资源位二级入口数据 | 资源位二级入口数据* | 周+行业+内容类型+资源位二级入口 | 同上 | S3 |

## analysis_rules

- **must_explain_conditions**: 环比波动 >5% 的指标
- **allowed_evidence**: 头部商家/商品变化、流量曝光变化、转化率变化
- **forbidden_inferences**: 不得猜测因果、不得引用未声明字段
- **narrative_direction**: 必须明确 上涨/下跌/持平，禁止模糊写"变化"

## output_contract

- **format**: html
- **runtime_dependency_policy**: Chart.js 4.x 内联，禁止 CDN
- **style_system**: 内联 base-report.css
- **chart_runtime**: 内联 chart-defaults.js
- **chart_api**: chartPresets.combo / .line / .bar / .doughnut + REPORT_FORMAT + REPORT_WOW
- **指标格式规则**: 率值→百分比、数值→数值、金额→¥前缀、环比→带符号百分比
