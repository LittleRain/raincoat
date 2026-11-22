# 模型档案

记录日期：2026-11-18（第5阶段更新）。模型名来自本机选择器、CLI 请求或桥接 state；不将同名标签等同于固定供应商快照。本阶段只使用本地证据，不据名称臆测模型能力。

| 模型标签 | 环境与可识别信号 | 当前证据及边界 | 待验证表达规则 |
| --- | --- | --- | --- |
| DeepSeek V4.1 Flash (`deepseek-v4.1-flash`) | Bitto；OCR 精确匹配已知标签，评测显式请求，local-agent state 回显 | 第5阶段新增12份成功回答，型号标签精确匹配；4份旧基线复用，形成8对。未固定供应商快照；不代表脱离 harness 的表现 | numeric候选 E/Cdoubleprime 0-8-0，基线满分天花板，缺少两胜，disabled；D独立收益未覆盖 |
| Kimi K2.5 (`kimi-k2.5`) | WorkBuddy CLI；显式请求及 state 标签，桌面可手选 | 第5阶段新增28份成功回答，型号标签精确匹配；4份旧基线复用，形成16对。不能从单次行为推出模型普遍习惯 | plan候选4-2-2、format候选2-5-1，均有质量败，disabled；格式仅general手选范围，D独立收益未覆盖 |
| GPT-6.1 Sol (`gpt-6.1-sol`) | 历史 `codex exec --model ...`；客户端已有对应已知标签 | 早期初始化失败保留；解除限制后少量A/C真实回答成功，但型号未确证。第5阶段未调用，不是ChatGPT界面实测 | E/D未覆盖，无可启用规则 |
| 其他已知 UI 标签 | GPT-6 Astra/Terra/Luna、DeepSeek V4、Claude、Gemini 等见 `ModelLabel.known` | 识别列表服务于选择，不是能力目录。本阶段无对应运行组合 | 无发布规则，回退基础场景模板 |

## 发布与证据

统一数据源为 [prompt-rules.json](../Sources/PromptCore/Resources/prompt-rules.json)。每条适配记录 id、kind、target、scene、version、evidence、enabled、instruction；模型规则另含精确 model。当前所有 Agent/模型候选 `enabled=false`，没有把旧轮混合模板的胜出当成独立模型规则证据。

默认评测 E 在同一题目、环境、模型、repeat 下，给 D 仅增加一条候选模型规则。第5阶段显式选择冻结Cdoubleprime基底、关闭Agent层，以逐字单条增量验证E/Cdoubleprime。没有命中型号或候选时在调用前拒绝；无操作对照不得作为启用证据。更换请求型号时，须新增对应候选或只跑 A–D。

`validate_rules.py` 检查本地 runs + 匿名评分映射，至少有两个不同配对胜出、两个 repeat 和保留题、可见型号精确匹配请求和规则标签、E无关键错误且无质量败才允许启用；这只是最小工程门禁，不能替代人工复核。本轮全部成功配对一起试启用，三条均未通过，不能挑选胜例。运行时还要求 enabled 且 evidence 非空、target/scene/model 全部匹配。版本变化需重跑，不按家族名泛化。

来源：[首轮原始结果](../.build/evaluation/round-01/results.json)、[扩展 runs](../.build/evaluation/round-02/runs.jsonl)、[Codex 探针](../.build/evaluation/smoke-stage1/runs.jsonl)、[模型标签实现](../Sources/PromptCore/PromptCore.swift)。所有日期指本次本机观察日；旧产品设计中的外部提示指南属于候选背景，未在本阶段核实，不能充当启用证据。

新增本地来源：[第5阶段逐条门禁与逐题报告](../.build/evaluation/stage5-report.md)、[实际运行汇总](../.build/evaluation/stage5-summary.json)、[解除限制后的GPT探针](../.build/evaluation/smoke-gpt-unblocked/runs.jsonl)。第5阶段评审为单人、非盲、同模型初评。

## 第7阶段盲评更正

旧stage5候选的E/Cdoubleprime，按胜-平-负：plan为Bitto2-1-5、WorkBuddy3-2-3，旧切点总体负收益，人工4-2-2高估；format两评委均2-5-1，顺序一致5/8；numeric为1-6-1与1-7-0，不足每评委两胜。源文件完整行快照与归一方向已核对，不照抄不同范围/顺序的消息摘要。当前stage6收窄版是不同版本、尚未完整验收，不能借用旧版结果。三类规则（format含开发/报告两个作用域）全部disabled。

正式0.2.0仅发布场景文案，不是上述模型规则发布。双评委的总体比较与额外一个空闲评委的全量关键错误核验分开记录；旧导入不确证评委实际型号，只有新调用保留完整后端状态。人工初评不再单独决定发布，详见[evaluation-protocol.md](evaluation-protocol.md)。
