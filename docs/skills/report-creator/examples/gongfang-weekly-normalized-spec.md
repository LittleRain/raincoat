# Gongfang Weekly Normalized Spec

Source requirement:
[工房业务交易双周报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/工房业务交易双周报需求.md)

## report_goal

- `report_name`: 工房业务交易双周报
- `domain`: gongfang-commerce
- `audience`: 交易业务 owner、运营同学、分析同学
- `decision_goals`:
  - 识别工房交易业务在周维度的规模和效率变化
  - 识别绘画+绘画周边与 VUP 周边两个重点行业的核心波动来源
  - 为行业经营动作和内容渠道资源分配提供可执行结论
- `success_definition`:
  - 稳定输出固定栏目和固定顺序的 HTML 周报
  - 每个结论都能回溯到已声明的数据合同和字段
  - 能解释 GMV、买家数、转化率、GPM 及重点渠道占比的周波动

## business_context

- `business_summary`:
  - 工房是一个用户个人开店的平台，平台提供交易工具和流量支持成交
- `business_units`:
  - 工房交易业务
- `scope_notes`:
  - 重点品类包括绘画、VUP周边、绘画周边、知识&服务、手工
  - 重点行业分析聚焦绘画+绘画周边、VUP周边
  - 重点流量渠道包括商品、视频、动态、直播
- `known_limitations`:
  - 需求文档未单独声明读者角色，本 spec 按内部交易经营周报惯例补全为 owner、运营、分析

## terminology

### terms

- `核心成交体裁`
  - `definition`: 根据表格中的 `内容类型` 字段区分的成交结构
  - `source_fields`: `内容类型`
- `流量渠道`
  - `definition`: 商品、视频、动态、直播四类核心内容渠道
  - `source_fields`: `内容类型`
- `行业`
  - `definition`: 绘画、VUP周边、绘画周边、知识&服务、手工、极客创造、手办模玩等后台一级类目
  - `source_fields`: `后台一级类目名称`

### segment_rules

- `行业口径`
  - `rule_type`: category mapping
  - `rule_logic`:
    - 绘画+绘画周边 = 绘画 + 绘画周边
    - VUP周边 = VUP周边
  - `source_fields`: `后台一级类目名称`
- `内容渠道口径`
  - `rule_type`: dimension mapping
  - `rule_logic`:
    - 商品 = 商品 feed 流场域
    - 视频 = 内容场域的视频带货
    - 动态 = 内容场域的图文内容带货
    - 直播 = 直播间带货
  - `source_fields`: `内容类型`

## time_definition

- `reporting_granularity`: weekly
- `current_period_definition`: 每周五到周四为一个完整周
- `comparison_period_definition`: 对比上一完整周五到周四周期
- `historical_window`: 周维度趋势图按输入文件中可用周数据展示

## report_outline

### section `core-data-trend`

- `title`: 核心数据趋势
- `purpose`: 看清工房交易规模与效率的周变化
- `required_views`:
  - GMV 周趋势柱状图
  - 买家数周趋势柱状图
  - 下单转化率周趋势折线图
  - GPM 周趋势折线图
- `required_metrics`:
  - GMV
  - 支付订单数
  - 支付订单买家数
  - 商详支付转化率-UV
  - GPM
- `required_dimensions`:
  - 周
- `required_outputs`:
  - 图表
  - 指标波动结论
- `narrative_expectations`:
  - 解释 GMV、订单数、买家数、支付转化率的周波动

### section `industry-breakdown`

- `title`: by 行业拆解
- `purpose`: 解释重点行业交易规模变化与渠道结构波动
- `required_views`:
  - 绘画+绘画周边 GMV 周趋势图
  - 绘画+绘画周边 GMV 渠道分布图
  - 绘画+绘画周边 买家数周趋势图
  - 绘画+绘画周边 买家数渠道分布图
  - 绘画+绘画周边 转化率与 GPM 折线图
  - VUP周边 GMV 周趋势图
  - VUP周边 GMV 渠道分布图
  - VUP周边 买家数周趋势图
  - VUP周边 买家数渠道分布图
  - VUP周边 转化率与 GPM 折线图
  - 重点商品影响表
- `required_metrics`:
  - GMV
  - 支付订单买家数
  - 支付订单数
  - 商详支付转化率-UV
  - GPM
  - 商品曝光PV
  - PVCTR
- `required_dimensions`:
  - 周
  - 行业
  - 内容类型
  - 商品名称
- `required_outputs`:
  - 图表
  - 商品归因分析
  - 渠道占比波动结论
