# 提示词合约

## 活动抽取提示词

```text
你负责从 source_item 中抽取漫展、二次元、同人展、cosplay、IP 活动相关线下活动信息。

只返回符合 event_candidate schema 的合法 JSON。

规则：
- 不要编造缺失字段。
- 未知字段填 null。
- 每个非 null 字段都必须包含 evidence。
- 活动类型输出名称，不要输出 id。
- 活动类型优先输出：主题漫展、漫展、Only同人展、IP展览、动漫嘉年华、电子游戏展、场贩、见面会、快闪、主题餐厅、生咖、观影会、同好会。
- 信息不足时，event_type_name 填 null，不要直接填“其他活动”。
- 省份、城市、区县、场馆、场地都输出原始名称，不要猜 id。
- 票价按元抽取，Hermes 转发布接口时再转换成分。
- 如果票价未公布，ticket_price_min 和 ticket_price_max 填 null，price_status 填 1。
```
