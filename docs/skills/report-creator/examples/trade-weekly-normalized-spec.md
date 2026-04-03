# Trade Weekly Normalized Spec

Source requirement:
[交易业务周报需求文档.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/交易业务周报需求文档.md)

## report_goal

- `report_name`: 交易业务周报
- `domain`: trade-commerce
- `audience`: 交易业务 owner、运营同学、分析同学
- `decision_goals`:
  - 识别小店与自营在周维度的 GMV、订单、买家和效率变化
  - 找出行业、商家、流量渠道、成交体裁对波动的核心贡献
  - 为后续经营动作提供异常解释和资源配置依据
- `success_definition`:
  - 稳定输出固定栏目和固定顺序的 HTML 周报
  - 每个结论都能回溯到声明过的数据合同和指标
  - 下游 skill 可直接读取真实 Excel/CSV 生成报告

## business_context

- `business_summary`:
  - 平台是内容电商平台，交易业务包含自营业务和小店业务
- `business_units`:
  - 自营
  - 小店
- `scope_notes`:
  - 周报关注交易规模、流量效率、行业结构、商家结构和成交体裁结构
  - 行业拆解使用 4 大行业和各自类目口径
  - 重点流量专项包含天马推荐商品卡和商城首页 feed

## terminology

### terms

- `核心成交体裁`
  - `definition`: 根据 `内容类型` 字段区分的成交结构
  - `source_fields`: `内容类型`
- `核心流量入口`
  - `definition`: 根据 `资源位一级入口` 和 `资源位二级入口` 区分的流量渠道
  - `source_fields`: `资源位一级入口`, `资源位二级入口`
- `业务线二级`
  - `definition`: 区分自营和小店
  - `source_fields`: `业务线二级`

### segment_rules

- `ACG-南征`
  - `rule_type`: category mapping
  - `rule_logic`:
    - 硬周 = 商品一级经营类目为硬周
    - 游戏虚拟 = 商品一级经营类目为虚拟卡券，或二级类目为游戏账号
    - 出版物 = 商品一级经营类目为出版物
  - `source_fields`: `商品一级经营类目`, `二级类目`
- `ACG-Allen`
  - `rule_type`: category mapping
  - `rule_logic`:
    - 软周 = 商品一级经营类目为软周
    - 盲盒 = 商品一级经营类目为赏类
  - `source_fields`: `商品一级经营类目`
- `非ACG-悟饭`
  - `rule_type`: category mapping
  - `rule_logic`:
    - 珠宝文玩 = 后台一级类目名称或一级类目为珠宝文玩
    - 组装机 = 商品一级经营类目为电脑
    - 兴趣手作 = 后台一级类目名称或一级类目属于特色手工艺、母婴萌宠、智能家居、文创礼品
    - 卡牌 = 后台三级类目名称或三级类目为卡牌
  - `source_fields`: `后台一级类目名称`, `一级类目`, `商品一级经营类目`, `后台三级类目名称`, `三级类目`
- `非ACG-加林`
  - `rule_type`: attachment mapping
  - `rule_logic`: 根据头部 UP list 里的商家 ID 识别
  - `source_fields`: `商家ID`

## time_definition

- `reporting_granularity`: weekly
- `current_period_definition`: 每周五到周四为一个完整周
- `comparison_period_definition`: 对比上一完整周五到周四周期
- `historical_window`: 默认展示最近若干周的周趋势

## report_outline

### section `core-data-trend`

- `title`: 核心数据趋势
- `purpose`: 看清小店和自营 GMV 规模变化
- `required_views`:
  - 小店指标卡
  - 自营指标卡
  - GMV 柱状图
  - 小店对自营控比折线图
  - 买家数折线图
  - 订单数柱状图
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
  - 图表
  - 指标卡
  - 周维度结论
- `narrative_expectations`:
  - 解释 GMV、订单数、买家数、支付转化率的周波动
- `table_schemas`:
  - 无固定表格
- `narrative_schema`:
  - 关键指标必须显示本周值、上周值和 WoW

### section `industry-breakdown`

