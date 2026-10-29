# raincoat-trade-weekly-report

读取交易周报数据，生成五个栏目组成的 HTML。当前默认生成器使用六份固定名称的 Excel，与历史四文件合同不同。名称暂未迁移为 raincoat- 前缀。

## 安装与运行

需要 Python 3.10+，单独复制整个 Skill 后安装其自身依赖，不需要 Raincoat 仓库或作者机器目录：

```bash
python -m pip install -r scripts/requirements.txt
python scripts/run_report.py --input-dir /path/to/input --output-dir /path/to/output --run-id example
```

`--run-id` 仅在日志中标识本次运行，不代表已有归档平台。输出为指定目录的 `report.html`；也可用 `--output` 指定文件。可选 Bash 入口保持上述参数兼容，也支持旧的 `run-report.sh <input-dir> <output.html>`；脚本不会自动安装依赖。

直接使用 `python scripts/generate_report.py --data-dir <directory> --output <file>` 仍然有效。省略数据目录时仅使用当前 cwd，不使用作者下载目录；建议始终显式指定输入输出。文件资源按脚本安装位置解析。

## 当前输入合同

| 文件 | 必需信息 |
| --- | --- |
| 整体.xlsx | 周五-周四周、业务线二级、GMV、订单数、买家数、商品曝光PV、商详PV、CTR、CVR、GPM |
| 行业.xlsx | 周、业务线与指标，商家ID、店铺名称、经营一级类目名称；GPM 可由 GMV/曝光计算 |
| 商品明细.xlsx | 周、商家ID、店铺名称、商品ID、商品名称、GMV、订单数、买家数、商品曝光PV；兼容文件名 商品.xlsx |
| 流量.xlsx | 周、业务线与指标、资源位二级入口 |
| 内容类型.xlsx | 周、业务线、商家ID、内容类型、GMV |
| 商家标签.xlsx | 工作表名必须为 sheet；merchant_id/owner_ld/owner_cate，或商家id/行业负责人/行业 |

指标别名兼容见 SKILL 与生成器的 load_all；例如 GMV（不减退款）、支付订单数、支付订单买家数。输入至少覆盖两个完整周期，保持商家 ID 类型一致。商家行业归属和自营分类见 [SKILL.md](SKILL.md)。

输出覆盖核心趋势、行业、商家、渠道与成交体裁；月度与日期相关展示仍含历史固定口径，不能把本次合成测试当作所有周期适配已经完成。报告图表运行仍依赖 CDN 中的 Chart.js，离线生成通过不代表离线浏览图表通过。

## 历史四文件入口

原 docs/周报生成器_v3 的不同版本已完整保留于 [scripts/legacy/README.md](scripts/legacy/README.md)。它接受通配文件名及 CSV，用 `--dir` / `-o`，按经营分类与可选 UP 列表分类；当前默认版本使用六份 Excel 和商家负责人标签。迁移未将两种口径强行合并。

## 验证与限制

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

测试临时生成合成表格，不读取旧 docs 或用户真实输入，核对两种生成器的小店 GMV 15000→30000、默认版本环比 +100% 及文件错误处理。从非仓库工作目录运行，全部临时产物自动清理。

仅在当前 macOS/Python 环境验证，Windows、真实业务数据完整性和全部图表交互未实测。私有数据与生成报告不随 Skill 打包；尚未指定公开许可证，不能因其他样板使用 MIT 就认为本作品也采用 MIT。

当前状态为 draft。合成回归已在当前 macOS/Python 环境运行；Windows、真实业务数据完整性与完整图表交互未实测。Chart.js 仍从 CDN 加载。许可证来源未确认，不附加 LICENSE。

## 迁移交付状态

当前为 `draft`。本轮完成包内路径与命名整理；许可来源尚未确认，不能正式发布。macOS 的具体检查见仓库迁移验收记录；Windows、其他宿主的原生安装与自动发现未实测。历史上标注 beta 的元数据不作为本轮验收结论。
