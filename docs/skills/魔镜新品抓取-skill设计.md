# 魔镜新品抓取 Skill 设计（v2）

目标：按「平台 × 类目」抓取魔镜洞察（market1.mktindex.com）的新品基础信息与销量，近 7 天滚动更新，落成本地结构化数据 + 一份摘要。

已确认的需求边界（2026-11-19）：多平台；近 7 天滚动；只输出本地内容，不接下游；按类目数量分档处理。

标 `TBD` 的项必须在实现阶段、用已登录账号实测后写回 `references/api-notes.md`。

## 0. 实现状态（2026-11-19）

已落地为 [`skills/raincoat-mj-products/`](../../skills/raincoat-mj-products/SKILL.md)：12 个脚本、62 个单元测试（合成数据，无需账号）、配置模板与排障手册。**M1 真实抓取已跑通**（账号 usertype=market）：面膜 2026-10 抓到 100 条（单平台）/ 182 条（all+tmall 合并），CSV/Markdown/xlsx 全部产出。

真实接口与设计假设的差距，比预想的大：

| 设计假设 | 实测结果 | 处理 |
| --- | --- | --- |
| 分页用 DataTables 的 `iDisplayStart/iDisplayLength` | 服务端**忽略**这两个参数，要传 `page`（1 起）+ `page_size` | 客户端改用 page/page_size |
| 榜单可以翻到几百条 | **每个类目每月硬上限 100 行**，偏移 100 之后返回空数组 | `topN` 默认与上限都改成 100 |
| 全品牌用 `brands/0` | 返回 `-420 此类目下无此品牌`，正确值是 `brands/all` | 全链路改正 |
| 金额单位未知 | `price=35000`、`sale=4900×100`，两处都指向**分** | 默认按分转元，保留 `price_raw`/`sale_raw`，可用 `--price-unit yuan` 关闭 |
| 一个类目一次请求就够 | 只能看到某一列排序的前 100，换 `order_by` 才能看到另一批 | 默认取 `sale` + `sold` 两片，按 `item_id` 合并 |
| 商品字段是前端那 12 列 | 实际还多出 `shop_name/item_id/title/cat_path(数组)/price_raw` 等，前端列名对不上 | 按真实字段重写映射 |
| 类目路径形如「美容护肤/面部护理/面膜」 | 淘系树在 `全部 / 淘小铺 / 旅行购物` 三个入口下重复，真实路径是 `洗护清洁剂/…/面部清洁/护理/面膜` | 去合成根 `全部`；后缀命中多个取最短分支（主站） |
| 京东树与淘系字段一致 | 京东用 `category_name`，淘系用 `name` | 解析两种都认 |
| 目标月份取配置平台的「最小可用月份」 | `pdd` 止于 2020-05，会把整体拉回 2020 | 取「最新可用月份」，停更平台跳过 |
| 请求可以 1.2 秒一个 | 连续 4 个请求就 `-429 访问频率过快` | 默认 4–6 秒，触发后等 60 秒起再重试 |

另外两个只有实测才会发现的坑：

- `/api/user` 未登录也返回 `status: ok`，靠 `usertype == "logged_out"` 判断游客态；否则会把失效会话当成有效。
- 登录后如果账号要求二次验证，取数接口返回 `-499 smsverify`，必须在浏览器里完成短信/邮箱验证，Cookie 换成 requests 也绕不过。

关于覆盖率的实测（这是本设计最大的实际限制）：

| 试探 | 结果 |
| --- | --- |
| 换 `order_by` 切片（`sale` / `sold`） | **同一批 100 个商品**，只是顺序不同（jaccard 1.00） |
| 换 `order_by` 到 `sold_yoy` / `yoy` / `surge` / `price` | **HTTP 422**，白名单只认少数列 |
| 换平台：`all` vs `tmall` vs `cshop` | 三套不同前 100：`all`∪`tmall` = 182，重叠仅 14 |

结论：单类目单平台能看到的就是 100 个，靠排序扩不出来；靠平台可以做到 ~182。
因此配置里引入 `platforms[].group`，把淘系各平台归到同一市场，去重按 `(group, item_id)`。

