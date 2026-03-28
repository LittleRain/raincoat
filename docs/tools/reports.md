# Reports 工具说明

`reports` 是 Raincoat 第一批上线的工具模块，路径前缀为 `/reports`。

## 当前场景

- `trading-weekly`
- `circle-daily`

## 目录约定

```text
tools/reports/
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
