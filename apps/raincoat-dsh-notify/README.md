# dsh-notify

> 规范位置：`raincoat` 仓库的 `apps/raincoat-dsh-notify`（原先在
> `deepseek-harness/default-workspace/dsh-notify`，已同步过去）。**只在前者改代码**；
> 如果在 `default-workspace/dsh-notify` 看到这份 README，那是临时镜像，别在那里改。
> 包名与 patch entry id 仍然是 `@local/dsh-notify` / `dsh-notify`，避免和 profile 里已有的 entry 重复。

DeepSeek Harness 任务完成后，给你推一条**系统通知**：macOS 通知中心原生提醒 + 提示音，
可选再转发到手机（Webhook / Bark / ntfy / 企业微信 / 飞书）。

目标是"你可以安心切走"：盯着 DSH 时不打扰，切走后才提醒；长目标只在真正完成/受阻时提醒一次。
点击通知会唤起 DeepSeek Harness 窗口，并切到触发这条通知的那条会话（默认用插件内置的 terminal-notifier 发送）。

## 触发规则

| 事件 | 默认 | 说明 |
| --- | --- | --- |
| 一轮对话完成 | ✅ | 正文带助手最后一段回复的摘要（去 Markdown、超长截断） |
| 一轮对话出错 | ✅ | 正文带错误信息 |
| 一轮对话受阻 | ✅ | `turn/end` 原因为 `blocked` |
| 目标（goal）完成 | ✅ | 自主推进的目标跑完时提醒一次 |
| 目标受阻 | ✅ | 带受阻原因 |
| 目标进行中的每一轮 | ❌ | 目标自动推进时静默，避免每轮都弹 |
| 子 Agent 收尾 | ❌ | 子 Agent 的轮次不打扰 |
| 后台任务结束（`job/settled`） | ❌ | 默认关闭；开启后只报超过阈值的长任务 |
| 手动停止 / 输出达到上限 | ❌ | 可在 `onTurns` 里加 `aborted` / `max-tokens` |

额外两条"降噪"规则：

- **只在前台之外提醒**（`onlyWhenBackground`）：`lsappinfo` 检测到 DeepSeek Harness 在前台就跳过；
- **太短的任务不提醒**（`minDurationMs`，默认 6 秒）：一问一答的碎操作不弹窗。

每条决策（包括"因为在前台被跳过"）都会写进 `~/.dsh/notify/history.jsonl`（保留最近 20 条），方便排查。

## 点击通知：唤起 DSH 并切到那条会话

| 后端 | 点击后 | 说明 |
| --- | --- | --- |
| `terminal-notifier`（默认，插件内置） | 激活 **DeepSeek Harness**，1 秒内切到对应会话 | `-activate` 唤起 + `-execute` 投递会话 id；同一会话用 `-group` 合并，不会堆一屏 |
| `osascript`（回退） | 打开 **Script Editor**，或没反应 | AppleScript 通知没有点击动作，这是 macOS 的行为，不是插件能控制的 |

DSH 本身没有会话级深链（只有 `dsh://open`），所以"跳到那条会话"由插件自己补：

```
点击通知
  └─ terminal-notifier -execute（本机 curl，带令牌）
       └─ POST <origin>/dsh-notify/open?session=<id>
            └─ 浏览器半边（client.js）每 1.2s 轮询 /dsh-notify/pending
                 └─ ctx.uiWorkspace.openSession(<id>)
```

两个容易踩的坑都在 `lib/http.js` / `lib/open-requests.js` 里处理掉了：

- **准入策略**：DSH 的 WebServer 默认按 `required` 做路由准入，点击命令是没有浏览器
  Cookie 的本机 curl，会被准入层直接 `401 unauthorized`，请求根本到不了 handler。
  所以 `/dsh-notify` 这条 prefix 路由显式声明 `auth: routeAuth`：`POST /open` 走
  `anonymous`（身份由 `x-dsh-notify-token` 校验），`GET /pending` 仍要求登录态。
- **origin 落盘**：Desktop 每次启动的端口是随机的，通知里的命令如果写死
  `http://127.0.0.1:<当时的端口>`，重启后点旧通知只会打到一个没人监听的地址。现在命令里
  写的是 `$(/bin/cat ~/.dsh/notify/origin)`，令牌同理，都在**点击那一刻**才读文件。

其余约定：

