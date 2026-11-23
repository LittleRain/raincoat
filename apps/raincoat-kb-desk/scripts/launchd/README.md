# 本机常驻任务的 launchd 配置

这两个 agent 让摄入闭环在没有 DSH 界面时也能跑：

| Label | 作用 | 频率 |
|-------|------|------|
| `com.rain.kbworker.local` | 抓取端 worker：从 `/jobs/claim` 领任务，把稿写进 `00 Inbox/`，不碰 git（`KB_LOCAL_ONLY=1`） | 常驻，60s 一轮 |
| `com.rain.kb.watchdog` | 看门狗：查闭环心跳、队列是否被消费、worker 心跳、新增失败、磁盘 | 每 600s |

## 为什么用 Electron 二进制跑 node

launchd 拉起的 `/usr/bin/node`（或 nvm 里的 node）**读不了 `~/Documents/ob_vault`**：Obsidian / DSH 写入的文件带 `com.apple.macl`，普通进程 `open` 会**阻塞**（不是报错），整轮任务就挂死在那儿。实测：同一台机器上 `node -e 'fs.readdirSync(vault)'` 从 launchd 起会永远卡住，但列表、读取都正常。

`/Applications/DeepSeek Harness.app/Contents/MacOS/DeepSeek Harness` 带着应用自己的 TCC 授权，用 `ELECTRON_RUN_AS_NODE=1` 跑同一个脚本就能正常读写，而且升级 node 不会失效。所以 worker 的 plist 用：

```sh
exec env ELECTRON_RUN_AS_NODE=1 "/Applications/DeepSeek Harness.app/Contents/MacOS/DeepSeek Harness" dist/worker.js --loop 60
```

看门狗用同一个二进制直接跑仓库里的 `scripts/watchdog.mjs`（不复制副本，改完下个 10 分钟自然生效）；普通的 `node` 连 `~/Documents/GitHub/...` 下的脚本都打不开，所以它也用 Electron。

## 安装

```sh
cp scripts/launchd/com.rain.kbworker.local.plist ~/Library/LaunchAgents/
cp scripts/launchd/com.rain.kb.watchdog.plist ~/Library/LaunchAgents/
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rain.kbworker.local.plist
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.rain.kb.watchdog.plist
```
