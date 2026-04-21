# 工房业务交易双周周报需求 normalized spec

## report_goal
- report_name: 工房业务交易双周周报需求
- domain: 工房交易
- audience: 待确认
- decision_goals: 基于一个内容电商平台，做一个交易业务双周周报。基于本文档描述的业务背景、数据源、分析逻辑输出一个可交互的html

**业务介绍：** 这是一个用户个人开店，平台提供交易工具和流量给用户成交，重点品类有绘画、VUP周边、绘画周边、知识&服务、手工，重点流量渠道有商品、视频、动态、直播
- success_definition: 每个章节按声明图表/表格完整输出，并使用声明证据完成归因。

## business_context
基于一个内容电商平台，做一个交易业务双周周报。基于本文档描述的业务背景、数据源、分析逻辑输出一个可交互的html

**业务介绍：** 这是一个用户个人开店，平台提供交易工具和流量给用户成交，重点品类有绘画、VUP周边、绘画周边、知识&服务、手工，重点流量渠道有商品、视频、动态、直播

## terminology
名词定义：

- **核心成交体裁**：根据表格中的"内容类型"字段区分，分别为：商品、视频、动态、直播、其他
- **流量渠道**：商品-商品feed流场域、视频-内容场域的视频带货、动态-内容场域的图文内容带货、直播-直播间带货
- **行业**：绘画、VUP周边、绘画周边、知识&服务、手工、极客创造、手办模玩，重点是绘画、VUP周边

## time_definition
时间段定义:

- 每周五到周四，对比当周和上周，如：
  - 本周 12 周（3月13日 ~ 3月19日）
  - 上周 11 周（3月6日 ~ 3月12日）

## report_outline
### s1: ① 核心数据趋势
- purpose: 看清交易规模变化 by周
- data_contracts: 文档1
- required_metrics: GMV、订单数、买家数、支付转化率、下单转化率、商品曝光PV
- charts_count: 4
- tables_count: 0
- charts:
    - name: GMV 周维度变化
      type: 柱状图
      source: 文档1
      description: GMV 周维度变化
      x_axis: 周
      y_axis: GMV
      split_rule: 
    - name: 买家数 周维度变化
      type: 柱状图
      source: 文档1
      description: 买家数 周维度变化
      x_axis: 周
      y_axis: 买家数
      split_rule: 
    - name: 下单转化率 周维度变化
      type: 折线图
      source: 文档1
      description: 下单转化率 周维度变化
      x_axis: 周
      y_axis: 转化率
      split_rule: 
    - name: 商品曝光PV 周维度变化
      type: 折线图
      source: 文档1
      description: 商品曝光PV 周维度变化
      x_axis: 周
      y_axis: 商品曝光PV
      split_rule: 
- tables:
    []
- attribution_rules: 波动超过5%的指标（GMV、订单数、买家数、支付转化率）

---
- empty_value_policy: 关键维度为空时阻塞；数值为空按 0 或缺失说明处理，需人工确认。

### s2: ② GMV 拆解
- purpose: 了解每个行业及类目的交易规模的变化趋势，得出 GMV 波动的原因分析
- data_contracts: 文档2、文档5、文档3
- required_metrics: GMV、买家数、下单转化率、商品曝光PV
- charts_count: 4
- tables_count: 4
- charts:
    - name: GMV by行业
      type: 折线图
      source: 文档2
      description: GMV by行业
      x_axis: 周
      y_axis: GMV
      split_rule: 行业
    - name: 买家数 by行业
      type: 折线图
      source: 文档2
      description: 买家数 by行业
      x_axis: 周
      y_axis: 买家数
      split_rule: 行业
    - name: 下单转化率 by行业
      type: 折线图
      source: 文档2
      description: 下单转化率 by行业
      x_axis: 周
      y_axis: 转化率
      split_rule: 行业
    - name: 商品曝光PV by行业
      type: 折线图
      source: 文档2
      description: 商品曝光PV by行业
      x_axis: 周
      y_axis: 商品曝光PV
      split_rule: 行业
