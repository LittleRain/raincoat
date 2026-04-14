# 校验清单

- [x] normalized spec exists
- [x] source requirement exists
- [x] required data contracts are mapped (6个数据合同)
- [x] required sections are present (核心数据趋势 / GMV 拆解 / 流量 拆解)
- [x] output format is HTML
- [x] 核心数据趋势 maps to `整体数据`
- [x] GMV 拆解 maps to `行业数据`, `行业商品明细数据`, `商家销售明细数据`, `内容渠道数据`
- [x] 流量 拆解 maps to `内容渠道数据`, `资源位二级入口数据`
- [x] section order matches normalized spec
- [x] key goods narratives explicitly state 上涨 / 下跌 / 持平
- [x] channel tables include GMV / 买家数 / 下单转化率 and WoW for each metric
- [x] shop top5 tables include WoW per metric and GMV share
- [x] product top10 tables include WoW per metric
- [x] dual-axis charts render for 内容渠道 and 资源位二级入口
- [x] all chart axes start at zero (axis_origin_policy: start-at-zero)
- [x] scripts/run-report.sh exists
- [x] scripts/requirements.txt exists
