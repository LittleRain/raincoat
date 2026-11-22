# 排障手册

## 登录态失效

现象：`AuthRequired`、`-401`、或 body 里出现 `您尚未登录`。

```bash
python scripts/login.py
python scripts/check_session.py --plat all --cid 50452018
```

`check_session.py` 会真的打一次 `hot_items`，能提前暴露「cookie 在但套餐没权限」的情况。
不要试图重放或伪造 cookie；账号被风控的代价远大于重新登录。

## 平台没有数据

现象：`数据止于 2025-01，2026-11 还没出`。

跑 `python scripts/platforms.py probe --refresh` 看实际区间。常见原因：

- 该平台已停更（`pdd` 止于 2020-05，`sn` 止于 2025-01）
- 当月数据尚未产出（魔镜是 T+1 月更，月初跑上月是正常的）
- `plat` 写错（`taobao` 不是合法 id，淘系用 `all`/`cshop`/`tmall`）

## 类目解析失败

`类目名不唯一` —— 类目树有 5.8 万节点，`面膜` 这类名字在多个层级重复。按报错里列出的候选写全路径：

```bash
python scripts/categories.py search --keyword 面膜
python scripts/categories.py resolve --plat all --path "面部清洁/护理/面膜"
```

`平台 X 没有公开类目树` —— 该平台只能直接写 `cid`。

## 抓到的数据比预期少

检查 `data/snapshots/<plat>/<cid>/<date>.jsonl` 的行数与 `run.py` 输出里的 `total`：

- `truncated=true`：到了 `max_items_per_category` 上限，属预期
- 行数远小于 `total`：分页参数可能不符（见 `references/api-notes.md` 的 TBD），先跑单类目排查：
  `python scripts/fetch_items.py --plat all --cid 50452018 --max-items 50`

## 报告里新品数异常

- 首跑必然是 0 或很少：没有历史快照就判不出「新」，`window_partial=true`。
- 跑了几天但新品数偏高：品类本身在换季，或跨类目重复计入——默认已做 `(plat, item_id)` 去重，`also_in` 列会标出重复归属。
- 老品被判成新品：看 `first_seen_month`，如果它是种子月之前就存在的品，说明种子没补上，跑一次
  `python scripts/run.py --config config.json`（默认会补 3 个月种子）。

## 请求太多 / 太慢

`run.py --dry-run` 先看预算。降请求量的顺序：

1. 减平台（`all` 已含淘宝+天猫，别同时配 `cshop`/`tmall`）
2. 降 `fetch.max_items_per_category`（长尾对新品发现价值低）
3. 降 `new_product.baseline_months`（种子只在冷启动时补）
4. 把 `window.cadence` 从 `daily` 改 `weekly`（请求量 ÷7，窗口精度下降）

不要提高并发或压低 `min_interval_ms`。默认 1.5s 已经不快，账号被限流后要等更久。

## 返回结构变化

现象：`SchemaChanged: 返回结构里找不到商品列表` 或 `找不到标题字段`。

说明平台改版。脚本会拒绝产出空表——这是刻意的。按报错里打印的实际字段更新
`scripts/fetch_items.py` 的 `ALIASES`，并在 `references/api-notes.md` 记一笔。
