# 官方抽赏追踪

维护企微智能表格「官方抽赏类商品追踪」（`s3_Af0A3AZAAEcCNLf1EXDRzSXK0El6U`）：按品牌抓新发售赏盘，按赏盘补子品结构。

表结构：`赏盘信息`（`tmNNY2`，一行一个赏盘）↔ `子品信息`（`tKst6t`，双向关联，一行一个赏）。价格与「共N个X赏」都在代理版官图里，因此整条链路的核心是**下载官图 + 本地 OCR**。

## 定时巡检

每周一、周五 10:00（Asia/Shanghai）跑一次「看有没有新发售的盘，补进表里」，**扫描窗口是发售日期在 [今天−30 天, 今天] 的盘**，更早的不扫，流程与验收见 [`docs/weekly-check.md`](docs/weekly-check.md)。这条定时任务由会话内的 schedule（id `schedule-1dbaeb55`）触发，**只负责发起**。

抓取分两阶段，**workbuddy 和 bitto 都要用**：

- **阶段 1 · 发现**：窗口内每个登记品牌，把同一个问题分别发给 workbuddy 和 bitto（「这 30 天发售了哪些盘」），取并集、按商品名称去重、标来源，冲突走官方渠道核实。
- **阶段 2 · 补信息**：每个候选盘按「workbuddy → bitto → 官方渠道」补单抽价 / 整套抽数 / 子品结构；**缺一项即算失败**，不允许部分写入。二手渠道（千岛、抖音、聚合站）只能确认「有没有发售、哪天发售」，价格与结构不采信。B站会员购数仓已停用（多为商家自组盘配比）。

每轮的发现步骤由**两个本地 Agent 并查**完成（workbuddy + bitto），不再用 `brand_sweep.py`（2026-10-23 停用：只扫微博，且与双 Agent 重复）。两个都报「该品牌无新盘」时，仍要按官方渠道复核一轮——2026-03～05 就是因为只查一番赏漏了好物赏 8 套、英雄赏第 4 弹、KAYOU赏银魂、另物赏 FATE。

## 唯一真源与迭代规则

品牌信息源只有一份：[`references/brand-sources.md`](references/brand-sources.md)。两个 Skill 的第一步都是读它，最后一步都是回写它（新品牌加行、状态升级、新坑入档、更新日志加一行）。别在别处另抄一份，也别凭记忆走上次的路径。

## 技能

| Skill                                                        | 用途                     |
| ------------------------------------------------------------ | ---------------------- |
| [`new-lineup-by-brand`](skills/new-lineup-by-brand/SKILL.md) | 输入品牌，抓已发售赏盘并写 `赏盘信息`   |
| [`lineup-subitems`](skills/lineup-subitems/SKILL.md)         | 输入赏盘，补每个赏的单套数量到 `子品信息` |

## 最短路径

```bash
# 0) 发现窗口内新盘：同一个问题分别发给 workbuddy 和 bitto，取并集去重
#    workbuddy 走本地 Agent 接口（backend=workbuddy，allowed_tools=["WebSearch","WebFetch"]）
#    bitto 走本地 sidecar；两边都空 → 按 brand-sources.md 的官方渠道复核一轮

# 1) 拉官方微博时间线（走 ego-browser 已登录会话）
#    ego-browser 不继承父进程 env，参数要写进包装脚本
printf 'process.env.WEIBO_UID="7324393029";process.env.WEIBO_PAGES="30";await import("%s");\n' "$PWD/scripts/weibo_timeline.mjs" > runtime/_wb.mjs
ego-browser nodejs < runtime/_wb.mjs
# → <workspace>/runtime/weibo_7324393029.json

# 2) 下载某条帖子的官图并 OCR，打印「共N个X赏 / 1次N元」
python3 scripts/ocr_post.py --posts runtime/weibo_7324393029.json --match "Magical Holiday" --dir runtime/ocr/hp

# 3) 读表拿到 record_id 和赏别
wecom-cli smartsheet records list --docid "<docurl>" --sheet-id tKst6t --type records --limit 1000 -o runtime/zipin.json

# 4) 写回（文本字段值是 JSON 字符串；数字字段传裸数字）
wecom-cli smartsheet records update --docid "<docurl>" --sheet-id tKst6t --type update \
  --key-type CELL_VALUE_KEY_TYPE_FIELD_TITLE \
  --records '[{"record_id":"cSozUC","values":{"单套数量":"2"}}]'
```

## 依赖

- `ego-browser`：访问已登录的微博会话（`ego-browser nodejs < script.mjs`）。
- `swiftc` + macOS Vision：OCR。`scripts/ocr_post.py` 首次运行会用 `swiftc -O scripts/ocr.swift -o scripts/ocrbin` 自动编译。
- `Pillow`：竖长图切段。
- `curl`、`wecom-cli`（`smartsheet` 子命令，非老版 `doc` 子命令）。

## 目录

| 路径                            | 作用                                                 |
| ----------------------------- | -------------------------------------------------- |
| `scripts/brand_sweep.py`      | **已停用（2026-10-23）**：只扫微博、与双 Agent 重复；文件保留但不再作为流程步骤 |
| `scripts/weibo_timeline.mjs`  | 拉账号时间线 → `runtime/weibo_<uid>.json`                |
| `scripts/ocr.swift`           | Vision OCR 可执行源，输出逐行文本                             |
| `scripts/ocr_post.py`         | 下载帖子官图、切段、OCR，打印候选行                                |
| `docs/weekly-check.md`        | 周一/周五巡检的流程、去重口径与验收                                 |
| `references/brand-sources.md` | 各品牌的一手信息源、价格/构成在哪、验证状态                             |
| `skills/`                     | 两个业务 Skill 的唯一真源                                   |

`runtime/` 下的图片、JSON 都是一次性产物，不提交。

## 最小验证

1. `references/brand-sources.md` 能过自检：「官方信息渠道」表每个品牌一行、状态只取 `已验证 / 待验证 / 失效 / 无`；「微博账号索引」里的 uid 都是 4–12 位数字。
2. 两个 Agent 都能跑通：`agent_status(backend="workbuddy").execution_ready == true`，且对同一个品牌各返回一次结果；任一失败时流程能继续走下一级。
3. `ocr_post.py` 对一个已知盘能打印出 `共N个A赏` 这类行，且封面上能读到 `1次N元`。
4. 单盘校验：`Σ各赏数量 == 官图标注的兑换券总数`（LAST 不在其中，固定 1 个）。
5. 写后重读该盘子品行，确认无空值，且抽查 2 行与官图一致。

## 已知边界

- 国内品牌（好物赏、另物赏、磁力赏、英雄赏、KAYOU赏、乐淘赏、天降鸿运、万花赏、秦赏令等）没有「共N个X赏」官图，价格也不带建议零售价：价格写 `未公布`、不写子品、交付列缺源清单，口径见 [`docs/weekly-check.md`](docs/weekly-check.md) 与 [`lineup-subitems`](skills/lineup-subitems/SKILL.md)。逐个品牌的信息源与验证状态见 [`references/brand-sources.md`](references/brand-sources.md)，**动手前先读它，别再从微博搜索开始试**。
- 微博搜索会漏帖，一律以账号时间线为准；时间线取不到时再用关键词搜索兜底。
