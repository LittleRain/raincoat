# dsh/ — 个人向 DSH 插件

放**不绑定工作业务**的 DeepSeek Harness 插件：双端会话、界面增强、模型通道这类自己天天用、但和工作交付无关的东西。

工作相关的 DSH 插件（赏类工作台、惊喜赏工作台、知识库提交与运维、目标追踪……）在 [`LittleRain/workspace`](https://github.com/LittleRain/workspace) 的 `plugins/` 下；ACG 抓取类在 [`LittleRain/acg_hot`](https://github.com/LittleRain/acg_hot) 的 `plugins/` 下，都带 `dsh-` 前缀。

## 现有的

| 目录 | 包名 | 干什么 |
| --- | --- | --- |
| `dsh-recent-workspace/` | `dsh-recent-workspace` | 侧栏「最近」分区：把最近活跃的 8 个会话提到工作区列表顶部 |
| `dsh-peer-bridge/` | `@local/dsh-peer-bridge` | 双端会话：桌面端与 web 端谁持有写锁可见、另一端只读跟随、一端切换 |
| `raincoat-kb-desk/` | `@local/raincoat-kb-desk` | 个人知识库工作台：摄入队列、体检、URL 学习、公众号/小红书选题 |

`dsh-notify`（任务完成通知）目前在 `main` 分支的 `apps/` 下，迁入待做；`dsh-our-free-model` 留在 `~/Documents/deepseek-harness/default-workspace`，不进仓库。

## 装到本机

插件是 bundle 包，用 profile 的 `link:` 依赖安装（不要手写 profile 的 `package.json`，走插件管理器或插件自带脚本）：

```bash
# 通用：应用内 Plugins → 安装本地 bundle → 选目录
# dsh-recent-workspace 自带脚本
node dsh/dsh-recent-workspace/scripts/install-profile.mjs web
node dsh/dsh-recent-workspace/scripts/install-profile.mjs desktop
```

装完要重启对应实例才生效（web 用 `launchctl kickstart -k gui/$(id -u)/co.dsh.web`；桌面端退出重开）。

## 新增一个插件时的约定

- 一个插件一个目录，目录名 = 包名（`@local/` 前缀可有可无，但目录和包名别不一致）。
- 必须带 `cordis.patch.yml`（`dsh.bundle.patch`）和 `locale/{zh,en}.json` 的 `meta.title/description`，插件管理器靠它显示标题。
- 不要把运行时数据写进仓库目录：统一落 `~/.dsh/<插件名>/`。
- 不要 vendored 依赖或 `node_modules`；需要构建的话把产物提交进来，让目标机器零构建安装。
