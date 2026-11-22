## 0.9.8

闭环改成「一台机器、一个写者」，并把「静默」本身当成故障来修。

- **单写者**：抓取端 worker 不再提交/推送 vault（`KB_LOCAL_ONLY=1`），只把稿写进本地 `00 Inbox/`；插件的 tick 是唯一 commit/push 的人。跨机双写这一类故障（目录改名假冲突、rebase 半途、推送滞留）没有前提了。
- **未跟踪文件不再挡住 pull**：`pullVault` 原来要求工作区「零改动」，而 worker 刚推进 Inbox 的稿天然是未跟踪文件——每次有新稿的那一轮就拒绝 pull。现在只看已跟踪改动（`trackedDirty`），未跟踪文件照常拉取。`gitOverview` 同时返回 `dirty`（全部）与 `trackedDirty`（已跟踪），体检报告仍按全部算。
- **灵感不再丢原文**：`decision=idea` 以前只写摘要就删 Inbox 原件，摘要里的 `[Source: 00 Inbox/...]` 指向一个已删除的文件（违反 Hard Rule 12）。现在先写 `02 outputs/builder/ideas/<slug>.md`（带 `captured_from`）再删，摘要的 `source:` 指向这份留存件；`02 outputs/builder/ideas` 纳入自动提交白名单。历史上 6 篇的原文已从 git 历史恢复到 ideas/ 并回填 Source。
- **看门狗**：新增 `scripts/watchdog.mjs`（launchd `com.rain.kb.watchdog`，每 10 分钟）：闭环心跳、卡住超过 45 分钟的整理任务、抓取端心跳、24 小时内新增的失败摄取、本地领先/落后、磁盘余量。异常推系统通知（同一问题 30 分钟不重复，可配 `settings.alertWebhook`），状态写 `~/.dsh/raincoat-kb-desk/ingest-status.md`，异常或跨天才在 `02 outputs/health/ingest-status.md` 留一份，避免每 10 分钟制造提交。
- **修掉每轮提交后抛错**：`gitCommitAndPush` 的返回里引用了未定义变量 `pulled`，每次成功提交推送后都会抛 `ReferenceError` 并把 tick 打断。

## 0.9.7

两件事：不再为「重投」多长一篇，以及队列空的时候也能回答「抓取端还活着吗」。

- **入队前按 canonical_url 去重**：worker 重投、手工补录都会把同一篇再推进 Inbox。现在 tick 在入队前用 `localIngestIndex` 查一遍 `00 raw`，命中就调 `dropDuplicateInbox` 把这份重复投递从 Inbox 移走，并在 `log.md` 留一条 `triage:<space> | 标题 → drop（重复：已有 …）`，报告里也写一行。之前这类重复会白跑一次模型、多出一条 job（`S-092`/`S-094` 那次就是这么长出第二条摘要的）。
- **抓取端活性**：`GET /ingest/stats` 新增 `workers`（读服务端 `/api/workers` 心跳）与 `lastDoneAt` 兜底；面板统计卡从 4 张变 5 张，多一张「抓取端」——在线显示「心跳 N 分钟前」，离线显示最后心跳，旧版 worker 没有心跳时退回「最近抓取 N 分钟前」，不再是空白。
- 服务端配套：`squirrel` 新增 `POST /api/worker/heartbeat` 与 `GET /api/workers`（心跳落 `data/queue/workers.json`，3 分钟无心跳判离线），worker 每 60 秒打一次（启动先打一次）。

## 0.9.6

修「Inbox 明明有东西，却一整天没摄入」这一类静默停摆。根因不是模型，是闭环的两个前置条件互相锁死：工作区脏就跳过 pull、队列里有活就跳过提交，而这两件事恰好互为解法——11-19 22:20 到 11-20 13:43 就这样零摄入 15 小时，且状态只活在内存里，面板看不出来。

