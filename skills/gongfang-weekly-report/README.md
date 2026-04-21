# Gongfang Weekly Report

这是一个面向工房交易双周报场景的执行型 skill，用于读取指定 Excel/CSV 数据并生成交互式 HTML 双周报。

## 它做什么

这个 skill 会：

- 读取一个输入目录中的 6 份数据文件
- 使用内置口径聚焦两个重点行业：`绘画` 与 `VUP周边`
- 输出核心数据趋势、GMV 拆解、流量拆解三大栏目
- 生成一个可直接打开的 `report.html`（Chart.js 与样式均内联，支持 `file://`）

## 输入要求

把以下文件放入同一个输入目录。文件可为 `.csv`、`.xlsx` 或 `.xls`，文件名前缀需匹配：

1. `整体数据*`
2. `行业数据*`
3. `行业商品明细数据*`
4. `内容渠道数据*`
5. `商家销售明细*`
6. `资源位二级入口数据*`

关键字段（各文件按需求文档对应）：

- 周字段：`周五-周四周`（或带尾部空格同名）
- 行业字段：`后台一级类目名称`
- 核心指标：`商品曝光PV`、`PVCTR`、`商详UV`、`支付订单数`、`支付订单买家数`、`GMV（不减退款）`、`商详支付转化率-UV`、`GPM`

说明：当前脚本按周粒度读取（不再按日二次聚合），需至少覆盖 2 周数据才能产出“本周 vs 上周”结论。

## 输出内容

运行成功后会生成：

- `report.html`：交互式双周报页面
- `run.log`：执行日志（匹配文件、周期信息、产出路径）

## 如何运行

```bash
bash skills/gongfang-weekly-report/scripts/run-report.sh \
  --input-dir /path/to/input \
  --output-dir /path/to/output \
  --run-id gongfang-biweekly-2026w14
```

## 最小使用步骤

1. 准备好 6 份输入文件
2. 确认字段齐全，且至少覆盖两个周周期
3. 把文件放到同一个输入目录
4. 运行 `scripts/run-report.sh`
5. 打开输出目录中的 `report.html`

## 目录结构

- `SKILL.md`：skill 工作流说明
- `skill.json`：skill 元数据
- `assets/`：HTML 合同、栏目结构、提示词、校验清单
- `examples/`：输入清单、标准化需求、输出 inventory 与输出骨架示例
- `scripts/`：执行脚本

## 验收基线

本 skill 内置 `examples/expected-output-inventory.json` 作为输出完整性基线。当前合同要求：

- 3 个业务栏目
- 16 个图表
- 8 个表格

生成后可用 `create-report` 的 inventory validator 校验 HTML 是否漏图、漏表或漏关键指标。
