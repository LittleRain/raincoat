# 规范化 Spec 摘要

## report_goal

- **report_name**: 交易业务周报
- **domain**: 内容电商交易分析
- **audience**: 交易业务负责人、数据分析师
- **decision_goals**: 分析 GMV 波动原因，识别增长机会
- **success_definition**: 周报包含 5 大栏目，数据准确，图表完整（22图 + 19表）

## business_context

- **business_summary**: 内容电商平台（类似 TikTok Shop），包含自营和小店两种业务模式
- **business_units**: 小店、自营、工坊、票务
- **scope_notes**: 仅分析交易相关指标，不包含直播实时数据

## terminology

### terms
- GMV: 支付销售额（不减退款）
- CTR: 点击率 = 商详曝光PV / 商品曝光PV
- CVR: 转化率 = 支付订单数 / 商品曝光PV
- GPM: 千次曝光GMV = GMV / 商品曝光PV × 1000
- 贡献率: (商家本周GMV - 商家上周GMV) / 该分类本周涨跌GMV
- 控比: 小店GMV / 自营GMV

### segment_rules
- 业务线二级: 小店、工坊、票务、自营
- 核心成交体裁: 商品、视频、动态、直播、其他
- 核心流量入口: 天马推荐商品卡、商城首页feed 等

### shop_industry_rules（小店行业分类）
通过 merchant_id 关联商家标签表（sheet 名：sheet），字段 owner_ld 区分行业：

| 行业 | owner_ld 值 | 说明 |
|------|------------|------|
| 南征 | 南征 | ACG ACG行业 |
| allen | allen | ACG ACG行业 |
| 孙悟饭 | 孙悟饭 | 综合行业 |
| 加林 | 加林 | 头部达人 |
| 小店其他 | 其他 / NULL | 未匹配均归此类 |

### ziying_industry_rules（自营行业分类）
通过经营一级类目名称字段区分：

| 行业 | 经营一级类目 |
|------|------------|
| ACG自营-南征 | 硬周、虚拟卡券、出版物 |
| ACG自营-allen | 软周、赏类 |
| 自营-其他 | 其余所有 |

## time_definition

- **reporting_granularity**: 周（周五至周四）
- **current_period_definition**: W{week}
- **comparison_period_definition**: W{week-1}
- **mtd_definition**: 当月内所有周GMV之和（近似）

## data_contracts

| contract_id | display_name | sheet | supported_sections | notes |
|-------------|--------------|-------|-------------------|-------|
| doc1 | 整体.xlsx | 默认 | S1 | 业务线级别指标，周粒度 |
| doc2 | 行业.xlsx | 默认 | S2, S3, S4小店行业流量 | 含商家ID，可关联商家标签 |
| doc3 | 商品明细.xlsx | 默认 | S3 | 日粒度，需按日期范围聚合 |
| doc4 | 流量.xlsx | 默认 | S4 | 资源位二级入口粒度；无商家ID |
| doc5 | 内容类型.xlsx | 默认 | S5 | 内容类型粒度 |
| doc6 | 商家标签.xlsx | sheet | S2, S3, S5 | merchant_id → owner_ld/owner_cate |

## field_mapping

整体/行业/内容类型文件字段重命名：
- `GMV（不减退款）` → `GMV`
- `支付订单买家数` → `买家数`
- `支付订单数` → `订单数`
- `商详支付转化率-UV` → `CVR`
- `PVCTR` → `CTR`

## output_contract

- **format**: html
- **expected_output_inventory**:
  - 总图表: 22（S1×6 + S2×3 + S3×1 + S4×4 + S5×8）
  - 总表格: 19（S1×2 + S2×4 + S3×7 + S4×6 + S5×0）
  - 必需指标: GMV, 控比, 买家数, 订单数, CTR, CVR, GPM, 贡献率
- **runtime_dependency_policy**: Chart.js via CDN + CSS/JS 内联
- **color_convention**: 上涨绿色，下跌红色（中国惯例）

## known_issues

- 流量文件无商家ID：小店分行业流量概况改用行业.xlsx 数据（有轻微口径差异，实际PV不等于渠道PV）
- 商品明细为日粒度：聚合时需按周起止日期筛选
- YOY 暂无历史同期数据，显示"暂无同期数据"

## skill_generation_contract

- **skill_name**: trade-weekly-report
- **skill_level**: L1
- **script**: scripts/generate_report.py
- **assets**: assets/base-report.css, assets/chart-defaults.js
- **level_readiness**:
  - real_samples_present: true
  - two_period_coverage: true
  - real_runner_present: true
  - full_spec_compliance: true（v2.0 已按需求文档完整实现）
