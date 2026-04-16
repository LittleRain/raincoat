# 标准化 Spec 参考

本 skill 为独立发布包，不依赖仓库外部 spec 文件。

执行时默认优先读取：
- `examples/normalized-spec-summary.md` — 标准化 spec 摘要（含数据合同、栏目定义、分析规则）
- `assets/report-outline.md` — 详细栏目结构（含图表/表格 schema）
- `assets/html-contract.md` — HTML 输出合同（含样式合同、图表合同、数据合同）
- `assets/report-prompt.md` — 生成 prompt（含样式规则、图表规则、数据规则）

仅在字段口径冲突或合同不一致时，回到本 skill 内的资产文件逐条核对。

## 设计系统依赖

本 skill 使用 `create-report` 标准化设计系统：
- CSS: `base-report.css`（Linear 暗色 + Stripe 数据精度混合体系）
- Chart: `chart-defaults.js`（Chart.js 4.x 标准配置 + chartPresets API）
- 设计参考: `DESIGN.md`（颜色体系、排版、组件规范）
