# dsh 双端会话（`@local/dsh-peer-bridge`）

桌面端（自带 host）和 `dsh web`（launchd 常驻）同时开着时，让**只有一个端在写、另一个端只读地跟着看**。

合并自三个插件：`@local/dsh-open-in-peer`（在另一端打开）、`@local/dsh-session-handoff`（处理权可见 + 分叉交接）、`@local/dsh-workspace-reconciler`（两端会话列表对账）。分叉与投递已被去掉。

## 它不做什么

- **不自动换手**：让出写锁只在用户点「切到本端」时发生，且只在被请求的那一端动手。平时两个宿主各写各的会话。
- **不修改核心包**：核心没有 release/detach 原语，插件是拿公开的 `ctx.sessionPersistence` 开出来的写句柄，靠 `handle.close()` 让 flock 随 fd 关闭释放。
- **不把登录 token 交给对端**：对端只拿到「能不能放出这条会话」的回执，拿不到浏览器会话。
- **不投递**：一端打的字不会被送到另一端执行。另一端的输入注定失败，插件只负责提前说清楚。
- **不分叉**：不在对端生成副本会话。同一时刻只有一条线。

## 它做什么

1. **对端发现**：每个宿主把回环地址、profile、带进程 token 的 URL 写到 `$DSH_HOME/handoff/peers/<pid>.json`（10 秒心跳、40 秒过期），并回答"我持有哪个会话"。两端读完拼成一张表。
2. **只读打开**：把对端的带 token 地址交给浏览器，在新标签页里落到同一个会话上；那边能看到完整历史。
3. **增量提示**：只读端比较会话的 `updatedAt`，发现对端写了新内容就在输入框上方提示"刚写了新内容 · 刷新"。
4. **让出写锁（`/release`）**：点「切到本端」时，请持有方关掉它的写句柄，把会话让过来；让出的那一端标成「已让出（本端冻结）」。详见下面「换手怎么换」。
5. **管理页**：侧栏「双端会话」入口，一张表列出会话 / 工作区 / 最后活动 / 状态 / 持有方，可按「运行中 / 本端持有 / 对端持有」筛选。
6. **会话头徽标**：显示当下谁持有（本端 / 桌面端 / Web 端 / 空闲），菜单里可以直接"在对端打开（只读）"或复制会话 ID。
7. **workspace 对账**：把两端的分组/顺序/归档集收敛成「会话目录的纯函数」，每 60 秒（启动后 1 秒）对一次账。DSH 的注册表是内存权威 + 整文件回写，两个 host 会互相覆盖；不对账就会出现「web 的对话列表和桌面端不一样」。跨 host 的归档真源在 `~/.dsh/workspace-reconciler/state.json`，状态报告在 `status-<pid>.json`。

## 换手怎么换

在这条会话所在的面板里点「切到本端」：本端请对端放掉写锁，然后自己打开这条会话。

对端放出锁的方式是关掉它手里那个写句柄，因此**对端会进入「已让出（本端冻结）」状态**——历史还能看，但已经写不进去了，要继续用那一端得重启它。这是不改核心的代价，界面和下面这张表都按「冻结」而不是「平滑移交」来说。

各种异常都会被翻译成一句人话加下一步：

| 情况 | 提示 |
|---|---|
| 能放出 | 正常打开；对端标成「已让出（本端冻结）」 |
| 放不出（这条会话在插件开始记账之前就打开了，通常是宿主启动时自动恢复的那条） | 报 `still-held`，指引退出本端应用（Cmd+Q）再重开 |
| 宿主没接上 `sessionPersistence`（DSH 版本不匹配） | 报 `still-held`，说明只能重启释放 |
| 正在跑回合 | 报 `busy`，让等这一轮跑完，避免切断生成中的内容 |
| 本端已冻结过 | 报 `frozen`，要求重启本端再接，避免把死句柄传下去 |
| 会话已经不在对端手里 | 报 `not-held`，直接在本端打开 |
| 对端不在线 / 请求失败 | 报 `peer-unreachable`，保留原会话不动 |

设置 `DSH_PEER_BRIDGE_PROBE=1` 后可以 `POST /dsh-bridge/api/_probe`，看一眼记账到底有没有生效（`writeCaptured`、`persistenceTapHits`）。DSH 升级后第一时间跑它，比等用户点按钮失败快。

## 升级兼容（DSH 0.2.2 起）

carrier 在路由之前统一鉴权，默认策略是「必须带浏览器 cookie」。宿主之间只有回环 + `x-dsh-bridge`，
永远拿不到 cookie，于是 `/dsh-bridge/api/held` 一律 401，两端互相判成离线（`alive:false`、`heldIds:[]`）：
「双端会话」面板里对端持有的会话显示成空闲，接管和只读入口都不出现。

修法两处：

