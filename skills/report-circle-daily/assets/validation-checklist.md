# 验证清单

## Spec 完整性

- [ ] `report_goal` 含 report_name / domain / audience / decision_goals / success_definition
- [ ] `report_outline` 含总览 + 4 个分析栏目（共 5 个）
- [ ] 每个栏目声明了 required_metrics / required_dimensions / required_outputs
- [ ] `data_contracts` 覆盖全部 5 个栏目
- [ ] `output_contract.format` 为 `html`

## Spec 一致性

- [ ] 总览指标（曝光、点击、CTR、互动率）都能在输入数据中计算
- [ ] 绘画/模型/漫展T3 为 PV 口径，票务商详为 UV 口径，未混算
- [ ] 项目转化栏目指标都能在 manzhan-conversion 合同中找到
- [ ] 时间口径统一为昨日

## 生成就绪

- [ ] skill 包含 SKILL.md / README.md / skill.json
- [ ] assets 含 html-contract.md / report-outline.md / validation-checklist.md
- [ ] examples 含 normalized-spec.md / normalized-spec-summary.md / input_inventory.md
- [ ] scripts 含 run-report.sh / generate_report.py

## HTML 输出合同

- [ ] 包含标题区（含日期）
- [ ] 5 个栏目顺序稳定（总览 + 4 个分析）
- [ ] 绘画/模型栏目包含 Top10 表（按曝光排序）和结论
- [ ] 内容表包含标题、副标题、发布时间、链接字段
- [ ] 漫展双路径栏目包含两条路径的 Top10 表和差异结论
- [ ] 漫展转化栏目包含漏斗承接率与代表性项目原因
- [ ] 数据说明区在末尾
