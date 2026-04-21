# Hermes 交接说明

Hermes 应把本技能作为版本化业务契约读取。

## 本地字典资产

- 省市区字典：`skills/anime-expo-ops-agent/assets/city-dictionary.xlsx`

## 外部 API

### 认证与敏感信息

接口调用所需 cookie、登录态、CSRF、token、浏览器 headers 都属于 Hermes runtime secrets，不得写入本仓库。

Hermes 可以保存：

- API URL
- 查询参数契约
- 返回结构示例
- 字段映射规则

Hermes 不应保存到本仓库：

- cookie 原文
- `_AJSESSIONID`
- `SecurityProxySessionID`
- 任何用户登录态 header

### 场馆 API

```text
GET https://show-mng.bilibili.co/api/ticket/mis/Venue/get?key=&page=1&pagesize=20
```

使用方式：

- 初始化时 `key` 为空，按 `page` 分页拉全量。
- 只取 `status_text = 有效` 的 `id` 和 `name`。
- Hermes 应保存 raw 响应、同步时间、页码和错误日志。

返回结构示例：

```json
{
  "errno": 0,
  "errtag": 0,
  "msg": "",
  "data": {
    "list": [
      {
        "id": 30227,
        "name": "濮阳银座京开店",
        "city": "濮阳市",
        "province": "河南省",
        "district": "华龙区",
        "address_detail": "京开大道中段363",
        "place_num": 1,
        "status": 1,
        "status_text": "有效"
      }
    ],
    "total": 1
  }
}
```

分页判断：

- `data.list` 是当前页场馆列表。
- `data.total` 是总数。
- Hermes 用 `page` 和 `pagesize` 翻页，直到已拉取数量 >= `data.total` 或当前页 `data.list` 为空。

### 场地 API

```text
GET https://show.bilibili.com/api/ticket-b/place/getbyvenue?venue_id=30204
```

使用方式：

- `venue_id` 必填，来自有效场馆。
- 返回结果里的 `id` 和 `name` 用于场地缓存。
- 场地必须与对应场馆绑定，不能跨场馆使用。

返回结构示例：

```json
{
  "errno": 0,
  "errtag": 0,
  "msg": "",
  "data": [
    {
      "id": 35550,
      "name": "濮阳银座京开店"
    }
  ]
}
```

### 已有活动查询 API

用于去重、合并审核和避免重复创建草稿。

```text
GET https://show-mng.bilibili.co/api/ticket/mis/project/search
```

已知查询参数：

| 参数 | 用途 |
| --- | --- |
| `name` | 项目名称 |
| `id` | 项目 ID |
| `start_min` | 开展时间下限 |
| `start_max` | 开展时间上限 |
| `page` | 页码 |
| `size` | 每页数量 |
| `status` | 状态过滤，当前示例为 `1` |
| `channel` | 渠道过滤，当前示例为 `1` |

接口还支持但暂未纳入 v0.1 去重核心的参数：`pub_min`、`pub_max`、`sale_min`、`sale_max`、`city`、`sale_flag`、`type`、`project_type`、`merchant_name`、`is_exclusive`、`channel_user_id`。

Hermes v0.1 查询策略：

- 优先用 `name` 搜索。
- 如果候选活动有明确开始时间，补充 `start_min`、`start_max` 缩小范围。
- 如果已知项目 ID，用 `id` 精确查询。
- 读取返回结构中的 `data.item` 作为活动列表。
- 读取 `data.page.num`、`data.page.size`、`data.page.total` 做分页。
- Hermes 用 `page` 和 `size` 翻页，直到已拉取数量 >= `data.page.total` 或当前页 `data.item` 为空。

返回结构示例：

```json
{
  "errno": 0,
  "errtag": 0,
  "msg": "",
  "data": {
    "item": [
      {
        "id": 1000220,
        "name": "宁波·文旅动漫嘉年华·泊港南京舰",
        "city": 330200,
        "province": 330000,
        "sponsor_type": "其他",
        "type": 10,
        "project_type": 1,
        "merchant_name": "浙江省宁波市幻焱动漫有限责任公司",
        "is_exclusive": "1",
        "start_time": 1777600800,
        "end_time": 1779271200,
        "pub_time": 1776677926,
        "sale_end_time": 1779271200,
        "sale_flag": "",
        "performance_image": {
          "banner": {
            "desc": "",
            "url": "//i0.hdslb.com/bfs/openplatform/202604/cJFarnDu1776517492_1776517492752.png"
          },
          "first": {
            "desc": "",
            "url": "//i2.hdslb.com/bfs/openplatform/202604/i1nuUugR1776517487_1776517487276.png"
          }
        },
        "venue_name": "131南京舰",
        "status": 1,
        "ver_id": "1231260863129",
        "hide": 0,
        "channel": 1,
        "channel_user_id": 303305152,
        "city_name": "宁波市",
        "today_count": 0,
        "total_count": 0,
        "remain": 92691,
        "jump_url": "https://show.bilibili.com/platform/detail.html?id=1000220",
        "real_auth": 0,
        "id_bind": 0,
        "pending": 0
      }
    ],
    "page": {
      "num": 1,
      "size": 20,
      "total": 63909
    },
    "ids": []
  }
}
```