- 请求 60 秒内有效，同一个会话只会被取走一次；
- 同一时间只保留一条待打开请求（后点覆盖先点）；
- 如果客户端半边没加载（或旧版本页面没刷新），点击仍然会唤起 DSH，只是不切会话；
- App 已经退出时点击不会留下待打开请求（命令没人接收），重新打开后也不会补跳；
- 想关掉跳转、只保留唤起：`clickToOpenSession: false`。

排查"点了没切过去"：

```bash
node scripts/open-session.js <sessionId>   # 绕过通知点击，直接投递一次打开请求
tail -1 ~/.dsh/notify/history.jsonl        # 拿最近的 sessionId

# 点击到底打通没有：这两条能区分「准入拦截」和「handler 逻辑」
curl -s -o /dev/null -w '%{http_code}\n' "http://127.0.0.1:<port>/dsh-notify/pending"   # 401 = 路由准入拦截（没登录态）
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  -H "x-dsh-notify-token: $(cat ~/.dsh/notify/token)" \
  "$(cat ~/.dsh/notify/origin)/dsh-notify/open?session=<sessionId>"                     # 200 = 投递成功
```

`/dsh-notify/*` 返回 401 且响应体是 `unauthorized`（不是插件自己的 JSON），说明请求停在
WebServer 准入层：检查这次挂载是否带上了 `auth: routeAuth`（老版本没有这一行），或者插件
是从旧目录加载的。

插件内置的是 terminal-notifier 2.0.0（官方 release，MIT，x86_64，走 Rosetta）。它已经被
`lsregister -f` 注册过；换机器或移动目录后要重新注册一次，否则点击时 macOS 找不到应用：

```bash
lsregister=/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister
"$lsregister" -f "$PWD/bin/terminal-notifier.app"
```

不想要这个内置二进制，可以把 `backend` 设为 `osascript`，或删掉 `bin/` 让它自动回退。

## 安装

本机已经装好（`~/.dsh/profiles/desktop`），指向的就是本目录：

- `package.json`：`dependencies` 里 `"@local/dsh-notify": "link:<本目录绝对路径>"`，
  `dsh.profile.bundles` 末尾加了 `@local/dsh-notify`；
- `pnpm-lock.yaml`：补了对应的 `link:` importer 条目；
- `node_modules/@local/dsh-notify` 指向本目录。

**改完 profile 需要重开一次 DeepSeek Harness**（bundle 列表在启动时读取）。

> 注意：`dsh plugin --profile desktop add …` 目前会在本机失败——profile 里已有的
> `dsh-context@0.74.0` 触发了 pnpm 的 `minimumReleaseAge` 供应链策略，导致整次安装回滚，
> 与这个插件无关。所以这里用的是手动 link 的方式。

从旧目录迁移过来（`default-workspace/dsh-notify` → 本目录）时，只改 link 目标，别新增 entry：

1. `~/.dsh/profiles/desktop/package.json`
   - `dependencies["@local/dsh-notify"]` 改成 `"link:<本目录绝对路径>"`
   - `dsh.profile.bundles` 已有的 `"@local/dsh-notify"` 保持不动（不要重复添加）
2. `~/.dsh/profiles/desktop/pnpm-lock.yaml` 的 `importers['.']` 里同样更新这一条 `link:` 路径
3. `ln -sfn <本目录绝对路径> ~/.dsh/profiles/desktop/node_modules/@local/dsh-notify`

然后重开 DeepSeek Harness。旧目录此时可以删掉，但先确认新路径已经生效（`[dsh-notify] 已启用` 日志）。

卸载：删掉上面三处，重开应用。

```bash
dsh plugin --profile desktop remove @local/dsh-notify   # 能成功时也可以用这个
```

## 配置

默认配置即可用。要调整就在 `~/.dsh/profiles/desktop/cordis.patch.yml` 里按 id 覆盖
（**patch 的 `config` 是整段替换**，没写的字段会落回默认值）：

