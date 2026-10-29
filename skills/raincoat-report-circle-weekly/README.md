# Report Circle Weekly

这是一个面向圈子业务周报的执行型 skill，用于按照
[圈子业务周报需求.md](references/business-requirement.md)
读取指定 Excel/CSV 数据并生成最终 HTML 周报。

## 它做什么

这个 skill 不是用来补需求的，而是直接按既定业务需求执行周报生成。

它会基于：

- 业务需求文档
- 输入数据文件
- 固定栏目结构

来输出一份结构稳定的 HTML 周报。

## 如何使用

当前这版 `raincoat-report-circle-weekly` 已经同时支持两种用法：

### 用法 1：作为 agent skill 使用

把以下材料一起提供给 agent：

- [圈子业务周报需求.md](references/business-requirement.md)
- 你的真实周报数据文件
- [examples/input_inventory.md](examples/input_inventory.md)
  作为文件清单参考

然后让 agent 使用 `raincoat-report-circle-weekly`，并明确要求：

- 按 `assets/report-outline.md` 的栏目顺序生成
- 按 `assets/report-prompt.md` 的规则输出
- 最终写出一个 `report.html`

### 用法 2：直接跑脚本生成 HTML

如果你已经确认业务需求文档就是本次周报的执行基准，可以直接运行：

```bash
python skills/raincoat-report-circle-weekly/scripts/generate_report.py --dir /你的数据目录 --output /你的输出目录/report.html
```

运行完成后，主要产物是：

- `/你的输出目录/report.html`
- `/你的输出目录/run.log`

需要 Python 3.10+，依赖见 [requirements.txt](scripts/requirements.txt)。Windows 可直接使用 Python 生成器；run-report.sh 是可选 Bash 入口。

### 用法 3：如有需要，再回到上游 `raincoat-create-report`

如果你担心需求或口径变化，可以先用
raincoat-create-report（需另行安装；不是本包依赖）
重新校验需求，再交给 `raincoat-report-circle-weekly` 产出 HTML。

## 最小操作步骤

1. 准备好本周所需数据文件，文件形态对齐
   [input_inventory.md](examples/input_inventory.md)
2. 确认本次按
   [圈子业务周报需求.md](references/business-requirement.md)
   执行
3. 让 agent 激活 `raincoat-report-circle-weekly`，或直接运行脚本
4. 明确输出路径，例如 `output/report.html`
5. 检查生成结果是否满足
   [assets/html-contract.md](assets/html-contract.md)
   和
   [assets/validation-checklist.md](assets/validation-checklist.md)

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
  - 入口脚本、生成器、渲染模板与依赖清单

## 当前状态

当前状态：`draft`

这已经是第一版带脚本执行能力的圈子业务周报下游 skill 包。
当前脚本可以直接读取输入目录并生成 `report.html`，但后续仍可以继续补：

- 更严格的输入文件校验
- 更稳定的依赖锁定
- 未来如需场景注册，需另行实现；原方案仅作历史设计

## 本地业务数据

历史业务表格不随 Skill 分发。请自行准备输入文件并通过 `--input-dir` 指定目录。仓库内合成回归命令为 `bash tooling/tests/raincoat-report-circle-weekly.sh`。

## 依赖与兼容性

需要 Python 3.10+，依赖见 scripts/requirements.txt。可在支持 Python 的 macOS、Linux、Windows 环境直接运行生成器；run-report.sh 是可选 Bash 入口。Chart.js 使用随包的 scripts/app.js，运行不依赖父仓库路径。合成回归由 Raincoat 仓库提供；独立导出测试、Windows 环境与真实业务数据完整性尚未实测。

公开许可证尚未确认，保持 draft，不附加许可证。

## 迁移交付状态

当前为 `draft`。本轮完成包内路径与命名整理；许可来源尚未确认，不能正式发布。macOS 的具体检查见仓库迁移验收记录；Windows、其他宿主的原生安装与自动发现未实测。历史上标注 beta 的元数据不作为本轮验收结论。
