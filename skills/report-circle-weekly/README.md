# Report Circle Weekly

这是一个面向圈子业务周报的执行型 skill，用于按照
[圈子业务周报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/圈子业务周报需求.md)
读取指定 Excel/CSV 数据并生成最终 HTML 周报。

## 它做什么

这个 skill 不是用来补需求的，而是直接按既定业务需求执行周报生成。

它会基于：

- 业务需求文档
- 输入数据文件
- 固定栏目结构

来输出一份结构稳定的 HTML 周报。

## 如何使用

当前这版 `report-circle-weekly` 已经同时支持两种用法：

### 用法 1：作为 agent skill 使用

把以下材料一起提供给 agent：

- [圈子业务周报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/圈子业务周报需求.md)
- 你的真实周报数据文件
- [examples/input_inventory.md](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-weekly/examples/input_inventory.md)
  作为文件清单参考

然后让 agent 使用 `report-circle-weekly`，并明确要求：

- 按 `assets/report-outline.md` 的栏目顺序生成
- 按 `assets/report-prompt.md` 的规则输出
- 最终写出一个 `report.html`

### 用法 2：直接跑脚本生成 HTML

如果你已经确认业务需求文档就是本次周报的执行基准，可以直接运行：

```bash
bash skills/report-circle-weekly/scripts/run-report.sh \
  --input-dir /你的数据目录 \
  --output-dir /你的输出目录 \
  --run-id circle-weekly-2026w12
```

运行完成后，主要产物是：

- `/你的输出目录/report.html`
- `/你的输出目录/run.log`

脚本依赖见：
[requirements.txt](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-weekly/scripts/requirements.txt)

### 用法 3：如有需要，再回到上游 `create-report`

如果你担心需求或口径变化，可以先用
[create-report](/Users/raincai/Documents/GitHub/raincoat/skills/create-report)
重新校验需求，再交给 `report-circle-weekly` 产出 HTML。

## 最小操作步骤

1. 准备好本周所需数据文件，文件形态对齐
   [input_inventory.md](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-weekly/examples/input_inventory.md)
2. 确认本次按
   [圈子业务周报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/圈子业务周报需求.md)
   执行
3. 让 agent 激活 `report-circle-weekly`，或直接运行脚本
4. 明确输出路径，例如 `output/report.html`
5. 检查生成结果是否满足
   [assets/html-contract.md](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-weekly/assets/html-contract.md)
   和
   [assets/validation-checklist.md](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-weekly/assets/validation-checklist.md)

## 目录结构

- `SKILL.md`
  - agent 工作流说明
- `skill.json`
  - 元数据
- `assets/`
  - HTML 合同、栏目结构、提示词、校验清单
- `examples/`
  - spec 参考、输入文件清单、输出 HTML 样例
- `scripts/`
  - 当前仅放置脚本说明

## 当前状态

当前状态：`draft`

这已经是第一版带脚本执行能力的圈子业务周报下游 skill 包。
当前脚本可以直接读取输入目录并生成 `report.html`，但后续仍可以继续补：

- 更严格的输入文件校验
- 更稳定的依赖锁定
- 更标准的 `tools/reports` 场景注册