```yaml
- id: dsh-notify
  name: '@local/dsh-notify'
  config:
    onlyWhenBackground: false   # 盯着看也弹
    minDurationMs: 0            # 每轮都弹
    sound: Glass                # '' 表示静音
    notifyJobs: true            # 长命令跑完也提醒
```

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `enabled` | `true` | 总开关 |
| `onlyWhenBackground` | `true` | DSH 在前台时不弹 |
| `frontmostApps` | `["DeepSeek Harness"]` | 判定"在前台"的应用名（不区分大小写） |
| `minDurationMs` | `6000` | 短于此时长的轮次不弹；`0` 表示都弹 |
| `onTurns` | `["completed","error","blocked"]` | 哪些 `turn/end` 原因要弹 |
| `suppressWhenGoalActive` | `true` | 目标自动推进期间不按轮弹 |
| `notifyOnGoal` | `["complete","blocked"]` | 目标到达哪些阶段要弹 |
| `notifyJobs` | `false` | 是否报后台任务结束 |
| `jobMinDurationMs` | `30000` | 后台任务最短时长 |
| `sound` | `"Glass"` | `Basso` `Blow` `Bottle` `Frog` `Funk` `Glass` `Hero` `Morse` `Ping` `Pop` `Purr` `Sosumi` `Submarine` `Tink`；`''` 静音 |
| `backend` | `"auto"` | `auto` / `terminal-notifier` / `osascript`；auto 优先内置 terminal-notifier |
| `terminalNotifierPath` | `""` | 自定义 terminal-notifier 路径；空表示自动探测（内置 → PATH → Homebrew） |
| `activateBundleId` | `"com.deepseek.dsh"` | 点击通知唤起哪个应用；`''` 表示点击不唤起 |
| `senderBundleId` | `""` | 让通知显示成哪个应用；空表示显示为 terminal-notifier |
| `clickToFocus` | `true` | 是否启用"点击唤起" |
| `clickToOpenSession` | `true` | 点击时是否切到对应会话（需要客户端半边） |
| `locale` | `"zh"` | `zh` / `en` |
| `titlePrefix` | `""` | 标题前缀，例如 `"[DSH] "` |
| `includePreview` | `true` | 正文是否带回复摘要 |
| `previewChars` | `160` | 摘要字符上限（20–400） |
| `historySize` | `20` | 历史保留条数；`0` 关闭 |
| `historyFile` | `""` | 自定义历史文件；空表示 `$DSH_HOME/notify/history.jsonl` |
| `webhook.enabled` | `false` | 远端推送开关 |
| `webhook.url` | `""` | http(s) 地址 |
| `webhook.format` | `"json"` | `json` / `bark` / `ntfy` / `wecom` / `feishu` |
| `webhook.timeoutMs` | `5000` | 请求超时 |
| `webhook.headers` | `{}` | 额外请求头 |

### 推送到手机

```yaml
- id: dsh-notify
  name: '@local/dsh-notify'
  config:
    webhook:
      enabled: true
      format: bark
      url: https://api.day.app/<你的设备 Key>
```

`format` 说明：

- `json`：`{ source, kind, title, subtitle, body, reason, sessionId, cwd, durationMs, timestamp }`
- `bark`：`{ title, body, group: "DeepSeek Harness", level: "active" }`
- `ntfy`：正文纯文本 + `Title` 请求头
- `wecom`：企业微信群机器人 `{ msgtype: "text", text: { content } }`
- `feishu`：飞书机器人 `{ msg_type: "text", content: { text } }`

## 验证

```bash
node scripts/demo.js             # 弹一条测试通知（默认走 terminal-notifier，点击应唤起 DSH）
node scripts/demo.js --osascript # 对比 osascript 的点击行为
node scripts/check.js            # 看平台、通知后端、前台应用、历史文件位置
```

收不到时依次检查：

1. 系统设置 → 通知 → DeepSeek Harness：允许通知、不是"静音"；
2. 是否开着专注模式 / 勿扰；
3. `~/.dsh/notify/history.jsonl` 里有没有记录：
   - 没有记录 → 插件没加载（profile 改完需要重开 DeepSeek Harness）；
   - `"skipped": true` → 当时 DSH 在前台，被降噪规则跳过；
   - `"native": false` 且 `"webhook": false` → 发送失败，看应用日志里的 `[dsh-notify]`。

## 实现要点

- 宿主插件，只订阅 `session/event`（`turn/start` / `turn/end` / `goal/change` / `session/title` / `job/settled`），
  不注册工具、不改会话内容；
- 默认后端是插件内置的 `terminal-notifier`（点击唤起 + `-execute` 切会话），找不到时回退 `osascript`；
  正文经 argv 传入，点击命令里的会话 id 只接受安全字符；
- 浏览器半边 `client.js` 只做一件事：轮询 `/dsh-notify/pending` 后调用 `uiWorkspace.openSession()`；
- 纯决策层（`lib/notifier.js`）不碰 I/O，可完整单测；投递层（`lib/deliver.js`）依赖可注入；
- 非 macOS 平台没有原生通知实现，仍可用 Webhook。

## 开发

```bash
npm test        # node --test test/*.test.js
```
