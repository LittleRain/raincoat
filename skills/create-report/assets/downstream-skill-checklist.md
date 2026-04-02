# 下游 Skill 检查清单

## 通用

- 存在 `SKILL.md`
- 存在 `agents/openai.yaml`
- 存在 `assets/html-contract.md`
- 存在 `assets/report-outline.md`
- 存在 `assets/report-prompt.md`
- 存在 `assets/validation-checklist.md`
- 存在 `examples/normalized-spec.md`
- 存在 `examples/normalized-spec-summary.md`
- 存在 `examples/input_inventory.md`
- 存在 `examples/output-outline.html`
- 已明确本 skill 是 `documentation-only` 还是 `runnable`
- 已定义首次生成后不符合预期时的调整入口或记录方式
- 输入合同已经写入 `SKILL.md`、`examples/` 或 `references/`
- `SKILL.md` 只引用 skill 包内部相对路径，或完全不依赖外部路径
- `assets/` 和 `examples/` 不引用仓库外部绝对路径
- 不包含 `__pycache__`、运行产物或其他本地缓存文件

## 对外发布额外检查

- 全包不依赖上游 `create-report`、`report-creator` 或原始需求文档路径
- 输入合同已经内嵌到 `SKILL.md`、`examples/` 或 `references/` 中，包本身可独立理解

## `runnable` 额外检查

- 存在 `scripts/run-report.sh`
- 存在 `scripts/requirements.txt`
- `scripts/run-report.sh` 实际调用真实渲染逻辑，而不是直接写 placeholder HTML
- 至少存在 1 个最小回归测试脚本
- 已用真实样本执行一次生成
- 生成出的 HTML 包含 spec 要求的关键图表 / 表格 / 结论区
- 若 spec 声明表格 schema，则输出列名与 schema 一致
- 若 spec 声明 narrative schema，则结论文本符合 schema