- **提案不再能冻住提交**：`expireStaleProposals` 在每轮开头就把「原文已不存在」的提案判废（历史上一条孤儿提案卡了 2 天），本轮尝试落盘仍失败的提案超过 `proposalTtlMinutes`（默认 30 分钟）也判废；判废会写进报告，不再安静消失。
- **提交与「全局空闲」解耦**：原来要等 `activeCount() === 0` 才提交，现在只要没有 `running` 的整理就推——已落盘的产出不再被一个坏条目扣住。tick 顺序也改成「判废 → 落盘 → 提交 → 拉取 → 入队」，脏工作区会先被自己的提交消化掉，而不是挡住 pull。
- **重试有预算、错误有分级**：`attemptsFor(path)` 数同一篇失败次数，超过 `maxAttemptsPerDoc`（默认 5）就停下并在报告里写明「先停下等人看」；命中 `429 / insufficient_quota / 配额` 后进入 `quotaCooldownMinutes`（默认 10 分钟）冷却，不再按 60 秒节奏重撞网关（11-16 曾对同一篇重试 53 次）。
- **两台宿主不再各跑一份内存队列**：`syncFromDisk()` 按 mtime 判断队列文件是否被另一个宿主改过，没有 running 任务时整体接管；`lastReport` 也落盘到 `watcher-state.json`，进程重启后仍能看到「上一轮为什么没动」。
- **git 拉取关掉目录改名推断**：`-c merge.directoryRenames=false`。worker 往 `00 Inbox/<日期>/` 加文件时，git 会把「Inbox → raw」的改名误判成整目录搬家，制造假冲突并把仓库留在 detached HEAD；现在 `pull --rebase` 失败会先 `rebase --abort` 再返回，绝不从半途状态 push。
- 新增 `tests/watcher-guards.test.mjs`：覆盖丢失原文的提案判废、存在的提案不动、失败计数与配额冷却、磁盘被另一宿主改过后整体接管。

## 0.9.5

- 补上 0.9.4 没覆盖的那一半：**摄入页新增「本地摄入」区块**。0.9.4 的本地反查只能给「远端已经有任务」的行贴「已摄入」——如果一次摄入**从来没走过远端队列**（agent 用脚本直接落盘，比如播客转写；或手工整理），列表里连一行都没有，看上去就像没摄入过。现在这些只在 vault 里存在的摄入会单独列出来，带标题 / 平台 / 时间 / 「raw + 摘要」，点开即看；按 URL 与远端队列、history 去重（`urlKeys` 归一化过尾斜杠与 query），不会重复显示。
- `lib/vault.js` 新增 `scanLocalIngests`：扫 `00 raw` 读 frontmatter 的 `source_url` / `canonical_url` / `url` 与 `ingested_at`（缺则用 mtime），摘要复用 0.9.4 的 `buildSummaryIndex`；没有来源链接的笔记（灵感 / 手记）不进来，避免污染列表。
- `GET /kb-desk/api/ingest/local?days=30&limit=20`：返回 `{ rows, count, remoteCount }`，远端读不到时降级为「全是本地」，不阻塞页面。
- 新增 `tests/scan-local-ingests.test.mjs`：覆盖带 url 的 raw 出现且带摘要、无 url 的不出现、`days` 之外的老摄入被过滤。

## 0.9.4

- 修「明明已经摄入了，插件里却只有 Inbox、看不到本地记录」：摄入列表和详情现在会按链接反查 vault，给每条任务带上 `local: { raw, summary }`。远端 history 里 `vault_path` 为空、或当时的摄入不是插件整理的（`triage-jobs.json` 里没有 job），都能显示成「写入本地」并给出 raw + 摘要路径，列表加「已摄入」标记；详情里的「落盘位置」优先给真正的 raw，点开就能看。
- `lib/vault.js` 新增 `buildLocalIngestIndex` / `localIngestIndex`：扫 `00 raw` 的 `source_url` / `canonical_url` / `url` 建 URL 索引，摘要侧兼容 `source`、`source_file` 与正文里的 `[Source: raw/...]` 三种写法，30 秒缓存；顺带兼容 frontmatter 没写收尾 `---` 的 raw。
- 新增 `tests/local-index.test.mjs`：覆盖尾斜杠 / 带 query 的链接、`source_file` 写法、未闭合 frontmatter 三种情况。

## 0.9.3

- 修「重试了没反应，还在失败里」：历史归档里的失败任务早已不在远端队列，`POST /jobs/:id/retry` 会回 `409 job is not retryable`，原来把它当成「远端服务没有重试接口」报出来、列表却一动不动。现在这类任务重试会退回按原链接重新提交（`POST /ingest`），后端返回新增的 `resubmitted` 字段说明换成了哪条新任务；本地 `retry-marks.json` 记一笔，列表与详情标「已重新提交」，不用再猜它到底处理没处理。旧版服务没有重试接口（404 + HTML）时同样退回重新提交。
- 历史归档行不再出现「全部重试」：远端队列里没有失败任务时按钮换成一句「只剩历史记录，逐条重新摄入」，避免一次重抓一堆旧链接；失败统计卡在「全都在归档里」时直接写明「队列里没有可重试的」。
- 重试结果除了顶部提示条，也在按钮下面留一行，单条重试后右侧详情保留并刷新——面板顶部的提示条在滚到下面点按钮时很容易看不见。
- `lib/retry-marks.js`：重新提交记录的本地存储（最多 300 条，按时间淘汰）。

