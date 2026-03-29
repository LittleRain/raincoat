# Reports Tool Scaffold

`tools/reports` 存放 Raincoat 周报系统的场景注册、脚本包和辅助资源。

## 目录说明

```text
tools/reports/
  README.md
  manifests/
  scripts/
    <scenario-id>/
```

## 结构约定

- `manifests/*.yaml`
  - 描述场景固定名称、说明、默认激活 release 等元信息
- `scripts/<scenario-id>/`
  - 存放该场景的脚本包、脚本 manifest、README 和依赖说明

## 首期规则

- 首期正式场景是 `trading-weekly`
- 脚本维持“输入目录 -> 生成完整 HTML”的模式
- 平台负责上传、执行、归档、记录和预览

## 新增场景方式

新增一个周报场景时，至少需要：

1. 新建 `scripts/<scenario-id>/`
2. 提供脚本入口和脚本 manifest
3. 新建 `manifests/<scenario-id>.yaml`
4. 在 manifest 中定义场景固定显示名称

## 版本要求

- 更新已有场景逻辑时，以新的 release/version 进入平台
- 历史运行结果必须可追溯到执行时使用的脚本版本
