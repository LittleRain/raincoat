# 个人知识库（raincoat-kb-desk）

DSH Web 插件：把「摄入 → 体检 → 学习 → 创作」四件事收进一个面板，直接读写本机 Obsidian vault。

- 侧栏入口：**个人知识库**
- 面板路径：`/kb-desk/api/*`（宿主路由，需 DSH 登录态）
- vault：默认 `~/Documents/ob_vault`（可在面板里改）

## 四个模块

**摄入**：读 `https://rainpark.cn/api/*` 的任务队列（queued / claimed / done / failed），展示每条 URL 的状态、耗时、落盘路径和时间线；顶部卡片给排队数、失败数、Inbox 待整理数。可以直接粘链接提交，服务端按 `dedup_key` 去重。列表是「实时队列 + VPS 历史归档」合并的：队列目录只是工作区、会被清理，而 `/kb/history.json` 里留着全部任务，所以旧任务（尤其失败的）不会凭空消失，历史行会标「历史」。输入框右边的「机制说明」把整条链路（远端队列 → worker 抓取 → Inbox → 模型提案 → 本地落盘 → 提交推送）逐段讲清楚，包括幂等、冲突和人工关卡。

**健康**：按 vault 的 `AGENTS.md` 规则体检——概念页连接度（≥2 条）、`> CONTRADICTION` 标记、`!` 待确认、Open Threads 停滞天数、Inbox 积压、日志断更、页面过期。结果分 🔴 必须处理 / 🟡 待处理 / 🔵 建议关注，可一键写进 `02 outputs/health/health-check-YYYY-MM-DD.md`。

**学习**：左侧用阅读视图渲染正文（也可切原文 iframe），段落可点选引用；右侧对话基于「文章 + 你选的段落 + 历史」回答，走 DSH 默认模型流式返回；学完可以沉淀成 Inbox 笔记，进入正常摄入链路。

**创作**：取 vault 里近 N 天的**沉淀物**（`00 raw`、`concepts`、`entities`、`summaries`，排除索引、日志、周报），勾选素材后让模型给公众号 + 小红书选题（标题 / 钩子 / 角度 / 提纲 / 素材出处），可以存成草稿到 `02 outputs/drafts/`。

## 安装

```bash
plugin_manager install_bundle target=link:/Users/raincai/Documents/GitHub/raincoat/apps/raincoat-kb-desk
```

`package.json` 里 `dsh.bundle.patch` 指向 `cordis.patch.yml`，插入的 entry id 是 `raincoat-kb-desk`。

## 配置

`~/.dsh/raincoat-kb-desk/settings.json`（面板里改，不改文件也行）：

| 键 | 默认 | 含义 |
| --- | --- | --- |
| `vault` | `~/Documents/ob_vault` | vault 根目录 |
| `apiBase` | `https://rainpark.cn/api` | 摄入服务地址 |
| `credentialsFile` | `~/.config/kb-ingest/credentials.env` | token 来源 |
| `inboxWarnDays` / `inboxDangerDays` | 3 / 7 | Inbox 积压阈值 |
| `threadWarnDays` / `threadDangerDays` | 60 / 90 | Open Thread 停滞阈值 |
| `stalePageDays` | 90 | 页面过期阈值 |
| `logStaleDays` | 7 | 日志断更阈值 |

Token 只从 `credentials.env` 读（`INGEST_TOKEN` / `WORKER_TOKEN` / `KB_API_BASE`），不回传前端、不落日志。

## 同步（pull）

worker 抓完直接在远端仓库提交并 push，本地 clone 不 pull 就看不到新文件——Inbox 显示 0、点开落盘路径是 404，但任务其实已经 done。面板顶部因此有两条：

- 顶栏右侧出现「落后 origin N」胶囊，点一下跑 `git pull --ff-only`；
- 体检的「摄入链路」里也会列一条「本地落后 origin N 个提交」。

