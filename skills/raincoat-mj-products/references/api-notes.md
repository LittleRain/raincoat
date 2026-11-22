# 魔镜接口备忘（market1.mktindex.com）

实测时间 2026-11-19。只记录核实过的内容；标 **TBD** 的项需要登录账号实测后回填。

## 鉴权

- 同源 Cookie 会话。未登录时 **HTTP 200**，body 为
  `{"status":"error","error_code":-401,"error_msg":{"msg":"您尚未登录, ..."}}`
- 因此调用方必须看 body 的 `status`/`error_code`，不能只看 HTTP 状态码。
- **`/api/user` 是例外**：游客访问也返回 `{"status":"ok"}`，只是
  `result.usertype == "logged_out"`、`username`/`nick` 为 `null`。所以「能拿到 200」不能证明已登录，
  判定要用 `usertype`；`-401` 来自真正取数的接口（如 `hot_items`）。
- 登录态以 Playwright `storageState` 保存，运行时转成 requests 的 cookie jar。

## 通用错误码

| error_code | 含义 | 处理 |
| --- | --- | --- |
| `-401` | 未登录/失效 | 停止，重跑 `login.py` |
| `-403` | 套餐无权 | 跳过该类目 |
| `-404` | 未收录 | 跳过，记 `no_data` |
| `-499` | 需短信验证 | 人工完成验证 |
| `-420` | 类目下无此品牌（`brands/0` 的典型症状） | 改用 `brands/all` |
| `-429` | 访问频率过快 | 等待 60s 起、逐步加倍后重试 |
| `-500` | 平台错误 | 退避重试 |
| `3` | 未知 platform id | 启动期拦截 |

## 平台 id

`/api/latesttime?plat=<id>` 可匿名探测数据区间（`start`/`end`，格式 `YYYY-MM`）。

实测（2026-11-19）：

| plat | 名称 | 区间 |
| --- | --- | --- |
| `all` | 淘宝+天猫 | 2016-04 ~ 2026-10 |
| `cshop` | 淘宝 | 2016-04 ~ 2026-10 |
| `tmall` | 天猫 | 2016-04 ~ 2026-10 |
| `jd` / `jd_only_self` | 京东 | 2016-04 ~ 2026-10 |
| `sn` | 苏宁 | 2016-04 ~ 2025-01 |
| `pdd` | 拼多多 | 2016-04 ~ **2020-05** |
| `douyin` | — | 不存在（`error_code 3`） |

不带 `plat` 时返回全局区间 `2013-01 ~ 2026-10`。注意 `taobao` **不是**合法 id（会报 Unkown platform id），淘系要用 `all`/`cshop`/`tmall`。

## 商品榜（已实测）

```
GET /api/platform/{plat}/cats/{cid}/brands/all/hot_items
```

| 参数 | 值 | 说明 |
| --- | --- | --- |
| `start` / `end` | `YYYY-MM` | 单月就传同一个 |
| `page` | 1 起 | **不是** `iDisplayStart`，那个会被忽略 |
| `page_size` | ≤100 | 传 50/100 都按请求返回 |
| `order_by` | `sale` / `sold` / 列名 | 排序切片 |
| `desc` | `true` / `false` | |
| `lang` | `zh` | |

`page_size=1` 会被拒（HTTP 400），最小可用值是 5；取值探测用 10。

**重要：每个类目每月最多 100 行。** `page=11&page_size=10`（偏移 100）返回空数组，
`page=3&page_size=50` 同样为空。这是服务端上限，不是分页没写对。

**换排序不会换池子。** 实测 `order_by=sale` 与 `order_by=sold` 返回的是**同一批 100 个商品**，
只是顺序不同（jaccard = 1.00）；`sold_yoy` / `yoy` / `surge` / `price` 直接 **HTTP 422**，说明
`order_by` 有白名单。所以多切片并不能扩大覆盖，默认只留 `sale` + `sold` 是为了排序稳定性。

**换平台才会换池子。** 同一类目 2026-10：

| plat | 行数 | 与 `all` 重叠 | 独有 |
| --- | --- | --- | --- |
| `all`（淘宝+天猫） | 100 | — | — |
| `tmall`（仅天猫） | 96 | 14 | **82** |
| `cshop`（仅淘宝） | 100 | 86 | 14 |

`all` ∪ `tmall` = **182** 个商品，比单平台多 82%。三者是同一套商品 id，所以要用 `group`
把它们归到同一个市场做去重，否则同一商品会被算两次（见配置里的 `platforms[].group`）。

`brands/0` 是**错的**：会返回 `-420 此类目下无此品牌`。全品牌要用 `brands/all`。

返回结构：

```json
{"status": "ok", "result": {"count": 100, "data": [ {…row…} ]}}
```

`count` 恒为 100（前 100 名的上限），不是该类目的全部商品数。

### 行字段（实际返回，比前端的列配置多）

```
item_id, title, shop_name, brand, brand_name, price, min_price, price_raw,
sale, sales, sold, yoy, sold_yoy, cat_path, uid, shop_type, pic, comment,
pred_prob, loc, reserve_price, is_global, is_tmgj, back_cid
```

| 源字段 | 输出列 | 处理 |
| --- | --- | --- |
| `item_id` | `item_id` | 原样 |
| `title` | `title` | |
| `shop_name` | `shop` | |
| `brand_name` / `brand` | `brand` | 两者都可能为空 |
| `price` / `min_price` | `price` / `min_price` | **按分处理**（35000 → 350 元），原值留在 `price_raw` |
| `sale` / `sales` | `sale` | 同上，原值留在 `sale_raw` |
| `sold` | `sold` | 件数 |
| `yoy` / `sold_yoy` | 同名 | 可能是字符串 `"-"`，按缺失处理 |
| `cat_path` | `cat_path` | 是**数组**，取 `category_name` 用 `/` 拼接 |

金额单位是**推断**出来的，不是文档写的：`price=35000` 对应面膜单价，`sale` 恰好等于
`price × sold`（14 × 350 = 4900），两处都指向「分」。若你的账号返回的是元，
用 `--price-unit yuan` 或配置 `fetch.price_unit` 关掉换算——原始值始终保留，可复核。

**仍然没有上架时间**。这是「新品靠快照首次出现判定」的根因。

### 限流

`-429 您的访问频率过快，请喝口水，休息一下再来`。实测 1.2 秒间隔、连续 4 个请求就会触发。
默认间隔改成 4–6 秒；触发后 `Session` 会等待 `cooldown_s`（默认 60s，逐次递增）再重试。

## 导出

同一 URL 加 `&fmt=csv` 走平台导出，属于异步任务（`/api/task`，记录里有 `export_time`/`export_begin`），
通常计入账号导出配额。Skill 默认不用它。

## 类目树

静态 JS，`var cache_cat_<tree> = {"status":"ok","result":{"childrenList":{...}}}`：

| tree | 地址 |
| --- | --- |
| taobao | `https://staticjs.mktindex.com/prod/bigcats_taobao.js` |
| jd / sn / gome / wykl | `https://chance.mktindex.com/static/chance/json/bigcats_<tree>.js` |

淘宝树 58,753 个节点，字段 `category_id/name/parent_id/level/chd`。节点重名普遍，
解析必须用全路径。

## 待实测

1. `/api/standard/...` 与 `/api/...` 的数据版本差异。
2. 商品级上架时间是否可得（决定 `first_seen` 精度能否升级）。
3. 京东类目树与淘系路径的对齐方式（当前靠人工写 `paths.jd`）。
4. 100 行上限是套餐限制还是接口固定（换账号复测）。
