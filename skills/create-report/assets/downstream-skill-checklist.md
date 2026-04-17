# 下游 Skill 检查清单

## 通用

- 存在 `SKILL.md`
- 存在 `agents/openai.yaml`
- 存在 `assets/html-contract.md`
- 存在 `assets/report-outline.md`
- 存在 `assets/report-prompt.md`
- 存在 `assets/validation-checklist.md`
- 存在 `assets/acceptance-matrix.md`
- 存在 `examples/normalized-spec.md`
- 存在 `examples/normalized-spec-summary.md`
- 存在 `examples/input_inventory.md`
- 存在 `examples/expected-output-inventory.json`
- 存在 `examples/semantic-contract.json`
- 存在 `examples/table-layout-contract.json`
- 存在 `examples/output-outline.html`
- 已明确本 skill 是 `L0 Documentation`、`L1 Runnable MVP` 还是 `L2 Publishable`
- 存在 `skill-manifest.yaml`
- `skill-manifest.yaml` 声明 `declared_level`、`effective_level`、`acceptance_status`、`acceptance_evidence`
- 已定义首次生成后不符合预期时的调整入口或记录方式
- 输入合同已经写入 `SKILL.md`、`examples/` 或 `references/`
- `SKILL.md` 只引用 skill 包内部相对路径，或完全不依赖外部路径
- `assets/` 和 `examples/` 不引用仓库外部绝对路径
- 不包含 `__pycache__`、运行产物或其他本地缓存文件

## 样式合规

- `output-outline.html` 内联了 `create-report/assets/base-report.css` 完整内容
- 使用 base-report.css 定义的标准 CSS class 构建页面
- 未自行发明替代样式系统（如自定义变量名、自定义 class 命名）
- 报告头使用 `.hero` 组件
- 导航使用 `.nav` 锚点模式（滚动+sticky）
- 指标卡使用 `.metric-grid` + `.metric-card`
- 图表容器使用 `.chart-container` + `.chart-area`
- 结论框使用 `.conclusion` 组件
- 数据说明使用 `.footnote` 组件
- 表格数值列自动启用 tnum（已内置于 table 样式）

## 对外发布额外检查

- 全包不依赖上游 `create-report`、`report-creator` 或原始需求文档路径
- 输入合同已经内嵌到 `SKILL.md`、`examples/` 或 `references/` 中，包本身可独立理解

## `L0 Documentation` 额外检查

- 已明确不可声明 runnable 输出
- placeholder HTML 没有作为执行证据
- `scripts/run-report.sh` 若存在，必须明确是文档 stub 并失败退出
- `blocking_gaps` 已记录真实样本、真实 runner、浏览器验证等缺口

## `L1 Runnable MVP` 额外检查

- 存在 `scripts/run-report.sh`
- 存在 `scripts/requirements.txt`
- `scripts/run-report.sh` 实际调用真实渲染逻辑，而不是直接写 placeholder HTML
- 至少存在 1 个最小回归测试脚本
- 已用真实样本执行一次生成
- 若一个 section 由多个数据源支撑，已定义主数据源与回退顺序
- 关键比率指标（如 CTR）已声明主口径与缺字段回退口径
- 执行日志包含文件匹配、读取状态、关键处理阶段摘要
- 日志在执行过程中实时输出，而不是仅结束后一次性输出
- 日志至少包含 `INFO` / `WARN` / `ERROR` 语义层级
- 生成出的 HTML 内联了 base-report.css 完整内容
- 生成出的 HTML 内联了 Chart.js 4.x（非 CDN 引用）
- 生成出的 HTML 内联了 chart-defaults.js
- 图表使用 chartPresets / reportChart API 创建
- `file://` 直接打开时图表可渲染
- `scripts/validate-output-inventory.py` 校验生成 HTML 的图表、表格数量、`required_metrics`、`required_dimensions` 和 `required_text` 与 `expected-output-inventory.json` 一致
- 表格按需求文档中的业务场景口径渲染，例如行业、分类、业务线、渠道、内容类型
- `semantic-contract.json` 中的 hard constraint 业务词、别名、分组规则和 semantic_examples 已被执行
- `table-layout-contract.json` 中的 layout_mode 已被执行，未把“按维度拆分”误解成错误的多表或单表
- `judgment_metrics` 可由大模型选择展示，不作为强制出现项；若展示，需标记 inferred/judgment-based 口径
- 若 spec 声明表格 schema，则输出列名与 schema 一致
- 若 spec 要求隐藏全空周期列，渲染结果中对应空列已自动隐藏
- 若 spec 声明 narrative schema，则结论文本符合 schema

## `L2 Publishable` 额外检查

- 满足全部 `L1` 检查
- 全包不依赖上游 repo-only 路径或绝对路径
- 图表运行时本地打包或内联，禁止 required CDN
- `file://` 浏览器验证通过
- 浏览器 console 无 blocking error
- 存在回归测试，覆盖缺失值、分母为 0、fallback 路径
- 存在 `output/browser-validation.json` 或等价证据