拉取只在工作区干净时执行（有未提交改动会直接告诉你，不强来）。

## 整理（triage）

每条原文卡片右下角有「整理」，分区头有「全部整理」。点下去只是**入队**：宿主里串行跑模型（一次一条，不并发烧 token），卡片上依次显示「排队中 → 整理中 → 待确认」，你可以直接切去别的页干活。任务写到 `~/.dsh/raincoat-kb-desk/triage-jobs.json`，重启后提案还在。

模型按 vault 的 `AGENTS.md` 出一份提案——判定（归档 raw / 只留灵感 / 丢弃）、space、slug、摘要（TL;DR、核心观点、我的判断、待验证）、以及要动的概念页（增量段落 + 新增 Open Thread）。默认全自动：宿主每 60 秒跑一轮，发现 Inbox 有新文件就直接排队整理、写入并提交推送；想人工过一遍，把「写入方式」切成「先给我确认」，提案会停在待确认，可以逐条打开弹窗确认，或点「全部写入 N 条提案」批量写入。落盘规则：

- `00 raw/<space>/<YYYY>/<MM>/<slug>.md`（原文归档，不可变）
- `01 wiki/<space>/summaries/S-<N>-<slug>.md`（带 `[Source: ...]`）
- 概念页只在指定小节追加一段 + Timeline 一条 + 回链，并 `source_count + 1`；新建的概念页 `status: draft`
- `01 wiki/index.md` 计数、`01 wiki/<space>/_index.md` 摘要列表、`01 wiki/log.md` 一条 `## [日期] ingest:<space> | …`
- 最后从 `00 Inbox/` 删掉原文件

写完后弹窗里给一个「提交并推送 git」按钮（`git add -A && commit && push`），因为 worker 写入前要求 vault 干净。

这条链路接的就是 Hermes 退役后的缺口：worker 只把原文推进 Inbox 并 push 远端，剩下的 pull → raw → summary → 概念页 → 索引/日志 → push 由插件闭环。模型只出提案，落盘由本地代码按规范机械执行，不整页重写既有页面；同一篇重复整理会复用已有摘要编号并跳过已写过的段落。

## 自动闭环

`lib/watcher.js` 每 60 秒（`watchSeconds`）跑一轮，四步都是幂等的：

1. `git fetch` + `git pull --ff-only`（工作区脏就先跳过，不会覆盖你的改动）
2. Inbox 里没进过队列的文件入队
3. 提案好的任务按「写入方式」处理：「直接写入」就落盘，「先给我确认」就停在待确认
4. 队列空了才 `git add 00 Inbox 00 raw 01 wiki 02 outputs/health|drafts && commit && push`（只提交这些路径，不碰你正在编辑的笔记）

界面上这行只有状态和一个真实选择：

- 状态：`自动处理中` / `已暂停`，右边是对应的 `暂停` 或 `继续`。暂停只停「整理新摄入」这一步，git 拉取和推送照常跑，不会冻结同步。
- 写入方式：`直接写入`（模型出完提案就落盘）或 `先给我确认`（提案停在待确认，Inbox 区出现「全部写入 N 条提案」，也可以逐条打开弹窗确认）。
- 行尾一句话说明上一轮干了什么（`上次 3 分钟前：拉取 2，整理 1，已推送`）或上一轮的错误；正常情况下不需要看。
- 「自动推送」不设开关：写盘后自动提交推送，失败才在行尾报错，下一轮重试。
- 手动同步：顶栏 `落后 origin N` 点一下 = 现在同步一轮（拉取 → 整理 → 写入 → 推送）。

## 失败排查

摄入页左栏切到「失败」，列表头会出现「全部重试」，一次把远端所有失败任务重新排队（不受界面只显示最近 40 条的限制）；选中单条时右侧还有「重试这条」。重试走服务端 `POST /jobs/:id/retry`：任务回到 `queued`、尝试次数清零，worker 下一轮就会重新领。逐条提交，某条失败不影响其他条，结果会写明成功几条、哪条没成功。远端服务版本旧、没有这个接口时，提示会直接说明需要部署新版摄入服务。

