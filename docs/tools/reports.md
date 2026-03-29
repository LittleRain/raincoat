# Reports 工具说明

`reports` 是 Raincoat 第一批规划中的工具模块，路径前缀为 `/reports`。

## 当前场景

- `trading-weekly`
- `circle-daily`

## 目录约定

```text
tools/reports/
  README.md
  manifests/
  scripts/
    trading-weekly/
    circle-daily/
```

## 约定

- `manifests/*.yaml` 描述场景元信息
- `scripts/<scenario>/manifest.yaml` 描述脚本入口和输出产物
- 脚本直接生成完整 HTML
- 平台负责发现、运行、归档和预览

## 首期平台能力

- 页面展示场景固定名称、描述和运行入口
- 用户通过网页上传数据文件触发脚本执行
- 平台保存运行记录、脚本版本、输入文件清单和产物路径
- 历史记录可查看运行状态，并打开对应的 `report.html`

## 场景扩展原则

- 新增场景通过代码注册，不走后台动态录入
- 每个场景保留固定显示名称，由 manifest 手动配置
- 平台需要支持两类后续演进：
  - 更新已有场景脚本逻辑，并保留历史运行记录的版本追溯
  - 添加新的周报场景，沿用统一的脚本 contract 和运行记录模型

## 运行记录约定

- 一次执行对应一个 `runId`
- 运行记录至少保存场景标识、场景名称、`releaseId/version`、状态、时间、输入文件和产物路径
- 历史 HTML 始终指向当次运行生成的静态产物，不受后续脚本升级影响

## 脚本 Contract

- 接收标准参数：`--input-dir`、`--output-dir`、`--run-id`
- 输出至少一个 `report.html`
- 可额外输出 `summary.json`、`run.log` 等附属产物
- 首期 `trading-weekly` 保持现有 Python 周报逻辑不变，仅做输入输出适配