- tables:
    - name: 展示行业（绘画）下，本周GMV top5的商家，字段：店铺名称、GMV、GMV占行业整体GMV的占比、买家数、下单转化率、商品曝光PV，拆解2周，每个指标增加周环比
      source: 文档5
      description: 展示行业（绘画）下，本周GMV top5的商家，字段：店铺名称、GMV、GMV占行业整体GMV的占比、买家数、下单转化率、商品曝光PV，拆解2周，每个指标增加周环比
      columns: 店铺名称、GMV、GMV占行业整体GMV的占比、买家数、下单转化率、商品曝光PV，拆解2周，每个指标增加周环比
      sort_rule: top5
    - name: 展示行业（绘画）下，本周GMV top10的商品，字段：商品名称、GMV、买家数、下单转化率、商品曝光PV，拆解2周，每个指标增加周环比
      source: 文档3
      description: 展示行业（绘画）下，本周GMV top10的商品，字段：商品名称、GMV、买家数、下单转化率、商品曝光PV，拆解2周，每个指标增加周环比
      columns: 商品名称、GMV、买家数、下单转化率、商品曝光PV，拆解2周，每个指标增加周环比
      sort_rule: top10
    - name: 展示行业（VUP周边）下，本周GMV top5的商家，字段：店铺名称、GMV、GMV占行业整体GMV的占比、买家数、下单转化率、商品曝光PV，拆解2周，每个指标增加周环比
      source: 文档5
      description: 展示行业（VUP周边）下，本周GMV top5的商家，字段：店铺名称、GMV、GMV占行业整体GMV的占比、买家数、下单转化率、商品曝光PV，拆解2周，每个指标增加周环比
      columns: 店铺名称、GMV、GMV占行业整体GMV的占比、买家数、下单转化率、商品曝光PV，拆解2周，每个指标增加周环比
      sort_rule: top5
    - name: 展示行业（VUP周边）下，本周GMV top10的商品，字段：商品名称、GMV、买家数、下单转化率、商品曝光PV，拆解2周，每个指标增加周环比
      source: 文档3
      description: 展示行业（VUP周边）下，本周GMV top10的商品，字段：商品名称、GMV、买家数、下单转化率、商品曝光PV，拆解2周，每个指标增加周环比
      columns: 商品名称、GMV、买家数、下单转化率、商品曝光PV，拆解2周，每个指标增加周环比
      sort_rule: top10
- attribution_rules: - 绘画行业汇总之后，当周环比波动超过5%的指标有哪些，利用表格1和表格2的数据来分析是不是头部商家变化导致的，如果是，结合表格2看变化的因素是什么，可以从买家转化或获得的商品流量角度分析

**图表：**

| 图表类型 | 维度 | 内容 | 数据源 |
|--------|------|------|------|
| 表格3 | 店铺名称 | 展示行业（VUP周边）下，本周GMV top5的商家，字段：店铺名称、GMV、GMV占行业整体GMV的占比、买家数、下单转化率、商品曝光PV，拆解2周，每个指标增加周环比 | 文档5 |
| 表格4 | 商品名称 | 展示行业（VUP周边）下，本周GMV top10的商品，字段：商品名称、GMV、买家数、下单转化率、商品曝光PV，拆解2周，每个指标增加周环比 | 文档3 |

**得出结论：**

- VUP周边，当周环比波动超过5%的指标有哪些，利用表格3和表格4的数据来分析是不是头部商家变化导致的，如果是，结合表格4看变化的因素是什么，可以从买家转化或获得的商品流量角度分析
- empty_value_policy: 关键维度为空时阻塞；数值为空按 0 或缺失说明处理，需人工确认。

