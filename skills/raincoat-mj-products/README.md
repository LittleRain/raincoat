# raincoat-mj-products

从魔镜洞察（market1.mktindex.com）按平台与类目抓商品榜，输出「近 N 天首次出现」的新品明细与摘要。

## 它解决什么

魔镜的商品榜没有「上架时间」，销量又是月粒度。直接问「最近一周有哪些新品」拿不到答案，只能靠**每天存一份快照、看哪些商品是新出现的**。这个 Skill 把这套采集、比对、出表固定下来。

## 安装

```bash
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Python **3.10+**（脚本用了 `X | None` 这类注解，3.9 会在 import 阶段直接 SyntaxError）。
首次安装 Playwright 需要下载 Chromium（约 130MB）。

Windows 用 PowerShell 执行同样的命令即可，不依赖 Bash / WSL。以下 POSIX 写法按需替换：

| POSIX | PowerShell |
| --- | --- |
| `cp examples/config.example.json config.json` | `Copy-Item examples/config.example.json config.json` |
| `~/.config/raincoat/mktindex/auth.json` | `%USERPROFILE%\.config\raincoat\mktindex\auth.json` |
| `python scripts/xxx.py` | `python scripts\xxx.py` |

装完先自检，缺什么它会直接告诉你装哪个：

```bash
python scripts/doctor.py
```

然后跑一次引导，把平台和类目定下来（只需一次）：

```bash
python scripts/onboard.py
```

它会探测各平台的数据区间、让你选平台、按关键字搜类目，最后把配置写到
`~/.config/raincoat/mj-products/config.json`。之后所有命令默认读这份配置，不用再传 `--config`。

## 包里有什么 / 没有什么

这个目录只有代码、文档和示例；**没有任何账号、Cookie、类目选择或抓取数据**。
用户的配置、登录态、快照和报告全部在包外：

```
~/.config/raincoat/mktindex/auth.json     # 登录态（0600）
~/.config/raincoat/mj-products/config.json # 你的平台与类目
~/.config/raincoat/mj-products/data/       # 快照与种子
~/.config/raincoat/mj-products/output/     # 报告
```

把整个 Skill 目录打包发给别人是安全的；对方跑一次 `onboard.py` 就是全新的一套。

**使用范围**：内部使用，暂未附带许可证。对外分发前先确定许可与版权主体，否则不要直接分享；
把包交给别人也不等于授权对方使用魔镜的账号或数据。

## 登录

```bash
python scripts/login.py
```

会打开一次有界面的浏览器，你自己完成登录（含短信验证），登录态存到 `~/.config/raincoat/mktindex/auth.json`（Windows 上是 `%USERPROFILE%\.config\raincoat\mktindex\auth.json`），之后所有抓取都是无头的。登录态过期时脚本会提示重跑，不会自动重登。

如果已经有开了调试端口的 Chrome：

```bash
python scripts/login.py --cdp http://localhost:9222
```

## 从 ego 浏览器导入登录态（推荐）

如果账号要求短信/邮箱二次验证，`login.py` 弹出的干净浏览器会卡在验证码。
这时在已经登录好的 ego lite 里导出一次 Cookie 更省事：

```bash
# 1) 在 ego lite 里登录魔镜（含短信验证），然后导出 Cookie
ego-browser nodejs <<'JS'
const fs = await import("node:fs/promises");
const page = (await taskSpace("default")).page("p1");
const dump = await page.cdp("Network.getAllCookies");
await fs.writeFile("/tmp/mmi-cookies.json", JSON.stringify(dump), "utf8");
JS

# 2) 转成登录态文件
python scripts/import_state.py --in /tmp/mmi-cookies.json

# 3) 验证
python scripts/check_session.py --plat all --cid 50452018
```

`import_state.py` 只保留 `*.mktindex.com` 的 Cookie，写到 `~/.config/raincoat/mktindex/auth.json`（0600）。
`--in -` 可以从 stdin 读，`--json` 只打印统计不写文件。

## 跑起来

```bash
python scripts/onboard.py                     # 一次性：选平台与类目
python scripts/run.py --dry-run               # 看档位与请求预算
python scripts/run.py
```

`--dry-run` 会打印档位、请求数、耗时和落盘估算。超过预算（默认 3000 请求）时只报数、不执行。

## 配置

```json
{
  "platforms": [
    {"plat": "all", "group": "taobao"},
    {"plat": "tmall", "group": "taobao"},
    {"plat": "jd", "group": "jd"}
  ],
  "categories": [{"path": "面部清洁/护理/面膜", "alias": "面膜"}],
  "window": {"days": 7, "cadence": "daily"},
  "new_product": {"baseline_months": 3},
  "fetch": {"max_items_per_category": 300, "page_size": 100, "min_interval_ms": 1500}
}
```

- `group` 表示「同一套商品 id 的市场」，淘系的 `all`/`tmall`/`cshop` 必须同组，去重时按 `(group, item_id)` 而不是按平台。
- `path` 写全路径（类目树 5.8 万节点，重名很多，`面膜` 在多个层级都有）。
- 京东等平台类目 id 不同，用 `paths: {"jd": "个护化妆/面部护肤/面膜"}` 单独指定；解析不到的平台记 `unmapped` 并跳过。
- 只有 `cid` 没有 `path` 也可以，此时 `cat_path` 留空。

## 输出

| 文件 | 内容 |
| --- | --- |
| `data/out/near7d_new_<date>.csv` | 新品明细：商品、品牌、店铺、价格、当月销量/销售额、名次、`first_seen_date` |
| `output/new_products_report_<date>.md` | 类目概览、TOP20 新品、价格带分布 |
| `output/new_products_<date>.xlsx` | 上面两块 + 完整明细 sheet |
| `data/snapshots/...` | 原始快照，可重算 |

## 口径与限制

- **销量是当月累计**，不是近 7 天。一个 15 号上架的新品，它的月销量天然只有半个月。
- **「近 7 天」是发现节奏**：窗口内首次出现在快照里。日快照不足 7 天时输出 `window_partial=true`，报告页脚有提示。
- **榜单截断**：每个类目每月只能拿到**前 100 名**（接口硬上限），真实新品可能延后被发现；`first_seen_date` 如实反映这个滞后。
- **扩覆盖只能靠加平台**：`all` 与 `tmall` 是两套不同的前 100（重叠仅 14），合起来 182 个；配置里给它们相同的 `group`，去重后不会重复计数。
- **价格单位**：接口返回的是**分**，Skill 已除以 100 输出元；`sale`/`sold` 同理。
- **限流**：连续请求会触发 `-429`，默认间隔 4–6 秒，触发后等 60 秒起再重试。
- **平台范围**：淘系（`all`/`cshop`/`tmall`）、京东（`jd` 系列）数据到 2026-10；苏宁止于 2025-01；拼多多止于 2020-05；抖音不在该产品线。以 `platforms.py probe` 的实际输出为准。
- **频率**：默认串行、请求间隔 4–6 秒。不要压低间隔或提高并发去抢数，账号被限流的代价远大于多等几分钟。

## 验证

在 skill 目录下执行（`tests/` 相对 `scripts/` 解析）：

```bash
python -m unittest discover -s tests
```

测试覆盖分档边界、预算拒绝、7 天窗口与冷启动、跨类目去重、类目重名解析，全部基于合成数据，不需要账号。
