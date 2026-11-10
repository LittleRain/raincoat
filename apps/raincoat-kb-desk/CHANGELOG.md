## 0.6.0

- 摄入页输入框旁新增「机制说明」：五步讲清从提交到 push 的完整链路，附幂等 / 冲突 / 人工关卡三条说明。
- 摘要幂等改为 slug + 标题双重匹配，修复同一篇重投时因模型换 slug 而多出一条摘要的问题。
- 路由与巡检在读 job 列表前先 `await triageReady()`，修复进程重启后 `/triage/jobs` 返回空数组。

# 变更记录

## 0.5.0

- 摄入页的失败任务详情加「排查原因」：弹窗先收证据（远端错误、阶段记录与最大空档、本机 vault 的 git 状态与落盘文件、本机对源站的一次 GET 探测、Inbox 与本地整理状态），按红/黄/绿/灰列成检查清单，再流式让默认模型给「结论 / 证据 / 怎么修 / 重试与验证」四段。
- `POST /kb-desk/api/ingest/diagnose`（SSE）：`context` 事件先回证据，`delta` 流式回结论，`done` 带完整文本。远端接口异常时退回前端任务快照，不整体失败；请求中断会 abort 模型调用。
- `lib/diagnose.js`：错误归类（vault 脏 / 租约过期 / git 同步 / 凭据 / DNS / 网络 / 登录墙 / 4xx / 重复）、源站探测（内网跳过、读前 220KB 找验证码与删除页）、阶段空档计算、检查清单与证据文本拼装；提示词禁止不可逆修法。
- 补充信息重跑：对话框底部可写模型看不到的现场信息，点「带上补充重新排查」整轮重来。
- 新增 `tests/diagnose.test.mjs`（`npm test`）。

## 0.4.0

- Hermes 退役，摄入闭环搬进插件：`lib/watcher.js` 每 60s 跑一轮「pull → 入队 → 整理 → 写盘 → 提交推送」，三个开关（自动整理 / 自动写入 / 自动推送）在摄入页可关，`POST /auto/run` 可手动跑一轮。
- 任务详情的时间线补上「本地整理」阶段：worker 只上报 Inbox 那一段，后面的写入与推送现在能在同一条时间线里看到。
- 整理幂等：同一篇重复整理会复用已有摘要编号、跳过已写过的段落，不再产生 S-2075 / S-2077 这种重复页。
- 修概念页插入位置：新增段落与 Open Threads 落在线下区标记（`<!-- 线下区 -->` / `---`）之前，回链不再插成 `- - [[...]]`，跨 space 链接统一用 `space/summaries/...`。

## 0.3.0

- 整理改成异步：`POST /triage/enqueue` 入队、`GET /triage/jobs` 轮询、`GET /triage/job?id=` 看详情、`POST /triage/apply {id}` 写盘；宿主串行跑模型，任务落盘 `~/.dsh/raincoat-kb-desk/triage-jobs.json`（重启后提案仍在，跑一半的标「宿主重启，任务已中断」）。
- Inbox 卡片显示「排队中 / 整理中 / 待确认 / 已写入 / 失败」，并加「全部整理」；关掉弹窗不影响后台任务。

## 0.2.1

- 加「同步」：`GET /kb-desk/api/vault/git` 读 behind/ahead/dirty，`POST /vault/pull` 跑 `git pull --ff-only`；顶栏出现「落后 origin N」胶囊，体检新增一条同规则。
- 摄入页状态胶囊带计数（排队中 / 处理中 / 已完成 / 失败），任务换 tab 时不至于像丢了。
- `gitCommitAndPush` 改成 commit → `pull --rebase` → push，push 被拒时再 rebase 重试一次。

## 0.2.0

- 新模块「整理」：Inbox 卡片上的「整理」按钮 → 模型出 triage 提案（判定 / space / 摘要 / 概念页增量）→ 弹窗确认 → 落 raw、summary、概念页增量、index/_index/log，并从 Inbox 移除原文；写完可一键 `git add -A && commit && push`。这是 Hermes 退役后摄入链路的闭环。
- `lib/triage.js`：`proposeTriage` / `applyTriage` / `gitCommitAndPush`；概念页只做「指定小节追加 + Timeline + 回链 + source_count+1」，不整页重写。
- 顶部 tab 改成分段控件：灰底凹槽 + 白色选中片 + 统一 58px 最小宽度；路径显示压成 `~/…`。
- 修三个不存在的主题 token：`--dsw-alias-border-secondary`、`--dsw-alias-label-tertiary`、`--dsw-alias-label-primary-inverted`。
- Inbox 卡片的来源列回落到 `ingest_mode` / `source_url`。

## 0.1.1

- 深色模式：面板白底改 `bg-base`，主按钮文字改 `bg-base`（`label-primary-inverted` 这个 token 在主题里不存在）。
- 修对比度 bug：状态胶囊 `.kbd-pill-*` 与 `.kbd-error-title` 原来直接把 `state-*-primary`
  当文字色（浅色下琥珀 2.15:1、绿 2.28:1），改为 `color-mix(状态色 55%, label-primary)`；
  圆点与边框保持原 token 不变。
