# dsh-recent-workspace

给 DSH 侧栏工作区列表加一个「最近」分区：把最近活跃的会话提到最上面，按最近一次用户提问的时间排序。

它就是侧栏里那第一个分区，不是新面板、不是新按钮：

```
Workspaces                    ← 分区标题（搜索 / 视图选项 / 添加工作区）
  Recent                      ← 本插件加的「最近」分区，可折叠
    本地Agent MCP接入Antigravity   50min
    ACG商品定期抓取工作流设计       3h
    …最多 8 行
  Default workspace
  ob_vault
  …
```

## 显示规则

| 维度 | 行为 |
| --- | --- |
| 分区位置 | 工作区列表最顶部；折叠状态记在 `dsh.workspace.view.v5` 的 `groupExpansion.__recent__` |
| 排序 | 严格按 `updatedAt`（= 最后一次**用户**提问时间，automation 触发不算），置顶不影响顺序 |
| 条数 | 最多 8 行，超出不进「展开其余」；会话总数少于 8 时按实际数量 |
| 与工作区分组的关系 | 允许同一个会话出现两次（上面 lens，下面原位置）——这是设计意图 |
| 归档筛选 | 跟随「隐藏已归档 / 全部对话 / 仅显示已归档」三态 |
| 空会话 | 空白新会话不进「最近」 |
| 分组方式 = 按工作区树 | 不显示（树模式下不插入顶部分区） |
| 分组方式 = 单列表 | 不显示（单列表本身就是全量按时间排） |
| 排序 = 手动排序 | 不显示（手动模式下顶部插入会破坏拖拽顺序） |
| 搜索态 | 不显示（搜索结果有独立列表） |
| 语言 | 跟随 DSH 语言：中文「最近」/ 英文 Recent / 日文 最近 / 其它语言同理 |

行本身完全复用官方会话行：置顶标记、Running、automation 徽标、悬停操作（归档 / 置顶）、右键菜单、点击打开都一样。

## 安装

### 本机（已装好）

`web` 与 `desktop` 两个 profile 都已注册。`web` 实例即时生效；`desktop` 下次启动桌面 app 时生效。

### 别的设备

把这个目录拷过去（或放 git 仓库里 clone），然后：

```bash
# 方式一：应用内插件管理（推荐）
# 打开 Plugins → 安装本地 bundle → 选这个目录

# 方式二：脚本，写 profile 的 package.json + bundles + node_modules 链接
node scripts/install-profile.mjs web        # 浏览器 GUI
node scripts/install-profile.mjs desktop    # 桌面 app
```

脚本做的事和插件管理器一致：`dependencies["dsh-recent-workspace"] = "link:<本目录>"`、`dsh.profile.bundles` 追加一项、`node_modules/dsh-recent-workspace` 建符号链接，改前备份 `package.json`。跑完重载对应实例即可。

### 卸载

插件管理器里停用/删除，或从 profile 的 `package.json` 去掉依赖与 `bundles` 项，再删 `node_modules/dsh-recent-workspace`。停用后侧栏立即回到官方版本（官方 ui-workspace 包没被改动，只是被 `cordis.patch.yml` 禁用了一行）。

## 工作原理

DSH 0.2.x 的侧栏只有 `sidebar.workspaces` 一个 single slot，由 `@deepseek-ai/dsh-client-ui-workspace` 独占，没有分区级扩展点。所以本插件不是「往别人的 DOM 里塞东西」，而是**接管这个 slot**：

`cordis.patch.yml` 禁用官方那一行，插入自己：

```yaml
- id: ui-workspace
  name: '@deepseek-ai/dsh-client-ui-workspace'
  disabled: true
- insert:
    - id: recent-workspace
      name: dsh-recent-workspace
```

`lib/client.js` 是官方客户端 bundle 的**补丁拷贝**：构建时从本机安装包读取 `@deepseek-ai/dsh-client-ui-workspace/lib/client.js`（未压缩、可读），按锚点做 16 处字符串替换，插进「最近」分区的派生逻辑、折叠、标题文案与行渲染参数。替换全部基于注释/字号不会漂移的短锚点，任一锚点匹配数不是 1 就构建失败，不会产出半成品。

## 构建 / 升级 DSH 之后

```bash
node scripts/build.mjs --check   # 只校验锚点，不写文件
node scripts/build.mjs           # 生成 lib/client.js，写 lib/build-meta.json
```

`lib/build-meta.json` 记录上游版本、字节数、命中的锚点。**DSH 升级后先跑 `--check`**：全部命中就直接重建；哪个锚点报错，就照着报错里的 `find:` 字符串去新的 `lib/client.js` 里找对应代码并更新 `scripts/build.mjs`。锚点集中在 8 个位置（prelude、SessionTree props、groups 派生、水位线、折叠、行标题、SessionTree 调用参数、locale 字典）。

当前对齐上游 `0.2.3-alpha.2`（记录在 `lib/build-meta.json`）。DSH 官方若将来自己做了「最近」分区，本插件可以直接退场。

## 目录

```
index.js                 宿主半边（空 apply，只为出现在 Loader 里）
lib/client.js            构建产物：官方 bundle + 本插件的补丁
lib/build-meta.json      上游版本 / 字节数 / 锚点清单
src/recent.prelude.js    注入到 bundle 模块作用域的「最近」派生逻辑（唯一手写逻辑）
scripts/build.mjs        读取上游 → 锚点替换 → 写 lib/client.js
scripts/install-profile.mjs  把插件注册进指定 profile
cordis.patch.yml         禁用官方 ui-workspace，插入自己
locale/{zh,en}.json      插件元信息（分区标题来自 bundle 内的 locale 字典补丁）
icon.svg                 插件图标
```

## 已知取舍

- **依赖上游内部结构**：补丁打在官方 bundle 上，DSH 升级可能让某个锚点失效——`--check` 会直接报出来，不会静默降级。
- **树模式 / 单列表 / 手动排序不显示**：见上表，是刻意规则，不是遗漏。
- **同一会话重复出现**：上面「最近」一次，下面所属工作区一次；两处都是活的行，操作互不影响。
- **与官方包同 ID 的 slot 竞争**：靠 `disabled: true` 让位，两者不会同时注册。
