# Raincoat

内部工具工作台，采用“一个平台 + 多个内置工具模块”的结构。

## 当前布局

- `apps/web`: 平台前端与工具入口页
- `apps/api`: 平台 API
- `apps/worker`: 任务型工具的 worker 骨架
- `tools/reports`: 周报系统工具资产、脚本、manifest 与样例
- `packages/*`: 平台共享类型、配置与任务 SDK
- `infra/*`: Docker、Nginx 与部署脚本
- `docs/*`: 架构与部署文档

## 第一阶段工具

- `reports`
  - 路径前缀：`/reports`
  - 初始场景：`trading-weekly`、`circle-daily`

## 常用命令

```bash
npm install
npm test
npm run build
```

## 部署思路

- 同一台服务器上与 `squirrel` 并存
- `raincoat` 使用独立目录、独立容器、独立 Nginx location
- 对外采用同域不同路径

详细说明见：

- `docs/architecture/overview.md`
- `docs/deploy/topology.md`
