# 漫展运营 Agent 计划进度

## 2026-04-20

- 在 `codex/anime-expo-ops-agent` 分支按历史记录重建 `skills/anime-expo-ops-agent`。
- 已复制省市区字典到 `skills/anime-expo-ops-agent/assets/city-dictionary.xlsx`。
- 已恢复活动发布字段、活动类型字典、省市区规则、场馆/场地 API 每周同步机制。
- 已重建 `task_plan.md`、`findings.md`、`progress.md`。
- 已根据最初目标补齐产品策略、系统设计和完整实施计划文件。
- 已按 harness 思路审查并补齐：run artifact、gate engine、replay、golden set、capability flag、上线门禁。
- 用户确认活动草稿创建接口尚未上线，已调整计划为不阻塞阶段 0-2。
- 用户提供已有活动查询接口、场馆返回结构和场地返回结构，已写入 Hermes 交接、工作流和数据模型；cookie 不写入 repo。
- 用户提供已有活动查询接口完整响应结构。已明确活动列表取 `data.item`，分页取 `data.page.num/size/total`，并补齐标准化字段和时间戳规则。
- 用户提供 v0.1 测试抓取渠道：微博 `https://weibo.com/6596632265/QuYfxs1po`，小红书 `http://xiaohongshu.com/user/profile/6333b2ee0000000023024449`。已写入 `source-config.md`、工作流和实施计划。
- 用户确认没有历史样本，将通过后续人工反馈打磨规则。已调整 eval 和实施计划：v0.1 不阻塞 golden set，先用 live dry-run 积累反馈样本。