### s3: ③ 流量 拆解
- purpose: 了解每个行业及类目的流量渠道转化趋势，得出 流量波动的原因分析
- data_contracts: 文档4、文档6
- required_metrics: GMV、商品曝光PV、PVCTR、CTR
- charts_count: 8
- tables_count: 4
- charts:
    - name: 行业（绘画）取GMV前2的内容渠道，每个内容渠道展示GMV（柱状图）、GMV占整体GMV的占比(折线图) by内容渠道，分两个轴，过去4周
      type: 组合图表
      source: 文档4
      description: 行业（绘画）取GMV前2的内容渠道，每个内容渠道展示GMV（柱状图）、GMV占整体GMV的占比(折线图) by内容渠道，分两个轴，过去4周
      x_axis: 周
      y_axis: GMV
      split_rule: 前2
    - name: 行业（绘画）取GMV前2的内容渠道，每个内容渠道展示商品曝光PV（柱状图）、商品曝光PV占整体商品曝光PV的占比(折线图) ，分两个轴，by内容渠道，过去4周
      type: 组合图表
      source: 文档4
      description: 行业（绘画）取GMV前2的内容渠道，每个内容渠道展示商品曝光PV（柱状图）、商品曝光PV占整体商品曝光PV的占比(折线图) ，分两个轴，by内容渠道，过去4周
      x_axis: 周
      y_axis: GMV、商品曝光PV
      split_rule: 前2
    - name: 行业（绘画）取GMV前4的资源位二级入口，每个资源位二级入口展示GMV（柱状图）、GMV占整体GMV的占比(折线图) by资源位二级入口，分两个轴，过去4周
      type: 组合图表
      source: 文档6
      description: 行业（绘画）取GMV前4的资源位二级入口，每个资源位二级入口展示GMV（柱状图）、GMV占整体GMV的占比(折线图) by资源位二级入口，分两个轴，过去4周
      x_axis: 周
      y_axis: GMV
      split_rule: 前4
    - name: 行业（绘画）取GMV前4的资源位二级入口，每个资源位二级入口展示商品曝光PV（柱状图）、商品曝光PV占整体商品曝光PV的占比(折线图)，分两个轴，by资源位二级入口，过去4周
      type: 组合图表
      source: 文档6
      description: 行业（绘画）取GMV前4的资源位二级入口，每个资源位二级入口展示商品曝光PV（柱状图）、商品曝光PV占整体商品曝光PV的占比(折线图)，分两个轴，by资源位二级入口，过去4周
      x_axis: 周
      y_axis: GMV、商品曝光PV
      split_rule: 前4
    - name: 行业（VUP周边）的GMV（柱状图）、GMV占整体GMV的占比(折线图) by内容渠道，分两个轴，过去4周
      type: 组合图表
      source: 文档4
      description: 行业（VUP周边）的GMV（柱状图）、GMV占整体GMV的占比(折线图) by内容渠道，分两个轴，过去4周
      x_axis: 周
      y_axis: GMV
      split_rule: 内容渠道，分两个轴，过去4周
    - name: 行业（VUP周边）的商品曝光PV（柱状图）、商品曝光PV占整体商品曝光PV的占比(折线图) ，分两个轴，by内容渠道，过去4周
      type: 组合图表
      source: 文档4
      description: 行业（VUP周边）的商品曝光PV（柱状图）、商品曝光PV占整体商品曝光PV的占比(折线图) ，分两个轴，by内容渠道，过去4周
      x_axis: 周
      y_axis: 商品曝光PV
      split_rule: 内容渠道，过去4周
    - name: 行业（VUP周边）的GMV（柱状图）、GMV占整体GMV的占比(折线图) by资源位二级入口，分两个轴，过去4周
      type: 组合图表
      source: 文档6
      description: 行业（VUP周边）的GMV（柱状图）、GMV占整体GMV的占比(折线图) by资源位二级入口，分两个轴，过去4周
      x_axis: 周
      y_axis: GMV
      split_rule: 资源位二级入口，分两个轴，过去4周
    - name: 行业（VUP周边）的商品曝光PV（柱状图）、商品曝光PV占整体商品曝光PV的占比(折线图)，分两个轴，by资源位二级入口，过去4周
      type: 组合图表
      source: 文档6
      description: 行业（VUP周边）的商品曝光PV（柱状图）、商品曝光PV占整体商品曝光PV的占比(折线图)，分两个轴，by资源位二级入口，过去4周
      x_axis: 周
      y_axis: 商品曝光PV
      split_rule: 资源位二级入口，过去4周
