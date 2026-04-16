# 校验清单

## Spec 完整性

- [x] normalized spec 存在（`examples/normalized-spec-summary.md`）
- [x] 原始需求存在（`docs/skills/工房业务交易双周报需求.md`）
- [x] 6 个数据合同已映射（整体数据/行业数据/行业商品明细数据/内容渠道数据/商家销售明细/资源位二级入口数据）
- [x] 3 个栏目已定义（核心数据趋势 / GMV 拆解 / 流量拆解）
- [x] 栏目顺序与 spec 一致
- [x] 表格 schema 已定义（商家TOP5 / 商品TOP10 / 内容渠道 / 资源位入口）
- [x] 比率指标口径已声明（转化率=支付订单数/商详UV, PVCTR=商详UV/曝光PV, GPM=GMV/曝光PV×1000）
- [x] 指标格式规则已定义（率值→pct, 金额→gmv, 人数→num, 量级→pv）

## 样式合规

- [x] `output-outline.html` 内联了 `base-report.css` 完整内容
- [x] 使用 base-report.css 标准 CSS class（未自行发明替代样式）
- [x] 报告头使用 `.hero` 组件
- [x] 导航使用 `.nav` 锚点模式（滚动+sticky）
- [x] 指标卡使用 `.metric-grid` + `.metric-card`
- [x] 图表容器使用 `.chart-container` + `.chart-area`
- [x] 结论框使用 `.conclusion` 组件
- [x] 数据说明使用 `.footnote` 组件
- [x] 表格数值列使用 `.num` 右对齐
- [x] 表格自动启用 tnum（font-feature-settings）

## 图表合规

- [ ] Chart.js 4.x 内联（非 CDN）
- [ ] chart-defaults.js 内联且位于 Chart.js 之后
- [ ] 图表使用 `chartPresets` / `reportChart` API
- [ ] 双轴组合图右轴网格线隐藏
- [ ] 双轴组合图折线颜色与柱状图对比
- [ ] `file://` 直接打开时图表可渲染
- [ ] 使用 `REPORT_PALETTE` 10 色数组

## 运行时合规

- [x] `scripts/run-report.sh` 存在
- [x] `scripts/requirements.txt` 存在
- [x] 已用真实样本执行一次生成
- [x] 执行日志包含文件匹配、读取状态
- [x] 日志支持 INFO / WARN / ERROR 层级
- [x] 生成的 HTML 栏目顺序与 spec 一致
- [x] 商家 TOP5 表含 GMV 占比 + 每指标环比
- [x] 商品 TOP10 表含每指标环比
- [x] 结论文本明确写出 上涨/下跌/持平
- [x] 双轴图用于内容渠道和资源位二级入口