1. 路由注册带 `auth` 策略（`index.js`）：只对「回环 + 带 `x-dsh-bridge` 头 + 只打 `/held`、`/release`」
   的请求返回 `anonymous`，交给插件自己的 `authorizePeer` 校验；`/overview`、`/sessions` 等浏览器路由
   仍是 `required`，不走这个旁路。
2. `authenticatedUrl` 改成每次心跳重算（原来只在插件启动早期算一次，拿不到就写死裸 origin）。
   注意：DSH 0.2.3 的宿主已经不把 `authenticatedUrl` 挂在 `connection` 上（实测为 `undefined`），
   所以新版上 peer 记录里的 `url` 仍是裸 origin，「在对端打开」会落 401；这一项等宿主给出可用入口再补。
   影响面仅限「新标签页打开对端」，面板识别持有、只读提示、接管都不依赖它。

改完两端都要重启才生效：web 端 `launchctl kickstart -k gui/$(id -u)/co.dsh.web`，桌面端 Cmd+Q 重开。

## 安装

```bash
bash scripts/install.sh
```

脚本对每个 profile：摘掉 `@local/dsh-open-in-peer` 与 `@local/dsh-session-handoff`，写入 `link:` 依赖、加进 `dsh.profile.bundles`、建软链，备份原 `package.json` 成 `package.json.bak-<时间戳>`。`headless` profile 会被跳过（没有浏览器 UI，装上只会变成假的交接目标）。幂等。

装完重启两个宿主才生效：

```bash
launchctl kickstart -k gui/$(id -u)/co.dsh.web   # web host（会中断当前页面，token 会换）
# 桌面端：Cmd+Q 完全退出后重新打开
```

## 验证

```bash
ls ~/.dsh/handoff/peers/      # 每个存活宿主一个 <pid>.json，带 profile 与 label
ls -l ~/.dsh/handoff/secret   # 0600，两端读到同一份
```

页面里：侧栏出现「双端会话」；会话右上角有徽标；被对端持有时输入框上方出现只读提示；被对端占用时每行多一个「切到本端」。

会话不是本端打开时（对端持有，或本端已经让出过写锁），会话头徽标旁边会多一个「双端会话」按钮：点它直接跳进面板、只留这一条，顶上带「显示全部」可以退出筛选。这样从对话里发现「这条不归我写」时，不用再去侧栏找面板。

同一个会话，输入框上方还有一条只读提示条，按钮就在提示条右边，分三步走：

1. **接管到本端**：点一次变成「确认接管」，再点一次才真的请对端放掉写锁、在本端打开这条会话。中间留这一步，是因为对端那条会话接管后会冻结（还能读，写不进去），要恢复得重启对端。对端正跑着回合时按钮是灰的，等它跑完再点。
2. **在双端会话里看**：不换手，只跳到面板、聚焦这一条。面板顶上变成一条操作条：`切到本端` · `在对端打开` · `← 回到刚才的会话` · `显示全部`，这个会话那一行带左边一条品牌色高亮并滚到视口中间，按 Esc 退出聚焦。
3. **回程**：从面板点回会话（「← 回到刚才的会话」、行标题、或任何打开会话的动作）都会清掉聚焦，地址栏里的 `#dsh-bridge-session=…` 一起清掉。

「跳到面板看这一条」也能给链接：在任一端打开 `http://<host>/#dsh-bridge-session=<sessionId>`，会直接进面板并聚焦这条（刷新后仍然聚焦，hash 留在地址栏里）。对端打开会话的老链接 `#dsh-bridge-open=<sessionId>` 仍然可用。

想确认「让出写锁」在这个宿主上真的可用，看 `/overview` 里的 `writeTap`：

```json
"writeTap": { "installed": true, "hits": 3, "selfCheck": { "ok": true } }
```

`installed` 只说明包上了方法，`hits` 和 `selfCheck` 才说明真的拦到了句柄。`selfCheck.ok === false` 时页面顶部会出现一条黄色说明，此时「切到本端」只能提示对端重启。

## 接口

| 方法 | 路径 | 鉴权 | 用途 |
|---|---|---|---|
| GET | `/dsh-bridge/api/overview` | 浏览器同源 | 徽标 / 提示条 / 管理页的唯一数据源 |
| GET | `/dsh-bridge/api/held` | 回环 + `x-dsh-bridge` 共享令牌 | 对端自述持有情况 |
| GET | `/dsh-bridge/api/sessions` | 浏览器同源 | 纯会话列表 |
| POST | `/dsh-bridge/api/release` | 浏览器同源，或宿主令牌 | 让出这条会话的写锁（`{sessionId, toPid?}`）；带 `toPid` 时由本端转给对端执行 |
| POST | `/dsh-bridge/api/diagnose` | 宿主令牌 | 某条会话能不能被拆：`captured` / `writeCaptured` / `frozen` 等 |
| POST | `/dsh-bridge/api/_probe` | 宿主令牌 + `DSH_PEER_BRIDGE_PROBE=1` | 自检台账是否真的生效；会顺手调一次 release |

## 测试

```bash
node --test test/*.test.js
```