剩余待实测见 `references/api-notes.md` 末尾（`/api/standard` 版本差异、上架时间是否可得、100 上限是否套餐相关）。

---

**许可状态**：内部使用，暂不附带 LICENSE（`status: draft`）。发布流程要求随包许可证，因此导出用
`--draft`；对外分发前需先定许可与版权主体（职务作品归属公司时还需公司同意），再补 LICENSE 并跑
`lint --release`。

## 1. 平台可用性（已实测，决定「都要」能要多少）

`plat` 参数有效值共 20 个（`all, cshop, tmall, chaoshi, nochaoshi, tmqjd, tmzyzmd, tmallhk, notmallhk, jd, jd_only_self, jd_exclude_self, jd_hk, sn, jm, dd, amazon, global, gome, wykl, pdd`），用 `/api/latesttime?plat=` 逐个探测数据区间：

| 你要的 | market1 实际 | 数据截止 | 可用性 |
| --- | --- | --- | --- |
| 淘宝 + 天猫 | `all` / `cshop` / `tmall` | 2026-10 | ✅ 主力 |
| 京东 | `jd` / `jd_only_self` / `jd_exclude_self` / `jd_hk` | 2026-10 | ✅ |
| 苏宁 / 国美 / 唯品系 | `sn` / `gome` / `wykl` | sn 2025-01 | ⚠️ 部分停更 |
| 拼多多 | `pdd` | **2020-05** | ❌ 数据停更，做不了新品 |
| 抖音 | **无此 platform id**（返回 `error_code:3 Unkown platform id`） | — | ❌ 不在该产品线 |

结论：Skill 支持「淘系 + 京东」为主要平台，苏宁等按数据区间可用即抓；**拼多多和抖音必须显式拒绝**，而不是抓到空表还报成功。配置里写了不支持的平台，启动时直接失败并给出上表理由。

`scripts/platforms.py probe` 输出这张可用性表（plat / 中文名 / `start`~`end` / 是否有类目树），每次跑之前先看它，避免拿 2020 年的拼多多数据做「本周新品」。

---

## 2. 其它已核实事实

| 结论 | 证据 |
| --- | --- |
| 页面是 AngularJS 壳，数据全走同源 `/api/...` | `dashboard` 39KB 静态壳，`ng-app="mojing"` |
| Cookie 鉴权，未登录是 **HTTP 200 + body `error_code:-401`** | `hot_items` 匿名请求实测 |
| 商品榜 `…/{plat}/cats/{cid}/brands/{bid}/hot_items`，服务端分页 | `itemlist.js` |
| 同 URL 加 `fmt=csv` 是平台导出（异步任务 + `export_time` 记录） | `downloadUrl = url + '?…&fmt=csv'`，`/api/task` |
| 商品维度字段仅 12 个：`id, itempic, item, price, min_price, ishop, cat_path, sale, sold, yoy, sold_yoy, brand` | `ItemList` 字段表 |
| **没有上架时间字段** | 同上 |
| 淘宝类目树离线可得，58,753 节点带 `level/parent_id` | `staticjs…/bigcats_taobao.js`（14MB） |
| 京东/苏宁/国美/唯品会类目树另有文件 | `chance.mktindex.com/…/bigcats_{jd,sn,gome,wykl}.js` |
| **数据是月粒度**，`latesttime` 只返回 `YYYY-MM` | `/api/latesttime` 全平台探测 |

---

## 3. 关键设计决策

**D1｜走 JSON 接口，不爬 DOM。** SPA + DataTables 只能拿到当前页 10~50 行；接口可分页、可断点、可校验结构。DOM 只在 M1 阶段做一次字段对账。

**D2｜一次登录，运行期无头。** `login.py` 开一次有头浏览器让用户登录 → 存 `storageState`（0600）→ 之后全 headless 复用。过期只提示重登，不自动重登。

**D3｜新品 = 首次出现（first_seen），7 天窗口靠快照节奏实现。** 见第 4 节，这是本设计最需要说清楚的一点。

**D4｜原始快照不可变，派生表重算。** 口径、窗口、类目合并都可重算，不必重抓。

