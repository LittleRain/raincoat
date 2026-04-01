# report-circle-daily

每日读取圈子业务 feed 流和转化数据，生成分析日报 HTML。

## 快速开始

```bash
bash skills/report-circle-daily/scripts/run-report.sh \
  --input-dir /path/to/input \
  --output-dir /path/to/output \
  --run-id circle-daily-2026-04-01
```

## 输入文件说明

见 [examples/input_inventory.md](examples/input_inventory.md)

## Spec 说明

- 入口索引：`examples/normalized-spec.md`
- 执行摘要：`examples/normalized-spec-summary.md`

## 输出

- `report.html`：可直接在浏览器打开的日报
  - 包含总览、圈子内容分析、漫展双路径对比、项目转化分析
  - 表格支持点击表头进行排序（交互）
- `run.log`：执行日志

## 文件结构

```
report-circle-daily/
├── SKILL.md               # skill 定义
├── README.md              # 本文件
├── skill.json             # skill 元数据
├── assets/
│   ├── html-contract.md   # HTML 输出结构合同
│   ├── report-outline.md  # 报告栏目结构
│   └── validation-checklist.md
├── examples/
│   ├── normalized-spec.md # 标准化 spec 索引
│   ├── normalized-spec-summary.md # 标准化 spec 执行摘要
│   ├── input_inventory.md # 输入文件清单样例
│   └── output-outline.html
└── scripts/
    ├── run-report.sh      # 执行入口
    └── generate_report.py # 报告生成器
```
