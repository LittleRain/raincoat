# 圈子业务日报生成记录

## 目标

使用周报生产器 skill `create-report` 与源需求文档
[圈子业务日报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/圈子业务日报需求.md)，
生成一个正式的下游日报 skill：
[report-circle-daily](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-daily)。

## 输入

- 原始业务需求：`docs/skills/圈子业务日报需求.md`
- `create-report` 产品文档和 spec 文档（`docs/skills/report-creator/`）
- 标准化 spec：`skills/report-circle-daily/examples/normalized-spec.md`

## create-report 流程执行记录

### Phase 1: Intake

读取 `圈子业务日报需求.md`，识别：
- 报告类型：日报，日粒度
- 5 张输入表，by 不同圈子和路径
- 3 个分析课题（by 圈子内容质量，漫展项目转化，漫展路径差异）

### Phase 2: Extraction

提取业务事实：
- 读者：圈子业务运营/分析同学
- 用户路径：T3 入口（主动访问）、票务商详（意图明确）
- 关键指标：PV 口径（绘画/模型/漫展T3）、UV 口径（票务商详路径）
- 时间定义：昨日数据

### Phase 3: Clarification

无追问项——所有栏目有数据合同支撑，指标字段来源明确，时间定义清晰。

### Phase 4: Normalization

生成标准化 spec：`skills/report-circle-daily/examples/normalized-spec.md`

关键映射决策：
- T3 和票务商详路径的漫展圈 feed 文件分开为两个数据合同（PV/UV 口径不同）
- `manzhan-content-diff` 栏目同时依赖 `feed-manzhan-t3` 和 `feed-manzhan-ticket`
- 漫展项目转化分析的访问量筛选规则：取商详浏览 UV 前 50%，至少保留 3 个项目

### Phase 5: Validation

全部验证通过：
- ✅ `report_goal` 完整（5 个必填字段）
- ✅ 5 个栏目均有数据合同覆盖
- ✅ 所有指标有字段来源
- ✅ 时间定义：daily，昨日
- ✅ `output_contract.format` = html
- ✅ `skill_generation_contract` 完整
- ✅ 无未解决追问项

### Phase 6: Generation

生成 skill 包结构：

```
skills/report-circle-daily/
├── SKILL.md
├── README.md
├── skill.json
├── report.html            ← 测试运行产物
├── assets/
│   ├── html-contract.md
│   ├── report-outline.md
│   └── validation-checklist.md
├── examples/
│   ├── normalized-spec.md
│   ├── input_inventory.md
│   └── output-outline.html
└── scripts/
    ├── run-report.sh
    └── generate_report.py
```

## 测试运行

测试脚本：`tooling/tests/report-circle-daily.sh`

运行结果：

```
✅ 报告已生成: report.html（14 KB）
✅ 所有校验通过（6 个 section，19 个关键字验证）
```

## 验证

- `report-circle-daily` 包含所有 required files、assets、examples、scripts
- `scripts/run-report.sh` 支持 `--input-dir --output-dir --run-id` 合同
- HTML 输出包含 5 个需求栏目 + 数据说明区
- 漫展圈额外输出：项目转化分析（S4）、路径内容偏好对比（S5）

## 首次生成后定向调整记录

该日报 skill 在首次生成后经历了“结论深度增强 + 稳定性修复”的定向调整，
完整复盘见：

- [circle-daily-adjustment-retro.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/report-creator/examples/circle-daily-adjustment-retro.md)