- `narrative_expectations`:
  - 仅重点解释绘画+绘画周边、VUP周边中环比波动超过 5% 的指标
  - 使用行业商品明细数据说明受影响商品以及转化或流量变化
  - 观测内容渠道占比波动超过 5% 的渠道并解释原因

## data_contracts

- `overall-weekly`
  - `display_name`: 整体数据
  - `file_name_pattern`: `整体数据*`
  - `time_granularity`: weekly
  - `dimensions`: `日期`
  - `metrics`: `PVCTR`, `商详UV`, `支付订单数`, `支付订单买家数`, `GMV（不减退款）`, `商详支付转化率-UV`, `GPM`
  - `field_notes`: 用于整体核心趋势分析
  - `supported_sections`: `core-data-trend`
- `industry-weekly`
  - `display_name`: 行业数据
  - `file_name_pattern`: `行业数据*`
  - `time_granularity`: weekly
  - `dimensions`: `日期`, `后台一级类目名称`
  - `metrics`: `商品曝光PV`, `PVCTR`, `商详UV`, `支付订单数`, `支付订单买家数`, `GMV（不减退款）`, `商详支付转化率-UV`, `GPM`
  - `field_notes`: 用于重点行业周趋势和效率分析
  - `supported_sections`: `industry-breakdown`
- `industry-goods-weekly`
  - `display_name`: 行业商品明细数据
  - `file_name_pattern`: `行业商品明细数据*`
  - `time_granularity`: weekly
  - `dimensions`: `周`, `商品名称`, `后台一级类目名称`
  - `metrics`: `商品曝光PV`, `PVCTR`, `商详UV`, `支付订单数`, `支付订单买家数`, `GMV（不减退款）`, `商详支付转化率-UV`, `GPM`
  - `field_notes`: 仅包含本周和上周，用于商品归因
  - `supported_sections`: `industry-breakdown`
- `content-channel-weekly`
  - `display_name`: 内容渠道数据
  - `file_name_pattern`: `内容渠道数据*`
  - `time_granularity`: weekly
  - `dimensions`: `日期`, `后台一级类目名称`, `内容类型`
  - `metrics`: `商品曝光PV`, `PVCTR`, `商详UV`, `支付订单数`, `支付订单买家数`, `GMV（不减退款）`, `商详支付转化率-UV`, `GPM`
  - `field_notes`: 用于行业内内容渠道结构分布与占比波动分析
  - `supported_sections`: `industry-breakdown`

## analysis_rules

- `must_explain_conditions`:
  - 解释核心数据趋势中的周度波动
  - 解释重点行业中环比波动超过 5% 的指标
  - 解释重点行业中内容渠道占比波动超过 5% 的渠道
- `allowed_evidence`:
  - 仅使用声明的数据合同中的指标、维度和字段
  - 商品归因仅允许基于行业商品明细中的 GMV、买家数、转化率、曝光PV、PVCTR、商详UV
  - 渠道归因仅允许基于内容渠道数据中的占比和绝对值变化
- `forbidden_inferences`:
  - 禁止推断未声明的指标公式
  - 禁止在没有字段支撑时给出因果解释
  - 禁止扩展到非重点行业的深度归因
- `threshold_rules`:
  - 行业指标解释阈值：环比绝对变化超过 5%
  - 渠道占比解释阈值：占比变化超过 5%

## output_contract

- `format`: `html`
- `required_sections`:
  - 标题区
  - 周期信息区
  - 核心数据趋势
  - by 行业拆解
  - 数据说明区
- `section_order`:
  - `core-data-trend`
  - `industry-breakdown`
- `required_blocks`:
  - 图表渲染区
  - 指标摘要区
  - 栏目级结论区
  - 数据说明区
- `citation_rules`:
  - 每条结论必须能回溯到对应数据合同
  - 说明绘画+绘画周边为合并行业口径

## skill_generation_contract

- `skill_name`: gongfang-weekly-report
- `skill_title`: Gongfang Weekly Report
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

## acceptance_checks

- `spec_completeness_checks`:
  - 两个栏目均已定义 purpose、views、metrics、dimensions、outputs
  - 四个输入数据合同均已声明文件模式、字段与支持栏目
- `spec_consistency_checks`:
  - 时间定义统一为周五到周四
  - 绘画+绘画周边汇总口径已在 terminology 中声明
  - 输出合同与 HTML 约束一致
- `generation_readiness_checks`:
  - 已有下游 skill 名称
  - 所有栏目都有数据合同支撑
  - 波动阈值已明确
- `html_output_checks`:
  - 输出必须为单一 HTML 主产物
  - HTML 必须包含固定栏目顺序、图表区、结论区、数据说明区
