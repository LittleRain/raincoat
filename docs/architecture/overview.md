# Raincoat 架构概览

Raincoat 是一个内部工具工作台，采用“统一平台 + 内置工具模块”的结构。

## 平台目标

- 一个域名承载多个内部工具
- 工具按路径前缀挂载，例如 `/reports`
- 对任务型工具统一提供 API、worker、产物目录和发布流程

## 运行单元

- `apps/web`
  - 工作台首页
  - 工具导航
  - 第一阶段承载 `/reports`

- `apps/api`
  - 工具发现
  - 场景清单
  - 任务接口的统一入口

- `apps/worker`
  - 异步任务执行骨架
  - 后续承接脚本调度、日志采集、产物落盘

## 工具层

- `tools/reports`
  - 业务周报相关脚本与场景元数据
  - 每个脚本目录是一个最小交付单元

## 共享层

- `packages/shared-types`
- `packages/shared-config`
- `packages/task-sdk`
- `packages/ui`

这些共享包只承载跨工具、跨 app 的稳定抽象，不承载某个业务的定制逻辑。