- tables:
    - name: 行业（绘画）下，每个内容渠道的GMV（4周）、GMV占整体GMV的占比（本周）、商品曝光PV（4周）、商品曝光PV占整体商品曝光PV的占比（本周）、PVCTR（4周）
      source: 文档4
      description: 行业（绘画）下，每个内容渠道的GMV（4周）、GMV占整体GMV的占比（本周）、商品曝光PV（4周）、商品曝光PV占整体商品曝光PV的占比（本周）、PVCTR（4周）
      columns: 
      sort_rule: 
    - name: 行业（绘画）下，每个资源位二级入口的GMV（4周）、GMV占整体GMV的占比（本周）、商品曝光PV（4周）、商品曝光PV占整体商品曝光PV的占比（本周）、PVCTR（4周）
      source: 文档6
      description: 行业（绘画）下，每个资源位二级入口的GMV（4周）、GMV占整体GMV的占比（本周）、商品曝光PV（4周）、商品曝光PV占整体商品曝光PV的占比（本周）、PVCTR（4周）
      columns: 
      sort_rule: 
    - name: 行业（VUP周边）下，每个内容渠道的GMV（4周）、GMV占整体GMV的占比（本周）、商品曝光PV（4周）、商品曝光PV占整体商品曝光PV的占比（本周）、PVCTR（4周）
      source: 文档4
      description: 行业（VUP周边）下，每个内容渠道的GMV（4周）、GMV占整体GMV的占比（本周）、商品曝光PV（4周）、商品曝光PV占整体商品曝光PV的占比（本周）、PVCTR（4周）
      columns: 
      sort_rule: 
    - name: 行业（VUP周边）下，每个资源位二级入口的GMV（4周）、GMV占整体GMV的占比（本周）、商品曝光PV（4周）、商品曝光PV占整体商品曝光PV的占比（本周）、PVCTR（4周）
      source: 文档6
      description: 行业（VUP周边）下，每个资源位二级入口的GMV（4周）、GMV占整体GMV的占比（本周）、商品曝光PV（4周）、商品曝光PV占整体商品曝光PV的占比（本周）、PVCTR（4周）
      columns: 
      sort_rule: 
- attribution_rules: - 绘画行业汇总之后，当周GMV环比波动超过5%的内容渠道有哪些，结合文档4的流量侧、交易侧数据和表格2的数据分析波动的原因，如流量曝光降低、流量转化率降低、卖家转化率降低、某个资源位二级入口的曝光下降较多
- 绘画行业汇总之后，当周GMV环比波动超过5%的资源位二级入口有哪些，利用文档6的流量侧、交易侧数据分析波动的原因，如流量曝光降低、流量转化率降低、卖家转化率降低

**图表：**

