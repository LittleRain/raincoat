# 数据模型

所有对象都应序列化为 JSON。Hermes 可以把这些对象持久化到数据库、文件或内部 run store，但字段名和含义应保持稳定。

## source_item

从社交渠道、网页、社群、API 或人工备注采集到的原始信号。

必填字段：

- `id`：稳定的内部 id
- `source_type`：`xiaohongshu`、`weibo`、`bilibili`、`wechat`、`douyin`、`website`、`manual`、`api` 或 `other`
- `source_url`：原始链接，无法获取时可为空
- `source_account`：账号或作者名称
- `raw_text`：抽取出的文本
- `raw_media`：图片或视频引用数组
- `published_at`：原始发布时间，无法获取时可为空
- `collected_at`：采集时间
- `content_hash`：归一化后的去重 hash
- `language`：内容语言
- `confidence`：0-1 的采集置信度

来源完整性要求：

- `source_url` 必须来自采集工具返回的原始链接或 `source-config.md` 中明确配置的 seed/profile 链接。
- 不得由模型编造、拼接或把搜索页、登录页、跳转页当成原文链接。
- 微博 `source_item` 必须能追溯到配置的 `uid = 6596632265`。
- 小红书 `source_item` 必须能追溯到配置的 `user_id = 6333b2ee0000000023024449`。
- 如果采集器无法拿到稳定原文链接，`source_url` 可以为空，但该 source item 只能进入人工排查，不能进入自动活动抽取。
- 如果原始内容来自登录页、错误页、空页面或非目标账号，必须写入 `errors`，不得进入 `event_candidates`。

## event_candidate

从一个或多个 source items 中抽取出的结构化活动候选。

必填字段：

- `id`
- `source_item_ids`
- `name`
- `event_type_name`
- `province`
- `city`
- `district`
- `venue`
- `place`
- `start_date`
- `end_date`
- `organizer`
- `ticket_price_min`
- `ticket_price_max`
- `price_status`
- `poster_portrait_url`
- `poster_landscape_url`
- `description_html`
- `ip_tags`
- `category_tags`
- `guest_tags`
- `evidence`
- `confidence`
- `status`：`new`、`duplicate`、`needs_review`、`approved`、`rejected` 或 `published`

证据要求：

- `evidence` 中每条证据必须包含 `source_item_id`、`field`、`quote`、`url`。
- `url` 必须等于对应 `source_item.source_url`，或是该 source item 原始媒体里的 URL；不得是模型生成的新 URL。
- `quote` 必须能在对应 `source_item.raw_text` 中找到，或明确标记为 `media_ocr` 并关联 `raw_media`。
- 非空字段没有 evidence 时，该字段必须清空或整条候选进入 `needs_review`。
- 如果活动名称、城市、开始时间三者都缺少直接证据，不得生成 `event_candidate`。
- 如果候选活动与 `source_item.raw_text` 的主题明显无关，必须标记为 `rejected`，不要进入字典解析。

证据对象建议结构：

```json
{
  "source_item_id": "weibo_6596632265_xxx",
  "field": "start_date",
  "quote": "5月1日-5月2日",
  "url": "https://weibo.com/6596632265/xxx",
  "evidence_type": "text|media_ocr|metadata"
}
```

## platform_event_draft_payload

Hermes 调用活动发布接口前生成的草稿负载。这个对象必须由 `event_candidate` 加字典解析结果转换而来。

| 业务字段 | 接口字段 | 来源 | 处理规则 |
| --- | --- | --- | --- |
| 活动名称 | `name` | 抽取/人工确认 | 必填 |
| 活动类型 | `type` | 字典转换 | 必填，先从活动类型名称转换成 id |
| 场馆 | `venueId` | 场馆缓存转换 | 场馆明确时必填 |
| 场地 | `placeId` | 场地缓存转换 | 场地明确时必填，依赖 `venueId` |
| 场馆待定标记 | `venueUndecided` | 规则生成 | 场馆或场地无法确认时为 1，否则为 0 |
| 省份 | `provinceId` | 省市区字典转换 | 必填 |
| 城市 | `cityId` | 省市区字典转换 | 必填 |
| 区县 | `districtId` | 省市区字典转换 | 区县明确时转换成 id，无法确认时进入人工审核 |
| 开始时间 | `startTime` | 抽取/人工确认 | 格式 `YYYY-MM-DD HH:mm:ss` |
| 结束时间 | `endTime` | 抽取/人工确认 | 格式 `YYYY-MM-DD HH:mm:ss` |
| 项目时间状态 | `projectTimeStatus` | 规则生成 | 时间确认时为 0，时间待定时为 1 |
| 海报竖图 | `performanceImage.first.url` | 来源图片/人工补充 | 没有时可为空，但进入缺素材提示 |
| 海报横图 | `performanceImage.banner.url` | 来源图片/人工补充 | 没有时可为空，但进入缺素材提示 |
| 活动详情 | `performanceDesc` | 抽取/模板生成 | JSON 字符串，内容放在 `activity_content` 模块 |
| 最低票价 | `minPrice` | 抽取/人工确认 | 单位为分；价格待定时可为空 |
| 最高票价 | `maxPrice` | 抽取/人工确认 | 单位为分；价格待定时可为空 |
| 价格状态 | `priceStatus` | 规则生成 | 价格确认时为 0，价格待定时为 1 |

草稿负载示例：

