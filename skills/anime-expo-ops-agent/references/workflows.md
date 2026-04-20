# 工作流

## 字典同步（`dictionary_sync`）

目标：初始化并每周更新活动发布所需字典。

步骤：

1. 加载本地省市区字典 `assets/city-dictionary.xlsx`。
2. 循环调用场馆 API，拉取全量有效场馆并写入 Hermes 本地缓存。
3. 对每个有效场馆调用场地 API，拉取该场馆下的场地并关联 `venue_id`。
4. 记录每次同步的新增、更新、失效数量。
5. 定期重复同步；发现新增场馆或场地时更新本地缓存。

场馆 API：

```text
GET https://show-mng.bilibili.co/api/ticket/mis/Venue/get?key=&page=1&pagesize=20
```

规则：

- `key` 是关键词；初始化时用空 key 分页拉取全量。
- Hermes 必须分页直到没有更多数据。
- 只存储返回结果中 `status_text = 有效` 的 `id` 和 `name`，同时保留 raw 便于排查。
- 每次同步应保留上一次缓存，用于判断新增、更新、失效。

场地 API：

```text
GET https://show.bilibili.com/api/ticket-b/place/getbyvenue?venue_id=30204
```

规则：

- `venue_id` 是必填参数，来自场馆 API 的有效场馆 id。
- 返回结果中的 `id` 和 `name` 用于 `placeId` 和场地名称。
- 场地必须和对应 `venue_id` 绑定保存。

建议调度：

- 初始化：Hermes 启动或首次部署时执行一次全量同步。
- 定期更新：每周一 03:00 执行一次全量或准全量同步。
- 手动刷新：当运营人员发现场馆/场地缺失时，可触发单次同步。

## 每日行业情报（`daily_intel`）

目标：发现行业信号并产出活动候选。

步骤：

1. Hermes 读取 `references/source-config.md` 中的 v0.1 测试渠道。
2. 抓取微博 `uid = 6596632265` 的最近动态。
3. 抓取小红书用户 `6333b2ee0000000023024449` 的最近笔记。
4. 将微博和小红书内容统一归一化为 `source_item`。
5. 对 `content_hash` 去重。
6. 采集失败、登录态失效、限流都必须进入 `errors` artifact。
7. 使用活动抽取提示词抽取 `event_candidate`。
8. 用省市区字典解析 `provinceId`、`cityId`、`districtId`。
9. 用场馆/场地缓存解析 `venueId`、`placeId`。
10. 输出 `create_draft`、`merge_review`、`needs_review` 队列。

v0.1 不做全网搜索，只抓指定账号。

## 已有活动查重（`duplicate_match`）

目标：使用已有活动查询接口判断候选活动是否已存在。

步骤：

1. 读取 `event_candidate`。
2. 优先使用候选活动 `name` 调用项目搜索接口。
3. 如果候选活动有明确开始时间，用 `start_min` 和 `start_max` 限定时间窗口。
4. 从接口响应的 `data.item` 读取已有活动列表。
5. 使用 `data.page.total`、`data.page.num`、`data.page.size` 分页，直到拉完或当前页为空。
6. 将接口返回活动与候选活动按名称、城市、时间、场馆做匹配。
7. 输出 `platform_event_match`。
8. 疑似重复或字段冲突进入人工审核。

规则：

- 不要只凭名称相似就判定重复；必须结合城市或时间。
- 已有活动 `start_time`、`end_time` 是 Unix 秒级时间戳，匹配前需转换为本地时间或日期窗口。
- 已有活动 `city` 是城市 id，可直接和候选解析出的 `cityId` 对比。
- 已有活动 `venue_name` 只做文本匹配，不能当作 `venueId`。
- 同名不同城市、同名不同日期，默认进入 `possible` 或人工审核。
- 查询接口需要登录态，cookie 只能存在 Hermes secrets 中。

## 活动草稿（`draft_events`）

目标：在平台创建活动草稿，但不发布。

步骤：

1. 读取已审批或高置信度候选活动。
2. 执行活动类型、省市区、场馆、场地字典解析。
3. 生成 `platform_event_draft_payload`。
4. 如果 `type`、`provinceId`、`cityId` 无法解析，不得调用发布接口。
5. 如果 `venueId` 或 `placeId` 无法确认，可设置 `venueUndecided = 1`，但必须进入人工审核。
6. 如果时间无法确认，设置 `projectTimeStatus = 1`。
7. 如果价格无法确认，设置 `priceStatus = 1`。
8. 如果活动草稿创建接口未上线，只保存 payload artifact，不调用写入。
9. 接口上线且 `can_create_unpublished_drafts` 打开后，调用 Hermes 平台适配器创建或更新未发布草稿。
10. 回填平台活动 ID，并生成发布审批任务。

v0.1 阶段永远不要自动发布。

## 业务数据同步（`business_sync`）

目标：把运营指标规范化为快照。

建议调度：每天本地时间 10:00。

## 动作建议（`recommend_actions`）

目标：把行业情报和业务指标转换成运营决策。每条建议必须包含证据、预期影响、风险和下一步动作。

## 周复盘（`weekly_review`）

目标：闭环复盘，并改进后续决策。