敏感说明：

- 查询接口需要登录态 cookie 和浏览器 headers。
- cookie 必须由 Hermes secrets 管理，不得写入 skill、artifact 或日志。

### 活动草稿创建 API

当前接口尚未上线，因此不阻塞阶段 0、阶段 1、阶段 2。

在接口上线前：

- Hermes 只生成 `platform_event_draft_payload`。
- schema gate、dictionary gate、duplicate gate 仍然照常运行。
- `can_create_unpublished_drafts` 默认关闭。
- 阶段 3 等接口上线后再开启。

## 推荐运行时配置

- `dictionary_sync`：首次部署立即执行；之后每周一 03:00 更新。
- `daily_intel`：每天 08:00，v0.1 只抓 `source-config.md` 中的微博和小红书测试源。
- `business_sync`：每天 10:00。
- `recommend_actions`：每天业务同步完成后。
- `weekly_review`：每周一 09:00。

## Dry-run 运行语义

Hermes 必须把 `dry-run` 理解为“真实只读输入 + 禁止写入动作”。

dry-run 仍然要真实执行：

- 真实采集微博指定 uid。
- 真实采集小红书指定 user_id；如果能力不足，返回 `unsupported_connector`。
- 真实同步场馆/场地 API 或读取真实缓存。
- 真实调用已有活动查询接口做去重；如果鉴权失败，返回 `auth_required`。

dry-run 不得执行：

- 创建、更新、发布活动。
- 改价、投放、删除、降权。
- 使用 mock 数据冒充真实采集结果。

如果 Hermes 需要做演示数据，应显式使用 `run_mode = simulation`，并且输出不得进入 eval、golden set 或运营反馈闭环。

报告要求：

- 中文报告必须标明 `run_mode`。
- 如果出现 mock、模拟 API、fixture 或 demo 数据，报告必须标红并把 run 判为无效。
- `source_items`、`event_candidates`、`draft_payloads` 不得包含无法追溯到真实 source item 的内容。

## Hermes 必需能力

- 场馆 API 分页拉取和本地缓存。
- 场地 API 按场馆逐个拉取和本地缓存。
- 已有活动查询 API 适配器。
- 微博账号动态采集适配器。
- 小红书用户笔记采集适配器。
- `source_item` 归一化器。
- 来源完整性门禁：校验 source item 属于配置账号，且不是搜索结果、推荐流、登录页、错误页或空正文。
- 证据 URL 门禁：校验 evidence URL 来自 `source_item.source_url` 或 `raw_media`，quote 能在原文或 OCR 中定位。
- 字典解析器：活动类型、省市区、场馆、场地。
- schema 校验器。
- 运营视图同步器：把 artifacts 幂等同步到飞书多维表格，字段见 `operator-views.md`。
- 反馈读取器：读取飞书人工反馈，追加写入 `feedback_events` artifact。
- 活动草稿创建/更新适配器；接口上线前保持 disabled。
- 审批任务创建。
- 运行审计日志、重试和死信队列。

## 飞书表格交接

如果使用飞书多维表格作为运营视图，Hermes 需要运行时配置：

- 飞书 app token 或 table app URL。
- 每个表的 table id。
- 可写入这些表的飞书应用凭证或机器人能力。
- 字段名与 `operator-views.md` 保持一致，或提供字段映射。

安全规则：

- 飞书表格只保存摘要、状态和 artifact 链接。
- raw JSON、长正文、接口响应保存在 artifact store。
- 不得把 cookie、token、完整 header、登录态写入飞书。
- 飞书写入失败要进入 `errors`，但不能阻塞 artifact 保存。

## 不得自动执行

- 发布活动。
- 改价。
- 花推广预算。
- 删除或降权内容。
- 发送非模板化商务消息。
