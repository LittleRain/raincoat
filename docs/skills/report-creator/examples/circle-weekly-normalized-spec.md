# Circle Weekly Normalized Spec

Source requirement:
[圈子业务周报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/圈子业务周报需求.md)

## report_goal

- `report_name`: 圈子业务周报
- `domain`: circle-commerce
- `audience`: 交易业务 owner、运营同学、分析同学
- `decision_goals`:
  - 识别小店与自营在周维度的 GMV、订单、买家和效率变化
  - 找出行业、商家、流量渠道、成交体裁对波动的核心贡献
  - 为后续经营动作提供可执行的异常解释和关注重点
- `success_definition`:
  - 周报能稳定输出固定栏目
  - 每个结论都能回溯到声明过的数据合同和指标
  - HTML 结构对业务方可直接阅读和分发

## business_context

- `business_summary`:
  - 平台为内容电商平台，交易业务包含自营业务和小店业务
- `business_units`:
  - 自营
  - 小店
- `scope_notes`:
  - 本周报关注交易规模、流量效率和成交结构
  - 行业拆解使用业务方提供的 4 大行业口径

## terminology

### terms

- `核心成交体裁`
  - `definition`: 由内容类型字段区分成交结构
  - `source_fields`: `内容类型`
- `核心流量入口`
  - `definition`: 由资源位一级入口和二级入口区分流量渠道
  - `source_fields`: `资源位一级入口`, `资源位二级入口`
- `业务线二级`
  - `definition`: 区分自营与小店
  - `source_fields`: `业务线二级`

### segment_rules

- `ACG-南征`
  - `rule_type`: category mapping
  - `rule_logic`:
    - 硬周: 商品一级经营类目 = 硬周
    - 游戏虚拟: 商品一级经营类目 = 虚拟卡券 or 二级类目 = 游戏账号
    - 出版物: 商品一级经营类目 = 出版物
  - `source_fields`: `商品一级经营类目`, `二级类目`
- `ACG-Allen`
  - `rule_type`: category mapping
  - `rule_logic`:
    - 软周: 商品一级经营类目 = 软周
    - 盲盒: 商品一级经营类目 = 赏类
  - `source_fields`: `商品一级经营类目`
- `非ACG-悟饭`
  - `rule_type`: category mapping
  - `rule_logic`:
    - 珠宝文玩: 后台一级类目名称 or 一级类目 = 珠宝文玩
    - 组装机: 商品一级经营类目 = 电脑
    - 兴趣手作: 后台一级类目名称 or 一级类目 in 特色手工艺、母婴萌宠、智能家居、文创礼品
    - 卡牌: 后台三级类目名称 or 三级类目 = 卡牌
  - `source_fields`: `后台一级类目名称`, `一级类目`, `商品一级经营类目`, `后台三级类目名称`, `三级类目`
- `非ACG-加林/头部UP`
  - `rule_type`: attachment mapping
  - `rule_logic`: 根据头部 UP list 中的商家 ID 识别
  - `source_fields`: `商家ID`

## time_definition

- `reporting_granularity`: weekly
- `current_period_definition`: 每周五到周四
- `comparison_period_definition`: 对比上一完整周五到周四周期
- `historical_window`: 过去若干周的 by 周趋势

## report_outline

### section `core-data-trend`

- `title`: 核心数据趋势
- `purpose`: 看清小店和自营 GMV 规模变化
- `required_views`:
  - 小店指标表
  - 自营指标表
  - 历史趋势图
- `required_metrics`:
  - GMV
  - 小店对自营控比
  - 支付订单买家数
  - 支付订单数
  - 支付转化率
  - GPM
- `required_dimensions`:
  - 业务线二级
  - 周
- `required_outputs`:
  - 数值表
  - 趋势图
  - 周维度结论
- `narrative_expectations`:
  - 解释 GMV、订单数、买家数、支付转化率的周波动

### section `industry-breakdown`

- `title`: by 行业拆解
- `purpose`: 了解行业和类目交易规模变化并解释 GMV 波动原因
- `required_views`:
  - 整体行业周趋势图
  - 小店行业周趋势图
  - 自营行业周趋势图
  - 三张数据表