选一条任务后，右侧错误框旁边有「排查原因」。点开对话框后，插件先在本机把证据收一遍，再让默认模型基于证据给结论：

- 远端错误原文与任务字段（worker、尝试次数、耗时）；远端查不到这条任务（或接口挂了）时退回前端任务快照，界面会标出来；
- `/runs/<id>` 的阶段记录，以及阶段之间最大的空档——超过 90 秒单独列出，常见于租约/心跳掉线或抓取被源站卡住；
- 本机 vault 的 git 状态（未提交数、落后/领先 origin、最后一个提交），失败任务该落的文件在不在，以及这篇是否已经在 Inbox、本地整理任务是否也失败；
- 本机对源站发一次 GET（跟随重定向，只读前 220KB），看状态码、标题，以及验证码 / 已删除 / 要求微信内打开 / 登录墙这些页面标记。内网地址（localhost、10/8、192.168/16 等）直接跳过，不往本地服务打请求。

界面上先把这些证据按「检查清单」列出来（红 / 黄 / 绿 / 灰四级），再流式输出模型结论，固定四段：**结论**（分类 + 置信度 + 问题在远端 worker、本机 vault/git 还是源站）、**证据**、**怎么修**、**重试与验证**。模型只依据这份证据，不允许建议 `git reset --hard`、删 vault 文件、清空队列这类不可逆操作。

模型看不到的信息（比如「刚重启了 mac-mini 上的 worker」）写在对话框底部的输入框里，点「带上补充重新排查」整轮重跑；「复制结论」把机器证据和模型结论一起拷成 Markdown。证据是现场快照，修完再排查一次看清单变化，比记结论可靠。

## 写入边界

插件会写 `00 Inbox/YYYY/MM/DD/*.md`（学习沉淀、手动录入）、`02 outputs/drafts|health/*.md`（草稿、体检报告），以及整理时按上面的规则写 `00 raw/`、`01 wiki/`（summary、概念页增量、索引、日志）。git 提交只在自动闭环收尾（只 add 上面这些路径）或点「提交并推送」时发生。

## 学习模式的设计取舍

发散阶段问的是「一次学习到底在解决什么问题」，收敛阶段只保留能验证的那几条：

1. **定位**——为什么读它。它回答你哪个具体问题，还是只是看起来相关。
2. **拆解**——结论 / 机制 / 前提三层，标出哪层最脆弱。
3. **连接**——和你已有认知冲突的具体句子，不写「相关」这种废话。
4. **输出**——下一个动作 + 怎么验证有效。

对应到交互：左边是证据（原文，可点选段落当引用），右边是压缩（对话只回答这四问之一，默认反问一次再展开），最后一步必须能落地成 Inbox 笔记。刻意不做的事情：不做全文摘要（那是摄入该做的）、不做多轮闲聊、不做「相关推荐」（连接要具体到句子）。

默认节奏是**先出初稿、你只做删改**：打开链接后自动生成四条判断（每条 1–2 句，必须指向原文一句原话），你要么点「展开这条」让它按「结论 / 机制 / 前提」深挖，要么「划掉」认为不成立的那条，要么直接在下面提问。理由：读一篇新东西时，最贵的是「提出好问题」这一步，把它外包出去，人只保留判断和否决；一问一答的模式留作补充，不设为默认。

## 开发

纯 ESM，无构建、无第三方依赖：

```bash
node --check index.js && node --check lib/*.js && node --check client.js
node --test tests/*.test.mjs   # lib/diagnose.js 的错误归类、源站探测与证据拼装
```

改 `lib/*.js` 后需要重启 DSH 进程才生效（ESM 按 URL 缓存，插件开关只重新挂载不重新 import）；改 `client.js` 刷新页面即可。