## 0.9.2

- 排查的错误归类补上 `vault-git`：`unfinished rebase` / `rebase-merge exists` / `unmerged files` / 不在 `main` 这几类以前都落到 `unknown`，现在归到「vault 的 git 状态坏了（local）」，并在判读参考里写明先看 `git status`、再 `git rebase --continue` 或 `--abort`。2026-11-11 那次整条队列失败就是这类错误被归成 unknown，绕了一圈才发现是 mini 上 vault 停在冲突的 rebase。

## 0.9.1

- 修统计卡与列表数字不一致：实时队列里的任务常常也在历史归档里，原来两边直接相加导致偏大；现在按 id 去重后计数，卡片与列表同源。

## 0.9.0

- 支持双实例：桌面 app 与 `co.dsh.web` 共用 `~/.dsh`，自动闭环只由 `watcherOwner` 指定的实例跑（默认跟随设置），另一套实例跳过；同时用 `watcher.lock`（pid + 120s TTL）兜住并发。
- `web` profile 也装了本插件，手机入口能看到同一份摄入状态。

## 0.8.1

- 历史归档里部分记录只有 `finished_at`（来自 worker 日志），`created_at` 兜底成完成时间，避免列表显示 1970。

## 0.8.0

- 摄入列表合并 VPS 的历史归档（`/kb/history.json`）：队列目录是工作区、会被清理，旧任务（含失败）不再凭空消失；历史行带「历史」标记，已完成的统计卡也计入归档数量。
- `GET /ingest/jobs` 返回 `live` / `archived` 两个计数，面板按创建时间倒序合并去重。

## 0.7.0

- 摄入页支持重试失败任务：失败列表头「全部重试」一次重排远端全部失败任务（不受前端只取 40 条的限制），失败详情里「重试这条」只重排当前这条。逐条重试、结果按条汇报，部分失败会说明哪条没成功、为什么。
- 新增插件路由 `POST /ingest/retry`（body 可带 `ids`）与 `IngestService.retry()`：不带 `ids` 时先拉远端全部 `failed` 再逐条重试；远端缺少重试接口（旧版本部署）时提示「远端服务还没有重试接口」，不静默失败。
- 依赖摄入服务新增 `POST /jobs/:id/retry`：把 `failed` 任务放回 `queued`、`attempts` 清零；非失败任务返回 409。必须部署新版摄入服务后「全部重试」才会生效。
- 摄入页提示条改成「带失败字样一律判错」，避免「已重新排队 3 条，1 条没成功」被渲染成成功样式。
- 新增 `tests/ingest-retry.test.mjs`：用本地假服务覆盖指定 id、全部重试、部分失败、旧服务 404、重复 id 去重五种情况。
- 重做「自动闭环」那一行：去掉平级的三个开关和「立刻跑一轮」。现在是状态（`自动处理中` / `已暂停`）+ 一个 `暂停`/`继续` 动作 + 唯一真实选择「写入方式」（`直接写入` / `先给我确认`）+ 行尾一句「上一轮干了什么」。
- 「自动推送」从界面移除、永远开启：写盘后自动提交推送，失败在行尾报错并在下一轮重试。设置字段保留，高级用户仍可在 `settings.json` 里关。
- 「暂停」语义改清楚：只停「整理新摄入」，git 拉取和推送照常跑（`lib/watcher.js` 不再整轮 return）。
- 手动同步入口移到顶栏 `落后 origin N`，点一下 = 现在同步一轮（`POST /auto/run`），结果提示拉取/整理/写入/推送各几条。
- 「先给我确认」模式补批量操作：Inbox 区显示「全部写入 N 条提案」，两步确认（第一次点变确认态），逐条写入后统一提交推送，部分失败会说明。
- 新增 `tests/watcher-paused.test.mjs`：锁定「暂停时仍跑同步/推送、且报告里写明暂停」的语义，避免又被改回整轮 return。

## 0.6.1

- 摄入任务列表按创建时间倒序，最近的在最前面；服务端按升序并从最早的截断，因此改为多取一些（120 条）再在前端取最新 40 条。

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
