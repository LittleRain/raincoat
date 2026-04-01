# 验证清单

## Spec 完整性

- [ ] `report_goal` 含 report_name / domain / audience / decision_goals / success_definition
- [ ] `report_outline` 含全部 5 个栏目
- [ ] 每个栏目声明了 required_metrics / required_dimensions / required_outputs
- [ ] `data_contracts` 覆盖全部 5 个栏目
- [ ] `output_contract.format` 为 `html`

## Spec 一致性

- [ ] 绘画圈/模型圈/漫展圈T3 栏目指标能在对应 feed 数据合同中找到
- [ ] 漫展转化栏目指标能在 manzhan-conversion 合同中找到
- [ ] 路径对比栏目指标分 PV 口径（T3）和 UV 口径（票务商详）分别声明
- [ ] 时间口径统一为昨日

## 生成就绪

- [ ] skill 包含 SKILL.md / README.md / skill.json
- [ ] assets 含 html-contract.md / report-outline.md / validation-checklist.md
- [ ] examples 含 normalized-spec.md / normalized-spec-summary.md / input_inventory.md
- [ ] scripts 含 run-report.sh / generate_report.py

## HTML 输出合同

- [ ] 包含标题区（含日期）
- [ ] 5 个栏目顺序稳定
- [ ] 每个圈子栏目含 Top 内容表 + 特征结论
- [ ] 漫展转化栏目含项目表 + 转化结论
- [ ] 路径对比栏目含双路径表 + 差异结论
- [ ] 数据说明区在末尾