- `title`: by 行业拆解
- `purpose`: 了解行业和类目交易规模变化并解释 GMV 波动原因
- `required_views`:
  - 整体行业 GMV 趋势图
  - 整体行业 GPM 图
  - 小店行业 GMV 趋势图
  - 小店行业买家趋势图
  - 整体行业表
  - 小店行业表
  - 自营行业表
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
  - 三张数据表
  - 行业归因结论
- `narrative_expectations`:
  - 仅观测小店周维度 GMV 变化幅度超过 5% 的行业和类目
  - 仅观测自营周维度 GMV 变化幅度超过 5% 的行业和类目
  - 根据商家和商品的周维度 GMV 波动分析原因
- `table_schemas`:
  - 每张表必须按行业 / 类目展示各周 GMV、买家数、订单数、GPM 及 WoW
- `narrative_schema`:
  - 归因结论必须明确波动方向和主要驱动

### section `shop-merchant-breakdown`

- `title`: by 小店商家拆解
- `purpose`: 识别小店商家对行业变化的核心贡献
- `required_views`:
  - Top20 商家周趋势图
  - Top20 商家明细表
  - 分行业 / 类目 Top20 商家表
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
  - 分行业看周维度 GMV 变化幅度超过 5% 的商家并分析流量、转化率、商品因素
- `table_schemas`:
  - 表格必须包含本周 GMV、上周 GMV、GMV WoW、贡献率、买家、订单、客单价、转化率、GPM
- `narrative_schema`:
  - 商家结论必须标明 GMV 涨跌方向与原因

### section `traffic-channel-breakdown`

- `title`: by 流量渠道
- `purpose`: 了解流量的周维度变化及转化效率波动，区分小店和自营
- `required_views`:
  - 总流量柱状图
  - 小店 PV 占比折线图
  - 流量总览表
  - 小店分渠道表
  - 自营分渠道表
  - 分行业渠道表
  - 天马推荐商品卡专项图表和表格
  - 商城首页 feed 专项图表和表格
- `required_metrics`:
  - 商品曝光 PV
  - 流量占比
  - 订单量
  - GMV
  - GPM
  - CTR
  - 商详转化率
- `required_dimensions`:
  - 周
  - 业务线二级
  - 流量渠道
  - 行业
- `required_outputs`:
  - 趋势图
  - 分渠道表
  - 专项表
  - 渠道归因结论
- `narrative_expectations`:
  - 解释总流量波动和小店曝光占比波动
  - 解释小店各流量渠道转化效率的大幅波动
- `table_schemas`:
  - 流量表需展示 PV、占比、订单量、GMV、GPM、CTR、商详转化率及 WoW
- `narrative_schema`:
  - 渠道结论必须说明波动方向和归因依据

### section `transaction-content-breakdown`

- `title`: by 成交体裁
- `purpose`: 了解不同体裁下的成交规模变化，区分小店和自营
- `required_views`:
  - 整体饼图
  - 小店饼图
  - 自营饼图
  - 小店分行业饼图
  - 体裁对比表
- `required_metrics`:
  - GMV
  - GMV 占比
- `required_dimensions`:
  - 内容类型
  - 业务线二级
  - 行业
  - 周
- `required_outputs`:
  - 结构分布图
  - 对比表
  - 成交结构变化结论
- `narrative_expectations`:
  - 分小店：看整体和各行业的成交结构变化，包括占比和绝对值
- `table_schemas`:
  - 体裁对比表必须包含本周 GMV、占比、上周占比变化和 GMV WoW
- `narrative_schema`:
  - 结论必须说明占比上升 / 下降最大的体裁

## data_contracts

- `overall-weekly`
  - `display_name`: 整体数据
  - `file_name_pattern`: `整体数据*`
  - `time_granularity`: weekly
  - `dimensions`: `周`, `业务线二级`
  - `metrics`: `GMV`, `订单数`, `买家数`, `GPM`, `曝光PV`, `CTR`, `商详转化率`
  - `field_notes`: 只区分小店和自营
  - `supported_sections`: `core-data-trend`
  - `sample_file_required`: true