**D5｜请求预算是显式闸门。** 平台数 × 类目数 × 快照数 直接决定请求量，启动先 `--dry-run` 报预算，超阈值要显式 `--yes` 才真跑。

---

## 4. 「近 7 天滚动」的真实含义（重要）

平台数据是**月粒度**，没有 7 天窗口的销量。能诚实交付的是：

- **数据字段**：`sold` / `sale` 是**当月累计**，不是近 7 天。一个 11 月 15 日上架的新品，它的 11 月销量天然只有半个月，跟成熟品不可比。
- **7 天滚动**：滚动的是**发现节奏**，不是数据窗口。每次运行抓一份 `snapshot_date = 今天` 的当月榜单，与本地历史比，`first_seen_date` 落在最近 7 天的商品就是「近 7 天新品」。
- **节奏可选**：`--cadence daily`（每天一份快照，7 天窗口精确）或 `weekly`（每周一份，请求量 ÷7，窗口退化为「两次运行之间新增」）。默认 `daily` + 只跑配置里的类目。
- **冷启动**：第一次运行没有历史，判不出「新增」。所以首跑先补 3 个月度种子（M-3..M-1）建立 `first_seen_month`，日粒度从当天开始积累。**前 7 天输出标 `window_partial=true`**，第 8 天起口径完整——这一点必须写进报告页脚，否则第一次看到的结果会被误读成「本周只有 3 个新品」。
- **精度升级（TBD）**：若账号可见商品级「上架时间」（商品详情接口），可把它作为首选口径，快照 diff 降级为交叉校验；字段名与可得性在 M1 实测后定。

销量字段一律按「月累计 + 上架未满月」标注，不做年化、不做日均折算。

---

## 5. 类目数量分档（对应「不同处理逻辑」）

矩阵是 `平台 × 类目 × 快照`。分档按**单次运行的有效类目数**（平台去重后），阈值可在配置里覆盖：

| 档 | 类目数 | 策略 | 失败语义 |
| --- | --- | --- | --- |
| S | 1–10 | 串行全量抓取，`topN=500`，一次跑完 | 任一失败即整体失败，不产出半份报告 |
| M | 11–50 | 串行 + 断点续跑（`state.json` 记每个 `(plat,cid,snapshot)` 状态），按上次失败优先重试 | 单类目失败跳过并计入 `skipped`，报告里留空位并说明 |
| L | 51–300 | 两阶段：① 类目级探针（`summary`，1 请求/类目）判断是否值得深挖；② 只对候选类目抓明细；并发 2 + 全局令牌桶 | 探针失败即该类目降级为「待人工确认」，不阻塞其余 |
| XL | >300（近全树） | 只做变化检测：探针全扫 → 按「新品潜力」排序 → 取 Top-K（默认 50）抓明细；其余只留类目级指标 | 必须显式 `--max-categories`，不接受「全树明细」 |

配套的预算闸门：`估算请求数 = 平台数 × 类目数 × ceil(topN / page_size)`（探针另计 1/类目/次），默认上限 3000，超限只报预算不执行。`run.py --dry-run` 输出「类目数 / 档位 / 预计请求 / 预计耗时 / 预计落盘大小」。

---

## 6. 目录结构

```
skills/raincoat-mj-products/
├── SKILL.md                     # Agent 入口：输入、命令、工作流、失败处置
├── README.md                    # 人读：安装、登录、跑一次、输出说明
├── config.example.json
├── requirements.txt             # playwright, requests, pandas, openpyxl
├── scripts/
│   ├── login.py                 # 一次性有头登录 → state/auth.json (0600)
│   ├── check_session.py         # 会话有效性 + 一次真实接口探测
│   ├── platforms.py             # probe：平台可用性 / 数据区间 / 类目树
│   ├── categories.py            # 类目树同步；路径 → cid（分平台）
│   ├── plan.py                  # 分档、请求预算、dry-run 报告
│   ├── fetch_items.py           # 单 (plat,cid,snapshot) 抓取 → snapshots/*.jsonl
│   ├── diff_new.py              # first_seen 索引 → 近 7 天新品表
│   ├── build_report.py          # CSV + xlsx + markdown 摘要
│   └── run.py                   # 编排 + 断点续跑 + state.json
├── references/
│   ├── api-notes.md             # 端点、参数、字段、错误码、分页实测值
│   └── runbook.md               # 401/403/-500/结构变更/限流的处置
├── examples/
│   └── config.taobao-jd.json
└── tests/
    ├── test_categories.py       # 路径解析、重名、跨平台 cid 不串
    ├── test_plan.py             # 分档阈值、预算公式、超限拒绝
    └── test_diff_new.py         # 合成快照：7 天窗口、冷启动、重复 ID
```