- `required_metrics`:
  - GMV
  - 买家数
  - 订单数
  - GPM
- `required_dimensions`:
  - 行业
  - 类目
  - 业务线二级
  - 周
- `required_outputs`:
  - 图表
  - 整体/小店/自营数据表
  - 异常波动说明
- `narrative_expectations`:
  - 仅分析 GMV 变化幅度超过 5% 的行业和类目

### section `shop-merchant-breakdown`

- `title`: by 小店商家拆解
- `purpose`: 识别小店商家对行业变化的核心贡献
- `required_views`:
  - Top20 商家周趋势图
  - 整体 Top20 商家表
  - 分行业类目 Top20 商家表
- `required_metrics`:
  - GMV
  - 买家数
  - 订单量
  - 客单价
  - 下单转化率
  - GPM
  - 贡献率
- `required_dimensions`:
  - 商家
  - 行业
  - 类目
  - 周
- `required_outputs`:
  - 商家排序表
  - 贡献率分析
  - 波动原因说明
- `narrative_expectations`:
  - 仅关注周维度 GMV 变化超过 5% 的商家

### section `traffic-channel-breakdown`

- `title`: by 流量渠道
- `purpose`: 看总流量和核心渠道转化效率波动
- `required_views`:
  - 总流量柱状图
  - 小店曝光占比折线图
  - 渠道分布表
  - 天马推荐商品卡专项
  - 商城首页feed专项
- `required_metrics`:
  - 商品曝光 PV
  - 流量占比
  - 订单量
  - GMV
  - GPM
  - CTR
  - 商详转化率
- `required_dimensions`:
  - 渠道
  - 业务线二级
  - 行业
  - 周
- `required_outputs`:
  - 趋势图
  - 分渠道表
  - 归因结论
- `narrative_expectations`:
  - 解释总流量波动、小店曝光占比波动和关键渠道效率变化

### section `transaction-content-breakdown`

- `title`: by 成交体裁
- `purpose`: 识别不同成交体裁的结构变化
- `required_views`:
  - 整体成交结构饼图
  - 小店成交结构饼图
  - 自营成交结构饼图
  - 小店分行业成交结构饼图
- `required_metrics`:
  - GMV
  - GMV 占比
- `required_dimensions`:
  - 内容类型
  - 业务线二级
  - 行业
- `required_outputs`:
  - 结构分布图
  - 成交结构变化结论
- `narrative_expectations`:
  - 关注整体和各行业的占比及绝对值变化

## data_contracts

- `overall-weekly`
  - `display_name`: 整体数据
  - `file_name_pattern`: `整体数据*`
  - `time_granularity`: weekly
  - `dimensions`: `业务线二级`, `周`
  - `metrics`: `GMV`, `订单数`, `买家数`, `GPM`, `曝光PV`, `CTR`, `商详转化率`
  - `field_notes`: 仅区分小店和自营
  - `supported_sections`: `core-data-trend`
- `industry-weekly`
  - `display_name`: 区分行业
  - `file_name_pattern`: `区分行业*`
  - `time_granularity`: weekly
  - `dimensions`: `业务线二级`, `商家`, `经营类目`, `商品类目`, `周`
  - `metrics`: `GMV`, `订单数`, `买家数`, `GPM`, `曝光PV`, `CTR`, `商详转化率`
  - `field_notes`: 行业和类目拆解的主合同
  - `supported_sections`: `industry-breakdown`, `shop-merchant-breakdown`
- `traffic-weekly-summary`
  - `display_name`: 分行业x流量渠道
  - `file_name_pattern`: `分行业x流量渠道*`
  - `time_granularity`: weekly
  - `dimensions`: `业务线二级`, `流量渠道`, `周`
  - `metrics`: `GMV`, `订单数`, `买家数`, `GPM`, `曝光PV`, `CTR`, `商详转化率`
  - `field_notes`: 渠道总览和行业级流量分析
  - `supported_sections`: `traffic-channel-breakdown`