```json
{
  "name": "2026周杰伦嘉年华世界巡回演唱会-上海站",
  "type": 1,
  "venueId": 19652,
  "placeId": 20386,
  "venueUndecided": 0,
  "provinceId": 310000,
  "cityId": 310100,
  "districtId": 310101,
  "startTime": "2026-04-01 19:30:00",
  "endTime": "2026-06-15 22:00:00",
  "projectTimeStatus": 0,
  "performanceImage": {
    "first": {
      "url": "//uat-i2.hdslb.com/bfs/openplatform/202604/XK0az0zf1776066804_1776066804533.jpg",
      "desc": "竖版海报首图"
    },
    "banner": {
      "url": "//uat-i2.hdslb.com/bfs/openplatform/202604/DWEBG2mD1775628618_1775628618310.jpg",
      "desc": "横版海报首图"
    }
  },
  "performanceDesc": "{\"type\":1,\"list\":[{\"module\":\"activity_content\",\"details\":\"<p>活动详情待补充</p>\"}]}",
  "minPrice": 48000,
  "maxPrice": 188000,
  "priceStatus": 0
}
```

## 活动类型字典

| id | 名称 |
| --- | --- |
| 1 | 主题漫展 |
| 2 | 演唱会 |
| 3 | 电子游戏展 |
| 4 | 音乐会 |
| 5 | 动漫嘉年华 |
| 6 | 其他演出 |
| 7 | 舞台剧 |
| 8 | 其他展览 |
| 9 | 场贩 |
| 10 | 漫展 |
| 11 | 本地生活 |
| 20 | 电影 |
| 21 | 话剧 |
| 22 | 音乐剧 |
| 23 | 音乐节 |
| 24 | livehouse |
| 25 | Only同人展 |
| 26 | IP展览 |
| 27 | 主题餐厅 |
| 28 | 见面会 |
| 29 | 快闪 |
| 30 | 生咖 |
| 31 | 观影会 |
| 32 | 同好会 |
| 33 | 一日店长 |
| 34 | 其他活动 |
| 35 | 电竞赛事 |
| 36 | 观赛活动 |
| 37 | 体育赛事 |
| 38 | 其他赛事 |

归类规则：

- 综合性二次元展会优先 `10` 漫展。
- 单一主题或 IP 的漫展优先 `1` 主题漫展。
- Only、同人专场、CP 向同人展优先 `25` Only同人展。
- 官方 IP 展、动画/游戏 IP 展览优先 `26` IP展览。
- 动漫嘉年华、二次元嘉年华优先 `5` 动漫嘉年华。
- 信息不足但与漫展行业相关时，不要默认归为 `34` 其他活动；先进入人工审核。

## 省市区字典

文件路径：

```text
skills/anime-expo-ops-agent/assets/city-dictionary.xlsx
```

字段结构：`id`、`name`、`fullname`、`pinyin`、`parent_id`、`type`、`first_letter`。

规则：

- `type = 省份` 的 `id` 对应 `provinceId`。
- `type = 城市` 的 `id` 对应 `cityId`，`parent_id` 必须等于省份 id。
- `type = 区县` 的 `id` 对应 `districtId`，`parent_id` 必须等于城市 id。
- 直辖市保留省份和城市两级，例如北京省份 `110000`、城市 `110100`。
- 只提到城市时，不要默认选择中心城区。

## 场馆与场地字典

场馆和场地不放静态文件，必须由 Hermes 通过 API 初始化并每周更新本地缓存。

场馆缓存对象：

- `venue_id`
- `venue_name`
- `status_text`
- `raw`
- `synced_at`

场地缓存对象：

- `place_id`
- `place_name`
- `venue_id`
- `venue_name`
- `raw`
- `synced_at`

解析规则：

- 只使用 `status_text = 有效` 的场馆。
- 场地查询必须先有 `venue_id`，不能为空。
- `placeId` 必须来自对应 `venueId` 下的场地列表。
- 场馆或场地名称模糊匹配多个候选时，必须进入人工审核。
- 不得跨场馆选择场地。

## platform_event_match

候选活动与平台已有活动记录的匹配结果。已有活动来自项目搜索接口。

必填字段：

- `candidate_id`
- `platform_event_id`
- `match_type`：`exact`、`likely`、`possible` 或 `none`
- `match_score`
- `matched_fields`
- `conflicting_fields`
- `recommended_action`：`skip`、`merge_review`、`update_draft` 或 `create_draft`
- `raw`

匹配原则：

- 名称、城市、时间都高度一致：`exact`。
- 名称相似，城市一致，时间接近：`likely`。
- 名称相似但城市或时间不完整：`possible`。
- 关键字段冲突时不得自动合并。

## project_search_result

项目搜索接口返回的已有活动记录。当前只定义 Hermes 去重需要的标准化字段；raw 响应必须保留。

响应路径：

- 活动列表：`data.item`
- 当前页：`data.page.num`
- 每页数量：`data.page.size`
- 总数：`data.page.total`

标准化字段：

- `id`
- `name`
- `type`
- `project_type`
- `province`
- `city`
- `city_name`
- `venue_name`
- `start_time`
- `end_time`
- `pub_time`
- `sale_end_time`
- `sale_flag`
- `merchant_name`
- `is_exclusive`
- `status`
- `hide`
- `pending`
- `jump_url`
- `performance_image`
- `today_count`
- `total_count`
- `remain`
- `raw`

字段规则：

- `start_time`、`end_time`、`pub_time`、`sale_end_time` 是 Unix 秒级时间戳。
- `city` 和 `province` 是地区 id；`city_name` 是展示名。
- `venue_name` 是已有活动场馆名，用于与候选活动场馆做文本匹配。
- `performance_image.first.url` 是竖图，`performance_image.banner.url` 是横图。
- `status`、`hide`、`pending` 用于判断活动当前状态，v0.1 查重时保留但不自动更改状态。
- `raw` 必须保留完整 item，便于后续字段补充和排查。