---

## 7. 流程

```
run.py --config config.json [--date 2026-11-19] [--dry-run]
  │
  ├─ 0 platforms   校验配置里的 plat 都在可用表内；不可用直接失败
  ├─ 1 check_session  失效 → 提示跑 login.py，不自动重试
  ├─ 2 categories   每平台各自的 路径→cid；跨平台类目不做自动映射
  ├─ 3 plan         类目数 → 档位 → 请求预算 → dry-run 报告
  ├─ 4 fetch        逐 (plat,cid) 抓当月快照 → snapshots/{plat}/{cid}/{date}.jsonl
  │                 冷启动时先补 3 个月度种子
  ├─ 5 diff_new     first_seen 索引 → near7d_new_{date}.csv
  └─ 6 report       类目/平台维度汇总 + TOP 新品 → report_{date}.md / .xlsx
```

子命令都能单跑，便于排查：

```bash
python scripts/platforms.py probe
python scripts/categories.py sync --plat jd
python scripts/categories.py resolve --plat tmall --path "面部清洁/护理/面膜"
python scripts/fetch_items.py --plat tmall --cid 50452018 --date 2026-11-19 --max-items 300
python scripts/diff_new.py --date 2026-11-19 --window 7
python scripts/run.py --config config.json --dry-run
```

---

## 8. 配置示例

```json
{
  "platforms": [
    {"plat": "all",  "label": "淘宝+天猫"},
    {"plat": "jd",   "label": "京东", "jdcat_path": "个护化妆/面部护肤/面膜"}
  ],
  "auth_state": "~/.config/raincoat/mktindex/auth.json",
  "data_dir": "./data",
  "categories": [
    {"path": "面部清洁/护理/面膜", "alias": "面膜"},
    {"cid": "201252224", "alias": "纸尿裤"},
    {"path": "宠物/宠物食品/猫主粮", "alias": "猫主粮", "include_children": true}
  ],
  "window": {"days": 7, "cadence": "daily"},
  "new_product": {"baseline_months": 3, "min_sold": 1},
  "fetch": {"max_items_per_category": 300, "page_size": 100, "min_interval_ms": 1500, "max_retries": 3},
  "budget": {"max_requests": 3000, "max_categories": 300}
}
```

- 类目按平台各自解析：淘系用 `path`，京东用 `jdcat_path`（两套 cid 体系，不自动换算）。
- 只写 `path` 时，若某平台解析不到该类目，该平台记为 `unmapped` 并跳过，不阻塞其他平台。
- `include_children=true` 按子类目分别抓再合并（父类目不直接挂商品时用）。

---

## 9. 数据契约

**快照行（原样保留接口字段 + 定位信息）**

```json
{"snapshot_date":"2026-11-19","plat":"all","cid":"50452018","cat_path":"洗护清洁剂/卫生巾/纸/香薰/面部清洁/护理/面膜",
 "item_id":"...","title":"...","brand":"...","shop":"...","price":129.0,"min_price":99.0,
 "sale":123456.0,"sold":980.0,"yoy":0.42,"sold_yoy":0.31,"rank":7}
```

**`near7d_new_{date}.csv`**

