# Scripts 说明

这个目录现在已经包含可直接执行的周报生成脚本。

## 文件

- `run-report.sh`
  - 对外统一入口，遵循 `--input-dir --output-dir --run-id` contract
- `generate_report.py`
  - 核心周报生成逻辑，按业务需求文档读取数据、聚合分析并输出 HTML
- `app.js`
  - 前端渲染模板脚本
- `requirements.txt`
  - Python 依赖
- `manifest.yaml`
  - 脚本包说明，便于后续接入 `tools/reports`

## 用法

```bash
bash skills/report-circle-weekly/scripts/run-report.sh \
  --input-dir /path/to/input \
  --output-dir /path/to/output \
  --run-id circle-weekly-2026w12
```

执行完成后，产物默认写到：

- `output/report.html`
- `output/run.log`

## 输入约定

输入目录中的文件命名应与
[input_inventory.md](/Users/raincai/Documents/GitHub/raincoat/skills/report-circle-weekly/examples/input_inventory.md)
保持一致或可匹配。

脚本会根据
[圈子业务周报需求.md](/Users/raincai/Documents/GitHub/raincoat/docs/skills/圈子业务周报需求.md)
中定义的栏目和口径生成周报，不会在运行时重新设计周报结构。
