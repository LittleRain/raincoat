# Sport Cut Studio

本地运动片段工作台。创建场次时先选足球或羽毛球，随后共用视频导入、目标人物、候选片段、人工审核和 ChatCut 交接。足球通过可选多模态分析提出带前后文的动作候选；羽毛球用本机球场运动量提出待审活动范围。两种候选都需要人工确认人物和片段边界。最后导出原片时间码清单供 ChatCut Desktop 建立可编辑时间线，也可导出 MP4 预览。不自动发布、不修改原文件。原目录名暂时保留，以免影响现有启动路径。

## 启动与使用

需要 macOS、Python 3.11+、Node.js 20.19+ / 22.12+、FFmpeg 和 FFprobe（含 libx264）。

```bash
cd apps/football-ai-studio
./start.sh
```

首次联网安装 requirements.txt 和 npm 锁定依赖。访问 **http://127.0.0.1:8765/**。Ctrl+C 平稳停止，再次执行恢复未完成任务。只绑定本机；暂不支持手机局域网或公网访问。

1. 创建场次时先选择足球或羽毛球，再导入视频。旧场次自动归为足球。上传保存副本；注册文件只引用批准媒体根目录内文件。默认单文件最大100 GiB，目录注册最多200个第一层文件。
2. 等待预处理成功，在“指定目标人物”中播放原片，框选清晰的人物画面并填写本场衣着；可保存多张参考图。再次进入场次会显示已保存参考，可逐张删除错误标记或补充新参考。删除最后一张后，自动候选区重新隐藏，需重新指定人物才能分析；正在分析时暂不允许删除参考。只想手工剪辑时仍可直接使用编辑器。
3. 在“生成并挑选片段”选择视频。足球启动 MiniMax 分析；羽毛球在本机按运动量拆出活动范围。扫描完成后候选自动更新，按视频和时间显示缩略图、描述和片段预览。候选卡片只有播放、保留、跳过三个操作。点击播放会从候选起点自动播放，到终点暂停；保留或跳过后，同一按钮变为“撤销保留”或“撤销跳过”，也可直接切换另一种选择。保留片段立即出现在 05，点开后确认人物、裁切时间和描述；跳过与撤销选择的片段默认收起，可在 05 展开“未保留片段”查看。05 的手工补片段入口独立折叠，仅用于候选漏报。仅显示每段视频最近一次成功分析的候选，旧分析记录折叠在历史中。新足球分析要求模型用简体中文描述；旧英文结果仍保留在“模型原始说明”中。羽毛球候选的发球、结束点和人物均需人工确认。
4. 足球选择训练/实战和动作类型，羽毛球标为回合。确认人物身份，标记高光，保留/待定/丢弃并填写备注后保存。修改冲突保留草稿，重新载入再保存。
   固定机位长录像可展开“全片兜底复核”：每 8 秒一个起点、相邻时间窗重叠 2 秒，按页查看中间帧并打开原片复核。已看标记只保存在当前浏览器；时间窗覆盖全片，但不是自动动作或人物识别。
5. 可开启描述字幕、0.5倍整片段慢动作；原声同步减速并保持音调，无音轨补静音。清晰原片帧可框选保存目标参考。成片人物框只是最长1秒静态提示，不会追踪。
6. 上下移动排序。足球默认导出“保留 + 已确认目标孩子”；显式勾选可含身份不确定片段，其字幕增加“身份未确认”。羽毛球指定人物模式仅导出已确认目标球员的片段，普通活动模式可包含身份未确认的保留片段。
7. 羽毛球选择指定人物或普通活动集锦，设定回合数 N。06 会先显示已保留段数、符合人物条件的可交接段数，以及不能下载时缺少的条件；下载失败也会在按钮旁显示原因。下载“ChatCut 交接清单”，其中有原片绝对路径、符合交接条件片段的精确起止秒数、场景、高光和备注。在 ChatCut Desktop 导入原片，再让 Agent 依据清单创建时间线；JSON 清单本身不是 ChatCut 原生工程文件。需要本地 MP4 预览时，选择横屏1920×1080或竖屏1080×1920，清空标题可关闭1.5秒片头。完整画面背景留边，H.264/AAC、30fps，不重复凑时长。生成后下载MP4，可取消或显式重试。

“双机位”支持人工偏移、共同动作锚点拟合、不同素材事件关联和撤销。公式：`session_time = offset_s + source_time × drift_ratio`。不会自动删除片段或改变导出机位，仍需人工选择所需机位。

ChatCut 交接格式与 Agent 指令见 [运动片段交接说明](../../docs/skills/chatcut-handoff.md)。

## AI 配置与费用

见 [docs/analysis.md](docs/analysis.md) 和 `.env.example`。未配置时显示“未运行AI分析”，不生成模拟候选。配置 `MINIMAX_API_KEY` 可使用 MiniMax；配置 `FAS_AI_BASE_URL`、`FAS_AI_MODEL`、`FAS_AI_API_KEY` 可使用 Gemini 等兼容接口。两者都需显式设置 `FAS_AI_ENABLED=true`，页面发送前需单独同意。供应商选择默认 MiniMax，Gemini 为手动备用；失败后不会自动把素材发送给另一家。远端仅HTTPS，本地适配器可用localhost HTTP。