| 列 | 含义 |
| --- | --- |
| `plat` / `cat_alias` / `cat_path` / `cid` | 平台与命中类目 |
| `item_id` / `title` / `brand` / `shop` | 基础信息 |
| `price` / `min_price` | 页面价 / 最低折扣价 |
| `sold` / `sale` | 当月累计销量 / 销售额（非 7 天值） |
| `rank` | 当月该类目榜名次 |
| `first_seen_date` | 首次出现快照日（窗口判据） |
| `first_seen_month` | 首次出现月份（冷启动种子口径） |
| `window_partial` | 冷启动未满 7 天时为 true |
| `sold_yoy` / `yoy` | 平台原值，缺失留空不补 0 |

**报告维度**：按平台/类目的新品数、新品销售额占该类目总销售额比例、TOP20 新品、价格带分布、品牌集中度（TOP5 占比）、首月即进前 50 的「上新即爆」名单。

---

## 10. 新品判定与局限

1. **榜单截断**：只看得到当月前 N 名。真实新品首月没进榜，会延后到进榜那次快照才被记为 `first_seen`。报告保留该列，让使用者自己看滞后。
2. **换链接**：同一商品换 ID 会被判成新品。默认做全局 `item_id` 去重；「标题+店铺+价格」指纹去重可选，命中只在报告里提示疑似重复，不自动合并。
3. **类目迁移**：商品从 A 类目挪到 B，会在 B 里表现为新品。全局 `item_id` 去重可消掉。
4. **跨平台同款**：淘系与京东的同一商品是两个 ID、两套类目，不做合并，报告中分平台呈现。
5. **销量不可横比**：新品当月销量含「未满月」因素，报告里按上架时间（若可得）或首次出现日做分组提示，不直接与成熟品排名。

---

## 11. 失败与风控

| 现象 | 判定 | 处置 |
| --- | --- | --- |
| body `error_code:-401` | 会话失效 | 停止，提示重跑 `login.py`，不自动重登 |
| `error_code:3` Unkown platform id | 平台不支持 | 启动期即拦截，不进入抓取 |
| `-403` | 套餐无权看该类目 | 跳过，记 `skipped` |
| `-404` | 类目/商品未收录 | 跳过，记 `no_data` |
| `-500` / 超时 | 平台抖动 | 指数退避 3 次；仍失败则该 `(plat,cid)` 置 `failed`，继续下一个，下次运行优先重试 |
| `result` 结构或字段名变化 | 平台改版 | 直接失败，打印「期望字段 vs 实际字段」，不静默产出空表 |

- 限速：默认串行、间隔 ≥1.5s 带抖动；L 档才开并发 2，且共用全局令牌桶。
- `fmt=csv` **不作默认路径**：导出是异步任务、计入账号导出配额，只有 `--use-export` 时才用。
- 凭据：`auth.json` 0600、放 `~/.config/raincoat/`；`.gitignore` 覆盖 `data/`、`*.jsonl`、`auth.json`；日志对 Cookie 打码。
- 数据用途：内部经营分析，不对外分发原始明细。

---

## 12. 实施与验收

| 阶段 | 内容 | 验收 |
| --- | --- | --- |
| M1 | `platforms.py` + `login.py` + `fetch_items.py`（单平台单类目） | 真实账号抓到 tmall 面膜 2026-10 ≥100 条，字段与页面表格逐列一致；`platforms.py probe` 输出与本文第 1 节一致 |
| M2 | `categories.py` + `plan.py` + 多平台编排 + 断点续跑 | 3 类目 × 2 平台一次跑通；重名类目解析正确；中断重跑不重复抓；四档阈值各有测试 |
| M3 | `diff_new.py` + `build_report.py` | 合成快照验证 7 天窗口/冷启动/重复 ID；真实数据产出新品表与摘要；改 `window.days` 可复算 |

`TBD`（M1 实测后回填）：分页参数名与单页上限、`result` 实际结构（是否含 `total`）、`brands/0` 与 `bid=all` 差异、`/api/standard/...` 与 `/api/...` 的数据版本差异、商品级上架时间是否可得、京东类目树与淘系的对齐方式。

---

## 13. 仍未定的小项

1. `topN` 默认 300 是否够（新品多集中在头部，但小众类目长尾可能更早出现新品）？
2. 冷启动的 3 个月度种子是否可以接受（首跑请求量约 +3×）？
3. 报告要 Markdown 还是直接 xlsx 多 sheet？
