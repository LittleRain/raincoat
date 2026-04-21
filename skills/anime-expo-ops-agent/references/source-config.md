# 信息源配置

## v0.1 测试渠道

第一版 `daily_intel` 只抓取两个指定账号/入口，先验证从社交信号到活动候选的链路，不做全渠道铺开。

## 微博测试源

入口：

```text
https://weibo.com/6596632265/QuYfxs1po
```

解析：

- 平台：微博
- `source_type`: `weibo`
- `uid`: `6596632265`
- 示例微博路径标识：`QuYfxs1po`
- 采集范围：优先采集该 uid 的账号动态；示例微博作为 seed 和解析验证样本。

Hermes 采集要求：

- 首次 dry-run：拉取该 uid 最近 20 条微博。
- 后续增量：按发布时间或微博 id 游标采集新增内容。
- 每条微博归一化为 `source_item`。
- 保留原始链接、正文、图片、发布时间、互动数和 raw 响应。
- 不把微博 cookie 或登录态写入 repo；如需登录态，放 Hermes secrets。
- 如果工具返回内容不属于 `uid = 6596632265`，必须丢弃并写入 `errors`。
- 如果无法获取微博原文 URL，可以暂用 seed URL 作为 run 级来源，但对应候选必须进入人工审核。

建议 Hermes 调用能力：

```text
weibo.get_feeds(uid: "6596632265", limit: 20)
```

如果需要读取 seed 微博详情，Hermes 可根据微博工具能力把 `QuYfxs1po` 转为 mid 或直接保存为 source URL。

## 小红书测试源

入口：

```text
http://xiaohongshu.com/user/profile/6333b2ee0000000023024449
```

解析：

- 平台：小红书
- `source_type`: `xiaohongshu`
- `user_id`: `6333b2ee0000000023024449`
- 采集范围：该用户 profile 下的公开笔记。

Hermes 采集要求：

- 首次 dry-run：拉取该用户最近 20 条笔记。
- 后续增量：按发布时间、笔记 id 或 xsec_token 游标采集新增内容。
- 每条笔记归一化为 `source_item`。
- 保留原始链接、标题、正文、图片、发布时间、互动数、标签和 raw 响应。
- 小红书通常需要登录态；cookie 必须放 Hermes secrets，不得写入 repo 或 artifact。
- 如果 Hermes 暂时没有按 `user_id` 拉取 profile 笔记的能力，必须返回 `unsupported_connector`，不要改用关键词搜索或推荐流。
- 如果工具返回内容不属于 `user_id = 6333b2ee0000000023024449`，必须丢弃并写入 `errors`。

## source_item 归一化要求

微博和小红书都必须输出统一结构：

```json
{
  "id": "source_platform_native_id",
  "source_type": "weibo|xiaohongshu",
  "source_url": "https://...",
  "source_account": "账号名称或 uid",
  "raw_text": "正文",
  "raw_media": [],
  "published_at": "2026-04-20T10:00:00+08:00",
  "collected_at": "2026-04-20T10:05:00+08:00",
  "content_hash": "normalized_hash",
  "language": "zh",
  "confidence": 1.0,
  "engagement": {},
  "raw": {}
}
```

## 采集门禁

- 原始内容为空，不进入活动抽取。
- 采集失败必须写入 `errors` artifact。
- 登录态失效必须返回 `auth_required`，不要吞错。
- 同一内容 `content_hash` 重复时跳过抽取，但保留重复计数。
- 只有 dry-run 和 artifact 保存通过后，才进入 `event_candidate` 抽取。
- 平台搜索结果、推荐流结果、登录页、错误页、非目标账号内容不进入活动抽取。
- evidence URL 必须来自 `source_item.source_url` 或 `source_item.raw_media`，不能由模型生成。
