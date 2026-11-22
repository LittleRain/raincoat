---
name: raincoat-mj-products
description: Use when 需要魔镜洞察（market1.mktindex.com）的类目新品数据：魔镜新品、mktindex 新品、类目新品榜单、近7天新品、新品监控、竞品上新、淘宝/天猫/京东新品。触发场景：(1) 用户给出魔镜类目或链接并要新品明细 (2) 要求定期滚动跟踪某些类目的上新 (3) 需要某类目新品的销量/价格/品牌。产出 CSV + Markdown/xlsx。不适用：类目大盘/全量商品、日粒度销量、抖音数据（该产品线没有）。
metadata:
  version: "0.1.0"
  status: draft
---

# 魔镜新品抓取

按「平台 × 类目」抓取魔镜商品榜快照，用「首次出现」判定新品，产出 CSV 明细 + Markdown/xlsx 摘要。

## 先看三件事

1. **平台可用性有限**：`pdd` 数据止于 2020-05，抖音没有对应的 platform id。配置前先跑 `python scripts/platforms.py probe`，不要假设「都要」可得。
2. **数据是月粒度**：`sold`/`sale` 是当月累计，不是近 7 天。这里的「近 7 天」指**发现节奏**（窗口内首次出现在快照里），不是销量窗口。
3. **每个类目每月只有前 100 名**：服务端硬上限（`page=11&page_size=10` 返回空）。换 `order_by` **不会**换池子（`sale` 与 `sold` 是同一批商品，其他列直接 422）；要扩覆盖得换**平台**——`all` ∪ `tmall` 实测 182 个/类目，比单平台多 82%。多个淘系 plat 必须在配置里写同一个 `group`，否则同一商品会被算两次。
4. **冷启动需要窗口**：日快照连续采集满 `window.days` 天后口径才完整；之前输出带 `window_partial=true`，报告页脚也有提示。

## 首次使用（onboarding）

新机器上第一次用，先跑一次引导；它把平台、类目、窗口问清楚，写到**包外**的工作目录：

```bash
python scripts/onboard.py          # 交互式：选平台 → 搜类目 → 定窗口
python scripts/onboard.py --yes    # 不交互，用示例值（脚本/CI 用）
```

引导会做四件事：探测平台数据区间、让你挑平台、按关键字搜类目（也可以直接输 cid）、写
`~/.config/raincoat/mj-products/config.json`（可用 `RAINCOAT_MJ_HOME` 或 `--workspace` 改位置）。
登录态不在这一步处理——跑完它只会提示你走 `login.py` 还是 `import_state.py`。

工作目录结构：

```
~/.config/raincoat/mj-products/
├── config.json     # 平台、类目、窗口
├── data/           # 快照与种子（snapshots/ seeds/ out/）
└── output/         # 生成的 md / xlsx
```

**Skill 目录里不放任何用户数据**：导出包不含配置、登录态、类目选择或抓取结果。

## 输入

- 一份配置文件（模板见 [examples/config.example.json](examples/config.example.json)）：平台、类目、窗口、抓取上限
- 已保存的登录态（`python scripts/login.py` 一次，之后无头复用）
- 可选：`--date`（快照日）、`--month`（数据月份）、`--window`、`--max-items`

## 运行

```bash
pip install -r requirements.txt
python scripts/doctor.py                # 环境自检：依赖/浏览器/网络/登录态
python scripts/login.py                 # 仅首次或登录态失效时
python scripts/import_state.py --in /tmp/mmi-cookies.json   # 已有浏览器登录态时，从 CDP 导出转换
python scripts/platforms.py probe       # 看平台数据区间
python scripts/categories.py sync --plat all
python scripts/run.py --config config.json --dry-run   # 先看档位与请求预算
python scripts/run.py --config config.json
```

单步排查（都可单独跑）：

```bash
python scripts/categories.py resolve --plat all --path "面部清洁/护理/面膜"
python scripts/fetch_items.py --plat all --cid 50452018 --date 2026-11-19 --max-items 300
python scripts/diff_new.py --data-dir ./data --date 2026-11-19 --window 7
python scripts/build_report.py --csv ./data/out/near7d_new_2026-11-19.csv --date 2026-11-19
```

## 工作流

1. `platforms.py probe` 确认目标平台有该月数据（缓存 24 小时）。
2. `run.py` 解析类目 → 分档 → 预算校验 → `--dry-run` 通过后再实跑。
3. 抓取阶段按 `(平台, 类目, 快照日)` 落 `data/snapshots/<plat>/<cid>/<date>.jsonl`；已有文件默认跳过（断点续跑）。
4. 冷启动时补 `baseline_months` 个月度种子到 `data/seeds/`，只用于判断「这个品以前就有」。
5. `diff_new.py` 用日快照算 `first_seen_date`，产出 `data/out/near{N}d_new_<date>.csv`，跨类目按 `(plat, item_id)` 去重。
6. `build_report.py` 产出 `output/new_products_report_<date>.md` 与 `.xlsx`。

## 按类目数量分档

| 档 | 平台×类目 | 行为 |
| --- | --- | --- |
| S | 1–10 | 串行抓取，任一失败即整体失败 |
| M | 11–50 | 串行 + 断点续跑，单类目失败跳过 |
| L | 51–300 | 先探针（1 请求/类目）再抓明细，并发 2 |
| XL | >300 | 只抓前 `fetch.max_categories` 个类目，必须显式指定 |

分档由 `scripts/plan.py` 计算，`--dry-run` 会打印档位、请求数、耗时与落盘估算；超过 `budget.max_requests`（默认 3000）直接拒绝执行。

## 输出

- `data/out/near{N}d_new_<date>.csv`：新品明细（基础信息、价格单位**元**、当月销量/销售额、名次、`first_seen_date`、`window_partial`、`also_in`）
- `output/new_products_report_<date>.md`：类目概览、TOP20、价格带分布
- `output/new_products_<date>.xlsx`：类目概览 + 新品明细两个 sheet
- `data/state.json`：最近 50 次运行的档位、失败数、产物路径

## 失败处置

| 现象 | 处置 |
| --- | --- |
| `-401` / `AuthRequired` | 停下，重跑 `login.py`；不会自动重登 |
| `error_code 3` 未知平台 | 启动期拦截，不进入抓取 |
| `-403` 无权限 / `-404` 未收录 | 该类目记 `skipped`，不影响其他类目 |
| `-500` / 超时 | 自动退避重试 3 次，仍失败则该 (平台,类目) 置 failed，下次优先重试 |
| 返回结构变化（`SchemaChanged`） | 直接失败并打印「找不到商品列表/标题字段」，不产出空表 |

细节见 [references/api-notes.md](references/api-notes.md) 与 [references/runbook.md](references/runbook.md)。

## 什么时候不该用

- 要**类目大盘或全量商品**：接口每类目每月只给前 100 名，这里给不出全量。
- 要**日粒度销量**：魔镜电商数据是月累计，7 天只是发现节奏。
- 要**抖音数据**：该产品线没有抖音 platform id，拼多多也只到 2020-05。
- 只想要一次性的类目概览（不带新品判定）：直接用魔镜页面更快。

## 边界

- 不抓页面 DOM，只调 `/api/...` 的 JSON 接口；页面仅用于人工核对字段。
- 不使用 `fmt=csv` 导出（计入账号导出配额、异步任务），除非显式传入。
- 不做跨平台类目映射：淘系与京东是两套 cid，配置里分别写 `path` 和 `paths.jd`。
- 登录态落在 `~/.config/raincoat/mktindex/auth.json`（0600），不写进仓库。
