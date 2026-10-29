# Report Circle Daily

读取圈子业务昨日 feed 与转化数据，生成日报 HTML。完整业务合同随包保存在 `references/business-requirement.md`；输入文件清单见 `examples/input_inventory.md`。

## 安装与运行

需要 Python 3.10+。安装 `pandas` 与 Excel 读取依赖后，可在 macOS、Linux、Windows 的 Python 环境直接运行：

```bash
python -m pip install -r scripts/requirements.txt
python scripts/generate_report.py --dir /path/to/input --output /path/to/output/report.html
```

`run-report.sh` 是可选的 Bash 包装器，仅适用于提供 Bash 的环境。CSV 输入不需要 Excel 引擎；读取 `.xlsx` 需要 `openpyxl`。输出 HTML 内的表格排序由内联脚本提供。

## 输入与输出

输入文件命名和字段见 [input_inventory.md](examples/input_inventory.md) 与 [业务需求](references/business-requirement.md)。输出为指定路径的 `report.html`，默认运行日期取昨日。包内不附带业务数据。

## 当前状态与兼容性

当前状态为 `draft`。仓库提供合成数据回归脚本，但其测试流程由 Raincoat 仓库提供；此 README 不代表独立导出验证。当前实现面向 Python 与 Bash 环境；Windows 原生运行、全新环境安装和真实业务数据完整性尚未实测。公开许可证尚未确认，因此本 Skill 保持 draft，不附加许可证。

## 迁移交付状态

当前为 `draft`。本轮完成包内路径与命名整理；许可来源尚未确认，不能正式发布。macOS 的具体检查见仓库迁移验收记录；Windows、其他宿主的原生安装与自动发现未实测。历史上标注 beta 的元数据不作为本轮验收结论。