MiniMax M3 可优先扫描整段视频。工作台按 12 秒窗口、2 秒重叠计算所需调用，每窗预留初扫和复核各一次；开始前显示调用次数，最多 500 次，超出时需将原片分段导入。成功窗口的响应会缓存，失败后显式重试可复用；候选在整段扫描完成后发布。默认发送标明原片时间的低分辨率抽帧和本场次人物参考裁图，不发送原始4K文件。此前无声压缩短片的时间定位在实拍中不稳定，现仅作为显式选择的实验模式。两轮中任一轮发现的动作都保留为待审候选，并提示单轮发现的不确定性。模型身份仍为不确定，重新分析不覆盖人工审核。置信度未经校准，真实足球识别准确率及长视频运行时间未验证。

费用以供应商实际计费为准。调用次数上限及用户填写的单次费用上限预算由后端约束；内容SHA256、模型/提示/采样配置与参考图参与缓存。未知HTTP结果保留pending，禁止盲目重发，需核对账单后人工处理。

## 本地数据与备份

默认 `data/studio.sqlite3`（WAL）。v1→v2升级先在 `data/backups/pre-v2-*.sqlite3` 备份旧库，保留场次、素材、任务；新增审核、导出、分析、候选、目标参考、同步、关联等表。jobs按type区分preprocess/analysis/badminton_analysis/render，素材列表仅关联预处理任务。

- `data/uploads/`：上传原片副本；外部引用仍在用户原位置。
- `data/derived/<media_id>/`：代理、缩略图、帧、日志、目标参考。
- `data/exports/<export_id>/output.mp4`：成片；临时目录按任务隔离，完成/失败清理。
- 人工审核与机器候选分表。保存时验证场次、时间、版本；导出冻结审核快照与配置，后续编辑不影响当次成片。
- 单worker事务领取重任务，重启从头恢复失联任务。取消终止受控FFmpeg，成片FFprobe验证编码、音轨、尺寸、时长后原子发布。

本地存储用量仅统计应用数据目录，不计外部引用原片。清理只删可再生帧缓存，保留原片、代理、目标参考、审核、成片和费用缓存，活动任务时禁止清理。删除场次仅软删除并取消任务，保留磁盘文件。备份前停止服务并复制整个data，外部素材单独备份。

`FAS_DATA_DIR` 设置独立数据目录，`FAS_MEDIA_ROOT` 设置注册根目录，`FAS_PORT` 默认8765；FFMPEG_BIN/FFPROBE_BIN自定义工具位置。中文字体默认macOS STHeiti，其他系统设置 `FAS_FONT_PATH`。中文用本地Pillow图层渲染，不要求FFmpeg字幕滤镜。

## API 与验证

在线文档：**http://127.0.0.1:8765/docs**。

- 场次/导入/播放：沿用 `/api/sessions`、`/api/sessions/{sid}/upload`、`/register`、`/api/media/{mid}/proxy`、`/thumbnail`，媒体支持Range。
- 审核：GET/POST `/api/sessions/{sid}/review-events`，PATCH `/api/review-events/{id}`（含version），DELETE同路径（`?version=N`），PUT `/api/sessions/{sid}/timeline`（完整event_ids）。
- 羽毛球候选：GET/POST `/api/media/{mid}/badminton-analyses`，本机生成待审活动片段，经场次 `candidates` 接口查看。
- ChatCut 交接：GET `/api/sessions/{sid}/chatcut-handoff`；足球默认只含已保留且已确认目标孩子的片段。羽毛球可用 `mode=person|activity&target_count=N` 设置筛选方式和数量。
- 导出：GET/POST `/api/sessions/{sid}/exports`，GET `/api/exports/{id}`、`/download`。POST含event_ids/title/orientation/allow_uncertain/request_key。
- AI：GET `/api/analysis/config`，GET/POST `/api/media/{mid}/analyses`，GET `/api/sessions/{sid}/candidates`，GET/POST `/api/sessions/{sid}/target-references`，DELETE `/api/sessions/{sid}/target-references/{rid}`，GET `/api/media/{mid}/frame?time_s=...`。
- 同步：GET/PUT `/api/sessions/{sid}/sync`（批量mappings），`/sync-mappings`（单素材）；GET/POST `/api/sessions/{sid}/event-groups`，DELETE `/api/event-groups/{id}`。
- 任务：GET `/api/jobs`，POST `/api/jobs/{id}/cancel`、`/retry`。存储：GET `/api/storage`，POST `/api/storage/cleanup`。

```bash
.venv/bin/python -m pytest tests -q
cd frontend && npm run build
```

实施计划与P0审计：`docs/plans/2026-10-14-implementation.md`；本轮验收：`docs/validation-next.md`；原P0记录：`docs/validation.md`。

## 未实现与未验证

自动音频同步、可靠远景追踪、自动聚焦裁切、双机位自动剪切、局部而非整片段变速、背景音乐和复杂包装未实现。竖屏为完整画面留边。HDR/Dolby Vision尚未专门色彩映射。

尚未用约40分钟4K GoPro与多个长iPhone片段验证性能、磁盘不足恢复、完整音画同步；短测试不等于长视频验收。已有22秒素材的独立 MiniMax 调用未稳定找到用户确认的约15–17秒过人动作；本轮调整提示、加入候选前后文和人工兜底浏览，未重新调用模型，不能宣称识别效果已改善。没有完整人工标注验收集，不宣称召回率、有效率、身份准确率或同步已达指标。
