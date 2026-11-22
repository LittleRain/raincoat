# AI 候选分析（显式启用）

## MiniMax M3 优先扫描

先前已用当前22秒素材进行独立 MiniMax 实网验证，调用链路可用，但未稳定找出用户确认的约15–17秒过人动作；详见 `docs/validation-next.md` 及本地忽略目录 `data/validation/minimax-2026-10-15/report.md`。工作台现允许按窗口扫描整段视频；长视频的识别效果与运行时间仍待实测。

```dotenv
FAS_AI_PROVIDER=minimax
FAS_AI_ENABLED=true
MINIMAX_API_KEY=在本机填写自己的密钥
# 默认 FAS_AI_MODEL=MiniMax-M3
# 默认 FAS_AI_BASE_URL=https://api.minimax.io/v1
```

填写密钥后重启服务，在“生成并挑选片段”选择视频、勾选发送同意，再点“生成候选片段”。若使用国内账号的其他官方接入地址，可明确设置 `FAS_MINIMAX_BASE_URL`；不同区域密钥是否通用尚未验证。不要把密钥发送到聊天或提交Git。

若看到 MiniMax HTTP 401，先检查 `.env` 的 `MINIMAX_API_KEY` 是否为当前账号可用的密钥，并确认密钥所属区域与 `FAS_MINIMAX_BASE_URL` 一致。更新后重启工作台。HTTP 401 表示请求未通过鉴权；可在 MiniMax 官方额度查询接口检查密钥状态，不必重新上传视频。旧扫描任务仍保留，重试前按页面提示处理未确认窗口。

此预设不限制原片时长，但单次任务最多 500 次调用；每 12 秒窗口（重叠 2 秒）预留初扫与复核各一次，超出上限需分段导入，不安装模型。已成功窗口的响应可在显式重试时复用，但候选只在全片完成后发布。默认发送每窗口带原片时间的低分辨率抽帧，初扫4帧、复核8帧；此前原生视频输入在实拍中出现时间定位异常，因此仅在显式设置 `FAS_MINIMAX_INPUT_MODE=video` 时作实验。视频实验模式从原片生成最长边768像素、24fps的无声H.264短片，模型端初扫采样2fps、复核5fps；每片限制16MiB，临时文件在请求构造后删除。两种模式都不发送原始4K文件，也不调用视频生成。

MiniMax 单次请求最多等待 240 秒；超时后请求结果仍视为未确认，不自动重发。模型输出长度上限为 8192 tokens，若返回不完整结果则不会发布候选。

足球提示版本 `football-continuous-6` 要求同一次连续进攻或训练动作只返回一个事件，突破、对抗和球权变化写在同一段描述中；仅在明显重置或新一轮训练时另起片段。程序也会把初扫、复核及相邻时间窗里高度重叠的结果合成一段，按进球、射门、突破、抢断、其他的顺序选择主要动作。旧候选保留原样，新版本需要用户主动重新分析，不会自动产生费用。

模型偶尔会把片段时间写到本次分析窗口之外。与窗口部分重叠的结果只保留窗口内可见范围，并标记时间截取；完全位于窗口外的结果忽略。非数字、倒序等无效时间仍拒绝，以免生成错误裁切。已失败任务的原响应没有保存，修复不会自动重发或覆盖旧候选。

