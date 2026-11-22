# Football AI Studio 后续实施计划

依据：同目录 2026-10-14-handoff.md。用户已授权按交接方案开发；沿用现有项目，不另建空应用，不覆盖现有数据。默认远端分析关闭。

## 现场审计

| 功能 | 已存在 | 实测结果 | 缺口 / 下一步 |
|---|---|---|---|
| 场次和导入 | 是 | 用户真实 IMG_4974.MOV 已入库 | 保留数据 |
| FFmpeg 代理 / 缩略图 | 是 | 真实任务成功，100%，约17秒 | 检查 Range 和媒体流 |
| 服务与 Worker | 是 | 8765 健康检查通过，worker_alive=true | 继续串行重任务 |
| 审核与导出 | 否 | 未实现 | 首先完成手工闭环 |
| AI / 同步 / 圈选 | 否 | 未实现 | 在闭环基础上接入可关闭适配器 |
| 40分钟4K性能 / 模型准确率 | 未验证 | 无对应验收样本及模型授权 | 不宣称已达标 |

## 架构和契约

保留 `jobs.media_id`，导出任务关联首个素材。jobs 新增 payload_json。素材列表只关联 preprocess 任务，避免新类型使素材重复。v1→v2 迁移先用 SQLite backup API 保存备份，然后事务建表；单 worker 不变，按 type 分派。

`review.py`：review_events 表，手工事件 CRUD，乐观版本校验、时间和场次校验、排序。`render.py`：exports 表，冻结审核快照，以原片渲染，FFprobe 校验后原子发布。`analysis.py`：独立候选和 runs、目标参考、显式启用的多模态适配器；默认关闭，完整窗口覆盖、预算和缓存。前端新增 ReviewStudio 组件，保留现有导入界面。

API 契约：
- GET/POST `/api/sessions/{sid}/review-events`；POST `{media_id,start_s,end_s,event_type,identity_status,decision,description,effects}`。
- PATCH `/api/review-events/{id}`：完整可编辑字段加 `version`；DELETE 同路径用 `?version=N`。
- PUT `/api/sessions/{sid}/timeline`：`{event_ids:[...]}`，所列为全部事件的顺序。
- GET/POST `/api/sessions/{sid}/exports`：POST `{event_ids:[...],title,orientation:'landscape'|'portrait',allow_uncertain:false,request_key}`。输出包含 id/job_id/status/progress/stage/error/settings/snapshot。
- GET `/api/exports/{id}/download`，通用 jobs cancel/retry。
- GET `/api/analysis/config`；GET/POST `/api/media/{mid}/analyses`；GET `/api/sessions/{sid}/candidates`；GET/POST `/api/sessions/{sid}/target-references`。AI 配置和启用不得由默认值隐式开启。
- GET/PUT `/api/sessions/{sid}/sync`：人工锚点，时间映射独立于源视频时间。

## 执行与验证

- [x] 先写 review/export 关键约束和真实媒体集成测试，验证缺功能失败。
- [x] 数据备份和迁移，手工审核、范围裁切、排序持久化。
- [x] 真实 FFmpeg 原片渲染，中文字幕、无音轨、慢动作、横/竖屏完整画面，任务恢复与下载。
- [x] 前端接入预览、数值和拖动裁切、身份与保留决定、效果、排序与导出。
- [x] AI 适配器及目标参考、预算缓存、全素材窗口扫描、候选独立保存；无凭证时仅验证离线契约，不提交用户帧。
- [x] 人工同步映射和机位关联；自动同步与远景追踪需实测再开放。
- [x] 跑原有测试、必要新测试、前端构建；重启当前服务，真实素材检查并验证可访问。
- [x] 更新用户说明和已完成 / 未实现 / 未验证记录。

## 仍待后续验收与实现

- [ ] 用户选择AI供应商、在本机配置密钥并明确启用，运行真实素材分析。
- [ ] 建立人工标注和独立验收集，评估事件召回、有效率及错误归人。
- [ ] 提供约40分钟4K和多段iPhone长素材，实测耗时、内存、存储、磁盘不足与恢复。
- [ ] 自动音频同步、可靠远景追踪、自动机位切换、局部变速及更多包装。当前人工同步/关联、整片段慢动作和静态人物框为首轮范围。