- `industry-weekly`
  - `display_name`: 区分行业
  - `file_name_pattern`: `区分行业*`
  - `time_granularity`: weekly
  - `dimensions`: `周`, `业务线二级`, `商家`, `经营类目`, `商品类目`
  - `metrics`: `GMV`, `订单数`, `买家数`, `GPM`, `曝光PV`, `CTR`, `商详转化率`
  - `field_notes`: 行业和商家拆解主合同
  - `supported_sections`: `industry-breakdown`, `shop-merchant-breakdown`
  - `sample_file_required`: true
- `traffic-channel-summary`
  - `display_name`: 分行业x流量渠道
  - `file_name_pattern`: `分行业*流量*`
  - `time_granularity`: weekly
  - `dimensions`: `周`, `业务线二级`, `流量渠道`
  - `metrics`: `GMV`, `订单数`, `买家数`, `GPM`, `曝光PV`, `CTR`, `商详转化率`
  - `field_notes`: 流量总览和行业级流量分析
  - `supported_sections`: `traffic-channel-breakdown`
  - `sample_file_required`: true
- `traffic-channel-detail`
  - `display_name`: 商品x流量渠道x商家x经营类目x商品类目
  - `file_name_pattern`: `*商品*流量*商家*`
  - `time_granularity`: weekly
  - `dimensions`: `周`, `流量渠道`, `商家`, `经营类目`, `商品类目`
  - `metrics`: `GMV`, `订单数`, `买家数`, `GPM`, `曝光PV`, `CTR`, `商详转化率`
  - `field_notes`: 渠道归因和爆品归因
  - `supported_sections`: `traffic-channel-breakdown`, `shop-merchant-breakdown`
  - `sample_file_required`: false
- `content-type-summary`
  - `display_name`: 分行业x内容类型
  - `file_name_pattern`: `分行业*内容*`
  - `time_granularity`: weekly
  - `dimensions`: `周`, `业务线二级`, `内容类型`, `行业`
  - `metrics`: `GMV`, `订单数`, `买家数`, `GPM`, `曝光PV`, `CTR`, `商详转化率`
  - `field_notes`: 成交体裁结构分析
  - `supported_sections`: `transaction-content-breakdown`
  - `sample_file_required`: true
- `content-type-detail`
  - `display_name`: 商品x体裁x商家x经营类目x商品类目
  - `file_name_pattern`: `*商品*体裁*商家*`
  - `time_granularity`: weekly
  - `dimensions`: `周`, `内容类型`, `商家`, `经营类目`, `商品类目`
  - `metrics`: `GMV`, `订单数`, `买家数`, `GPM`, `曝光PV`, `CTR`, `商详转化率`
  - `field_notes`: 体裁爆品归因
  - `supported_sections`: `transaction-content-breakdown`
  - `sample_file_required`: false
- `owned-shop-channel`
  - `display_name`: 分自营和小店x流量渠道
  - `file_name_pattern`: `分自营和小店*流量渠道*`
  - `time_granularity`: weekly
  - `dimensions`: `周`, `业务线二级`, `资源位二级入口`, `商家`, `经营类目`, `商品类目`
  - `metrics`: `GMV`, `订单数`, `买家数`, `GPM`, `曝光PV`, `点击PV`, `商详PV`, `CTR`, `商详转化率`
  - `field_notes`: 区分小店和自营的流量渠道详表
  - `supported_sections`: `traffic-channel-breakdown`
  - `sample_file_required`: false
- `tm-card`
  - `display_name`: 天马推荐商品卡
  - `file_name_pattern`: `天马推荐商品卡*`
  - `time_granularity`: weekly
  - `dimensions`: `周`, `业务线二级`, `资源位二级入口`, `商家`, `经营类目`, `商品类目`
  - `metrics`: `GMV`, `订单数`, `买家数`, `GPM`, `曝光PV`, `点击PV`, `商详PV`, `CTR`, `商详转化率`
  - `field_notes`: 专项流量渠道数据
  - `supported_sections`: `traffic-channel-breakdown`
  - `sample_file_required`: false
- `feed-channel`
  - `display_name`: 分商城首页feed
  - `file_name_pattern`: `*商城首页feed*`
  - `time_granularity`: weekly
  - `dimensions`: `周`, `业务线二级`, `资源位二级入口`, `商家`, `经营类目`, `商品类目`
  - `metrics`: `GMV`, `订单数`, `买家数`, `GPM`, `曝光PV`, `点击PV`, `商详PV`, `CTR`, `商详转化率`
  - `field_notes`: 商城首页 feed 专项流量数据
  - `supported_sections`: `traffic-channel-breakdown`
  - `sample_file_required`: false
