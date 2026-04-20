# 漫展运营 Agent 关键发现

- Repo 中的 `anime-expo-ops-agent` 是业务契约；Hermes 是执行引擎。
- 场馆和场地不是静态字典，需要 Hermes 通过 API 初始化并持续更新本地缓存。
- 场地解析依赖场馆 id，不能单独解析。
- 场馆只使用 `status_text = 有效` 的记录。
- `dictionary_sync` 应先于 `daily_intel` 和 `draft_events` 执行。
- 字典同步每周一次即可，保留手动刷新。
- 最初目标应落地为“运营副驾驶”，不是一开始做全自动运营员工。
- Agent 的价值衡量应看活动草稿时效、建议采纳率和业务结果，而不是信息采集量。
- 按 harness 设计，模型只负责提出候选；系统负责 schema、gate、工具调用、审批和回放。
- 自动写入前必须先有 artifact store、replay、eval、capability flag。
- 活动草稿创建接口未上线，不应阻塞阶段 0-2；先推进字典同步、查重、payload dry-run。
- 用户提供了已有活动查询接口和场馆/场地返回结构，cookie 属于运行时密钥，不能写入 repo。
- v0.1 测试采集源已确定：一个微博指定账号入口和一个小红书 profile 入口。
- 用户没有历史样本，v0.1 应通过 live dry-run + 人工反馈来积累 eval/golden set，不阻塞启动。