MiniMax请求采用max_completion_tokens、reasoning_split和M3禁用思考选项，避免思考正文混入JSON。接受完整JSON或JSON代码块，截断/空响应/业务错误不标记成功。来源：2026-10-14核对的[官方OpenAI兼容文档](https://platform.minimax.io/docs/api-reference/text-openai-api)。此API不支持输入音频，无声短片不用于声音证据。

离线测试使用真实FFmpeg短片和替代HTTP响应，覆盖无音轨、尺寸、时长、时间偏移、临时文件清理、M3请求形状、缺密钥、长视频预算约束、两轮分析缓存与人工审核不覆盖。离线通过不代表已通过MiniMax长视频实网验收。以下为通用图片适配器说明。

默认不运行 AI；没有配置时不产生模拟候选，人工选片和导出独立可用。实现未验证真实足球识别效果、身份准确率、40 分钟 4K 性能或价格，不承诺自动追踪及同步。

服务端环境变量：

```dotenv
FAS_AI_ENABLED=false
MINIMAX_API_KEY=your-minimax-key
FAS_AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
FAS_AI_MODEL=gemini-3.8-flash
FAS_AI_API_KEY=your-gemini-api-key
```

只有 `FAS_AI_ENABLED=true` 且所选供应商配置有效时，分析任务才会提交抽帧。工作台默认选 MiniMax，整段视频优先走 MiniMax；用户可手动选 Gemini。MiniMax 失败后不会自动切换供应商，切换并开始新扫描须再次同意发送素材。各任务冻结供应商和模型，运行中的任务不会因页面切换而改用另一家。`FAS_AI_PROVIDER` 仅作为旧接口未指定供应商时的默认值。Base URL 不允许用户名、密码、查询或片段，远端必须 HTTPS，仅 localhost、127.0.0.1 和 ::1 允许 HTTP；密钥只经环境传入，不写数据库或前端。代码使用 OpenAI-compatible `/chat/completions`，模型须支持图片与 `response_format=json_object`。不自动安装模型或下载权重。

发送内容包括本素材窗口抽帧、源视频秒数、目标参考裁图及服装说明；不发送原视频。每图最长边 768 像素且不超过 600 KB；每窗默认 4 帧，候选窗口默认 8 帧验证。窗口默认 12 秒，重叠 2 秒，完整覆盖媒体时长。单素材串行处理，通过已有 Worker 检查取消；HTTP 适配器每 0.25 秒检查取消和停止，取消会中断异步传输。Gemini 兼容端点的读取超时为 180 秒，其他供应商为 60 秒，连接超时均为 10 秒；超时后请求结果仍视为未确认。

Gemini 兼容端点的足球扫描请求显式使用 `reasoning_effort: low`，并省去 `temperature`；[Google 官方兼容接口文档](https://ai.google.dev/gemini-api/docs/openai/)支持此参数，[Gemini 3.8 Flash 文档](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash)说明其默认思考强度为 medium，low 可降低延迟。请求版本随此调整升为 `football-continuous-4`，避免将旧请求的缓存误当成新参数下的结果。旧版未确认请求仍可能已计费，界面会要求额外确认后才能开始新版扫描。此调整不能保证消除供应商侧超时。

Gemini 返回 HTTP 503 时，页面说明供应商暂时不可用或繁忙，建议等待几分钟再手动重试；[Google 的 API 错误说明](https://ai.google.dev/gemini-api/docs/api-errors)将 503 归为临时服务不可用。工作台不自动重试，也不记录供应商原始错误正文；请求结果继续按未确认处理。

`POST /api/media/{id}/analyses` 接受 `request_key`、`window_s`、`overlap_s`、`frames_per_window`、`max_calls`、可选 `max_cost` 和 `cost_per_call_upper_bound`。费用字段是用户根据供应商和所选帧配置给出的单次费用上限；应用没有实时价格表，不能核实供应商收费。未提供费用参数时只控制调用次数，费用估算为 null。排队前要求预算可容纳所有扫描窗口及每窗一次密集验证；不足则返回 422，不截断扫描。最多 500 调用，发送前持久化计数，任务恢复后仍计入同一 run 的预算。返回估计和 job_id；同素材同 request_key 重复提交返回已有任务。

内容缓存键覆盖原片完整 SHA256、模型、供应商、提示版本、抽帧配置、目标参考内容和窗口；不同 request_key 可复用成功响应。请求前持久化 pending 标记，响应和结构校验成功后保存结果。超时或崩溃后 pending 结果未知，不自动重发，重试会明确停止，须先核对供应商账单再由管理员处理对应缓存。此策略优先避免重复费用，不能保证供应商端计费准确。供应商若支持，会收到 Idempotency-Key。没有后台自动 HTTP 重试。

失败任务若有未确认请求，当前素材的扫描表单上方会显示恢复入口。用户勾选重复计费确认后，点击“确认可能重复计费并重新扫描”，会删除该任务的 pending 缓存并创建新分析任务；旧任务及其请求记录保留。重新发送可能重复计费，普通“重试分析”不会执行此操作。接口为 `POST /api/analysis-runs/{rid}/retry-unknown`，请求体 `{ "confirm_possible_repeat_charge": true }`，仅允许失败任务且当前供应商配置与原任务一致。工作台 HTML 使用 `Cache-Control: no-store`，更新前端后刷新页面即可加载新版本。

候选结构校验限定窗口内时间、允许类型、两个独立置信度、独立证据和文本长度。每个窗口都做初扫和复核，任一轮发现的事件都保留为待审候选；只出现于单轮的事件会写明不确定性。相邻窗口内同类重叠候选只保留第一条；此去重为保守启发式，可能合并近邻动作，未做跨机位自动合并。只有完成全部窗口后才持久化候选。重跑创建新 run 和候选，绝不更新人工审核。模型输出永远保留 `identity_status=uncertain`，人工才可确认目标。置信值没有经过概率校准。

接口：

- `GET /api/analysis/config`：可用状态、供应商、模型、发送范围，无 API key。
- `GET/POST /api/media/{mid}/analyses`：分析历史（含预算、窗口覆盖、usage）与排队。
- `GET /api/sessions/{sid}/candidates?limit=200&offset=0`：真实模型候选；无模型结果则为空。
- `GET /api/media/{mid}/frame?time_s=1.5`：按受控媒体 ID 本地抽帧。
- `GET/POST /api/sessions/{sid}/target-references`：POST `{media_id,source_time,box_normalized:[x,y,width,height],clothing_notes}`；坐标基于 FFmpeg 自动旋转后的完整画面，归一化 0–1，每场次最多 8 张。引用裁图完全在本地生成，仅实际启用分析时发送。

集成：在 Store 迁移事务内执行 `analysis.init_schema(conn)`；在通用媒体动态路由和静态挂载之前执行 `analysis.register_routes(app,store)`；worker 遇 `jobs.type='analysis'` 调用 `analysis.analyze(worker,job)`。`analysis.analysis_config()` 提供 health 可用状态。

验证仅使用离线适配器，覆盖默认禁用、预算、幂等、完整窗口、响应约束、永不自动确认身份、缓存复用、未知请求不重复发送、HTTP 取消、本地 HTTP 边界、预处理失败拒绝、人工同步和关联撤销。未发送用户儿童影像进行云端测试。

## 人工同步与多机位关联

在 `sync.register_routes(app,store)` 注册下列接口；`sync.init_schema(conn)` 可在迁移事务内调用。它们仅保存人工校准，不运行音频相关、自动追踪或自动跨设备去重。

`GET /api/sessions/{sid}/sync` 返回 `{mappings:[...]}`。`PUT` 同路径接受：

```json
{"mappings":[{"media_id":"source-id","offset_s":10,"drift_ratio":1,"verification_status":"manual","anchor_pairs":[[0,10],[20,30.02]]}]}
```

计算公式为 `session_time = offset_s + source_time * drift_ratio`。无锚点时使用给定偏移与比例；一锚点仅算偏移、比例设为 1；至少两个锚点做线性拟合。源时间须在素材内，源锚点不能重复；比例超出 0.9–1.1 或任意拟合残差超过 1 秒拒绝。置信度为空，不冒充自动验证。批量更新先校验全部映射后在一个事务中保存，失败不部分写入。

`GET/POST /api/sessions/{sid}/event-groups` 接受 `{event_ids:[review_id_1,review_id_2],description:"同一动作的两个机位"}`，返回 id、人工关联状态和 event_ids。必须全部属于本场次、不同素材，不能重复引用同一个事件。完全相同的集合重复提交复用已有 group。`DELETE /api/event-groups/{id}` 撤销关联，不删原片或审核事件。关联只作人工标记；导出机位仍以审核台中选择的事件为准。

兼容接口 `GET/PUT /api/sessions/{sid}/sync-mappings` 可单条保存 `{media_id,offset_s,drift_ratio,anchors:[{source_time,session_time}]}`，GET 返回数组。前端优先使用批量 `/sync`。
