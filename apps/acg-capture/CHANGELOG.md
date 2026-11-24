# CHANGELOG

## 0.3.0

- 从 `workspace/plugins/acg-capture` + `workspace/workflows/kuji-tracking` 合并成独立应用：面板与引擎一起搬到 `apps/acg-capture`，引擎在 `engines/` 下自带 `references/`、`docs/`、`skills/`。
- 逐条结论表支持按结论筛选（全部 / 待确认 / 已采纳 / 判废 / 重复·表内已有 / 来源未公布），筛选按 tab 记住。
- 修 `bag_id` 撞车：slug 截断会让同 IP、名字前缀相同的候选共用同一个 id（实测一轮 86 条只有 82 个唯一 id），现补 6 位内容哈希，逐条裁决与前端渲染不再认错条目。
- 行 key 改为 `id-序号`，旧运行里已存在重复 id 时也不会复用错行。