| 图表类型 | 维度 | 内容 | 数据源 |
|--------|------|------|------|
| 组合图表 | 周 | 行业（VUP周边）的GMV（柱状图）、GMV占整体GMV的占比(折线图) by内容渠道，分两个轴，过去4周 | 文档4 |
| 组合图表 | 周 | 行业（VUP周边）的商品曝光PV（柱状图）、商品曝光PV占整体商品曝光PV的占比(折线图) ，分两个轴，by内容渠道，过去4周 | 文档4 |
| 表格1 | 内容渠道 | 行业（VUP周边）下，每个内容渠道的GMV（4周）、GMV占整体GMV的占比（本周）、商品曝光PV（4周）、商品曝光PV占整体商品曝光PV的占比（本周）、PVCTR（4周） | 文档4 |
| 组合图表 | 周 | 行业（VUP周边）的GMV（柱状图）、GMV占整体GMV的占比(折线图) by资源位二级入口，分两个轴，过去4周 | 文档6 |
| 组合图表 | 周 | 行业（VUP周边）的商品曝光PV（柱状图）、商品曝光PV占整体商品曝光PV的占比(折线图)，分两个轴，by资源位二级入口，过去4周 | 文档6 |
| 表格2 | 资源位二级入口 | 行业（VUP周边）下，每个资源位二级入口的GMV（4周）、GMV占整体GMV的占比（本周）、商品曝光PV（4周）、商品曝光PV占整体商品曝光PV的占比（本周）、PVCTR（4周） | 文档6 |

**得出结论：**

- VUP周边行业，当周GMV环比波动超过5%的内容渠道有哪些，结合文档4的流量侧、交易侧数据和表格2的数据分析波动的原因，如流量曝光降低、流量转化率降低、卖家转化率降低、某个资源位二级入口的曝光下降较多
- VUP周边行业，当周GMV环比波动超过5%的资源位二级入口有哪些，利用文档6的流量侧、交易侧数据分析波动的原因，如流量曝光降低、流量转化率降低、卖家转化率降低
- empty_value_policy: 关键维度为空时阻塞；数值为空按 0 或缺失说明处理，需人工确认。

## data_contracts
### doc1: 1. 整体数据
- file_name_pattern: 整体数据
- required: true
- fields: 周五-周四周	PVCTR 商品曝光PV 商详UV	支付订单数	支付订单买家数	GMV（不减退款）	商详支付转化率-UV	GPM
- description: 

### doc2: 2. 行业整体数据
- file_name_pattern: 行业数据
- required: true
- fields: 周五-周四周	后台一级类目名称	商品曝光PV	PVCTR	商详UV	支付订单数	支付订单买家数	GMV（不减退款）	商详支付转化率-UV	GPM
- description: 内容类型=内容渠道；后台一级类目名称=行业

### doc3: 3. 行业商品明细数据
- file_name_pattern: 行业商品明细数据
- required: true
- fields: 周五-周四周 商品名称 店铺名称 后台一级类目名称	商品曝光PV	PVCTR	商详UV	支付订单数	支付订单买家数	GMV（不减退款）	商详支付转化率-UV	GPM
- description: 后台一级类目名称=行业；含本周和上周的数据

### doc4: 4. 内容渠道数据
- file_name_pattern: 内容渠道数据
- required: true
- fields: 周五-周四周	后台一级类目名称	内容类型	商品曝光PV	PVCTR	商详UV	支付订单数	支付订单买家数	GMV（不减退款）	商详支付转化率-UV	GPM
- description: 内容类型=内容渠道；后台一级类目名称=行业

### doc5: 5. 商家销售明细数据
- file_name_pattern: 商家销售明细
- required: true
- fields: 周五-周四周 后台一级类目名称 店铺名称	商品曝光PV	PVCTR	商详UV	支付订单数	支付订单买家数	GMV（不减退款）	商详支付转化率-UV	GPM
- description: 内容类型=内容渠道；后台一级类目名称=行业

### doc6: 6. 资源位二级入口数据
- file_name_pattern: 资源位二级入口数据
- required: true
- fields: 周五-周四周	后台一级类目名称	内容类型 资源位二级入口	商品曝光PV	PVCTR	商详UV	支付订单数	支付订单买家数	GMV（不减退款）	商详支付转化率-UV	GPM
- description: 内容类型=内容渠道；后台一级类目名称=行业

## output_contract
- format: html
- expected_output_inventory: see expected-output-inventory.json

## next_stage
- deliverable: downstream report skill
- execution_design_required: true
- sample_test_required_for_L1_L2: true
- tuning_backflow_rule: business-specific fixes stay downstream; reusable failure patterns go back to create-report