- `up-list`
  - `display_name`: 头部UPlist
  - `file_name_pattern`: `*UPlist*`
  - `time_granularity`: snapshot
  - `dimensions`: `商家ID`
  - `metrics`: `无`
  - `field_notes`: 用于识别非ACG-加林行业
  - `supported_sections`: `industry-breakdown`, `shop-merchant-breakdown`
  - `sample_file_required`: false

## analysis_rules

- `must_explain_conditions`:
  - 核心数据趋势中的 GMV、订单数、买家数、支付转化率波动
  - 行业和类目中 GMV 变化幅度超过 5% 的小店和自营对象
  - 商家中 GMV 变化幅度超过 5% 的对象
  - 流量渠道中波动幅度大的渠道
- `allowed_evidence`:
  - 仅使用声明的数据合同和字段
  - 行业归因可用商家、商品、流量、转化率字段
  - 商家归因可用 PV、转化率、核心商品证据
- `forbidden_inferences`:
  - 禁止推断未声明的 KPI 公式
  - 禁止没有字段支撑的因果解释
  - 禁止脱离周维度和业务线二级口径解读
- `metric_calculation_contracts`:
  - 支付转化率 = 支付订单数 / 商品曝光PV
  - GPM = GMV / 商品曝光PV × 1000
- `threshold_rules`:
  - 行业与商家 GMV 重点观测阈值 = 5%
- `fallback_behavior`:
  - 可选明细文件缺失时保留主模块输出，但对应归因块需显式降级

## output_contract

- `format`: `html`
- `required_sections`:
  - 标题区
  - 周期信息区
  - 核心数据趋势
  - by 行业拆解
  - by 小店商家拆解
  - by 流量渠道
  - by 成交体裁
  - 数据说明区
- `section_order`:
  - `core-data-trend`
  - `industry-breakdown`
  - `shop-merchant-breakdown`
  - `traffic-channel-breakdown`
  - `transaction-content-breakdown`
- `required_blocks`:
  - 图表区
  - 表格区
  - 栏目级结论区
  - 数据说明区
- `citation_rules`:
  - 每条结论必须可回溯到数据合同
- `table_column_rules`:
  - 各栏目表格必须遵守 spec 中声明的固定列和 WoW 列
- `wow_display_rules`:
  - 所有按周对比的关键指标都必须显示上周环比或占比变化
- `narrative_direction_rules`:
  - 结论必须明确上涨 / 下跌 / 持平或环比方向

## skill_generation_contract

- `skill_name`: trade-weekly-report
- `skill_title`: Trade Weekly Report
- `skill_level`: `runnable`
- `required_files`:
  - `SKILL.md`
  - `README.md`
  - `skill.json`
- `required_assets`:
  - `assets/html-contract.md`
  - `assets/report-outline.md`
  - `assets/report-prompt.md`
  - `assets/validation-checklist.md`
- `required_examples`:
  - `examples/normalized-spec.md`
  - `examples/normalized-spec-summary.md`
  - `examples/input_inventory.md`
  - `examples/output-outline.html`
- `required_tests`:
  - `tooling/tests/trade-weekly-report.sh`

## acceptance_checks

- `spec_completeness_checks`:
  - 五个栏目都声明了 purpose、views、metrics、dimensions、outputs
  - 关键数据合同均已声明 pattern、字段和支持栏目
- `spec_consistency_checks`:
  - 周期统一为周五到周四
  - 行业分类口径已在 terminology 中显式定义
  - 输出合同与 HTML 周报兼容
- `generation_readiness_checks`:
  - 下游 skill 名称已确定
  - 所有核心栏目都有数据合同支撑
  - 样本脚本和样本数据可用于 runnable 验证
- `html_output_checks`:
  - 输出为单一 HTML 主产物
  - HTML 包含五个固定栏目和数据说明区
- `runnable_readiness_checks`:
  - 可执行脚本能读取 `docs/周报生成器_v3/docs` 中的样本数据
  - 生成的 HTML 包含核心栏目名称