- `traffic-weekly-detail`
  - `display_name`: 商品x流量渠道x商家x经营类目x商品类目
  - `file_name_pattern`: `*商品x流量渠道x商家x经营类目x商品类目*`
  - `time_granularity`: weekly
  - `dimensions`: `流量渠道`, `商家`, `经营类目`, `商品类目`, `周`
  - `metrics`: `GMV`, `订单数`, `买家数`, `GPM`, `曝光PV`, `CTR`, `商详转化率`
  - `field_notes`: 渠道归因和商家归因
  - `supported_sections`: `shop-merchant-breakdown`, `traffic-channel-breakdown`
- `content-weekly-summary`
  - `display_name`: 分行业x内容类型
  - `file_name_pattern`: `分行业x内容类型*`
  - `time_granularity`: weekly
  - `dimensions`: `业务线二级`, `内容类型`, `行业`, `周`
  - `metrics`: `GMV`, `订单数`, `买家数`, `GPM`, `曝光PV`, `CTR`, `商详转化率`
  - `field_notes`: 成交体裁结构分析
  - `supported_sections`: `transaction-content-breakdown`
- `content-weekly-detail`
  - `display_name`: 商品x体裁x商家x经营类目x商品类目
  - `file_name_pattern`: `*商品x体裁x商家x经营类目x商品类目*`
  - `time_granularity`: weekly
  - `dimensions`: `内容类型`, `商家`, `经营类目`, `商品类目`, `周`
  - `metrics`: `GMV`, `订单数`, `买家数`, `GPM`, `曝光PV`, `CTR`, `商详转化率`
  - `field_notes`: 成交体裁下钻分析
  - `supported_sections`: `transaction-content-breakdown`, `shop-merchant-breakdown`

## analysis_rules

- `must_explain_conditions`:
  - 行业或类目 GMV 周变化幅度超过 5%
  - 商家 GMV 周变化幅度超过 5%
  - 渠道效率波动明显
- `allowed_evidence`:
  - GMV、订单、买家、曝光、CTR、商详转化率、GPM、贡献率
  - 商家和商品层级的周维度波动
- `forbidden_inferences`:
  - 没有数据支持时，不得归因到外部营销活动、用户偏好变化或平台策略变化
  - 缺少附件时，不得自行推断头部UP商家范围
- `ranking_rules`:
  - 商家以 GMV 排序输出 Top20
- `threshold_rules`:
  - 仅对周变化超过 5% 的行业、类目和商家输出重点分析

## output_contract

- `format`: `html`
- `required_sections`:
  - `core-data-trend`
  - `industry-breakdown`
  - `shop-merchant-breakdown`
  - `traffic-channel-breakdown`
  - `transaction-content-breakdown`
- `section_order`:
  - `core-data-trend`
  - `industry-breakdown`
  - `shop-merchant-breakdown`
  - `traffic-channel-breakdown`
  - `transaction-content-breakdown`
  - `source-notes`
- `required_blocks`:
  - 标题区
  - 周期信息区
  - 图表区
  - 数据表区
  - 结论区
  - 数据说明区
- `citation_rules`:
  - 每个结论必须能映射到已声明的数据合同和指标

## skill_generation_contract

- `skill_name`: `report-circle-weekly`
- `skill_title`: `Report Circle Weekly`
- `required_files`:
  - `SKILL.md`
  - `README.md`
  - `skill.json`
- `required_assets`:
  - `html-contract.md`
  - `report-outline.md`
  - `report-prompt.md`
  - `validation-checklist.md`
- `required_examples`:
  - `normalized-spec.md`
  - `input_inventory.md`
  - `output-outline.html`

## acceptance_checks

- `spec_completeness_checks`:
  - 所有 5 个栏目均声明了目标、视图、指标和维度
  - 所有数据合同都有文件名模式和支持栏目
- `spec_consistency_checks`:
  - 栏目指标均能映射到声明过的数据合同
  - 时间口径统一为周五到周四
- `generation_readiness_checks`:
  - 下游 skill 包名称、文件、资产和样例已声明
  - 没有未解决的附件依赖冲突
- `html_output_checks`:
  - HTML 输出固定为标题、周期、栏目正文、数据说明的稳定结构
