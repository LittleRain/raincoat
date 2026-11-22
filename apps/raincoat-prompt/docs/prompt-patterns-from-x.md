# X Prompt 经验档案

**外部经验，未在本地评测验证。** 以下25条是用户提供的抓取笔记原样归档；[全文]仅表示抓取者取得文字，不代表本项目复核了作者身份、日期、模型名称或效果数字。中文“为什么有效”和“可改写规则”属于外部解释/候选，不是产品默认行为。二手及仅摘要条目不能提升为一手来源；重复引用同一帖不算独立证据。

10条可执行候选保存在资源目录 prompt-rules.json 的 external_candidates，全部 enabled=false。observed_failure 只记录本地问题的对应关系，不证明该外部技巧能修复问题。Cprime 的本地对照另见候选文案与本地评测产物。

# X 上的 prompt 优化实战笔记（可直接进规则库）

抓取时间：2026-11-17 23:00（Asia/Shanghai）｜来源：X / Twitter，`twitter-cli` v0.8.5
抓取方式说明：`twitter search` 全线 404（X GraphQL 端点变更，重试 + 升级到最新版仍失败，OpenCLI 未安装），改用 **用户时间线 `user-posts` + 已知推文 ID `tweet` 读取全文** 两条稳定路径；候选线索用 web 搜索定位原帖 URL 后回读。凡未拿到原帖全文的条目均标注「仅摘要 / 二手」。

标记约定：`[全文]` = 已用 twitter-cli 抓到推文原文；`[仅摘要]` = 只见到引用片段；`[二手]` = 原帖未抓到，依据解读文章（附链接）。

---

## 通用手法

### 1. 让模型「先修确定的，再列不确定的」——一条提示词当项目审计 [全文]
- 来源：@alexalbert__（Anthropic），2026-11-09，10,085 赞
- URL：https://x.com/alexalbert__/status/2119884951550386671
- 原文：
  > "Read this entire project and find everything that's broken, inconsistent, inefficient, or no longer needed. Fix what you're sure about and list the rest for me to review."
- 中文：读整个项目，找出坏的、不一致的、低效的、已经没用的东西；**你确定的直接改，不确定的列成清单给我审**。
- 为什么有效：把「改」和「判断」拆开，模型不必为了交付而强行改它没把握的部分，人只审一小段清单；同时天然产出一份待办。
- 适用：开发 / 代码库维护 / 方案评审；适用模型：Claude Code、Codex 等有仓库读写权限的 agent。
- 可改写规则：**「确定项直接执行 + 不确定项列清单待审」是默认交付形态；禁止把不确定的改动混进 diff。**

### 2. 从「给任务」升级为「给目标 + 验收集」[全文]
- 来源：@alexalbert__，2026-06-09（Fable 使用四建议）
- URL：https://x.com/alexalbert__/status/2064467657483829441
- 原文：
  > "4. Move from providing tasks to providing objectives. Describe what done looks like and how to verify it, then let Fable find the path (/loop and /goal are built for this)"
- 中文：别给任务清单，给目标和「完成长什么样、怎么验证」，路径交给模型。
- 同帖另两条可直接用：`3. Rework your skills and CLAUDE.mds. Instructions written for prior models anchor Fable to stale patterns, let it use its own judgment first.`（旧模型时代写的规则会把新模型锚回旧习惯）；`2. Use xhigh/high effort as your default...`（推理档位也是提示的一部分）。
- 适用：通用 / 开发；适用：Claude 5 代模型 + Claude Code。
- 可改写规则：**每条需求必须带「完成定义 + 验证方法」两栏，缺一栏视为需求未写完。**

### 3. 用受控语言压掉模型的「丰富表达」[全文]
- 来源：@karpathy，2026-10-02，56,856 赞
- URL：https://x.com/karpathy/status/2105819303471976479
- 原文：
  > "Ask your LLM to explain something in ASD-STE100, it's a controlled language specification originally developed for aerospace maintenance documentation... Sometimes I've tried to soften it a bit e.g. ask for '80% of the way to ASD-STE100' because the spec is quite stringent."
- 中文：让模型按航空维修文档的受控英语（ASD-STE100）写，一句话一个动作、限长、同一概念只用一个词；嫌太硬就要「80% 的程度」。
- 为什么有效：模型的默认失败模式是**同义词轮换和长句**，恰好是受控语言明令禁止的；这是用「风格约束」而不是「更多要求」来提升可读性。
- 适用：写报告 / 写方案 / 解释文档；适用：通用（GPT、Claude、DeepSeek 均可）。
- 可改写规则：**面向人阅读的长输出，默认加一条「按 ASD-STE100 的 80% 写：一句一动作、≤20 词、同一概念不换词」。**

### 4. 把输出形态当提示的一部分：文字 → 图 → 网页 → 视频 [全文]
- 来源：@karpathy，2026-10-02（同帖）
- URL：https://x.com/karpathy/status/2105819303471976479
- 原文：
  > "Instead of writing, ask your LLM to create a diagram... Ask for output 'in HTML' to get a beautiful, interactive webpage... The output format I am most bullish on is fully custom / bespoke explainer videos."
- 中文：同一个内容，要求画图 / 输出 HTML 网页 / 生成讲解视频，比让它写长文更好读。
- 适用：调研汇报 / 教学 / 方案；适用：有前端与多模态能力的模型（Claude、GPT）。
- 可改写规则：**解释类需求先问「最终给人看的是文字还是可交互物」，默认允许模型改用图表/HTML 交付。**

### 5. 用「idea file」代替给代码/给成品 [全文]
- 来源：@karpathy，2026-04-04，26,778 赞
- URL：https://x.com/karpathy/status/2040470801506541998
- 原文：
  > "The idea of the idea file is that in this era of LLM agents, there is less of a point/need of sharing the specific code/app, you just share the idea, then the other person's agent customizes & builds it for your specific needs. ... It's intentionally kept a little bit abstract/vague because there are so many directions to take this in."
- 中文：分享「意图 + 关键约束」的抽象说明，让对方的 agent 按自己的环境重建；刻意留白反而扩大适用面。
- 适用：写方案 / 跨团队交接 / 复用工作流；适用：Claude Code、Codex 等能读仓库的 agent。
- 可改写规则：**模板类交付物写成「意图 + 约束 + 验收」的 idea 文件，不写死实现细节。**

### 6. 让模型「增量编译」知识库，而不是一次性总结 [全文]
- 来源：@karpathy，2026-04-02，61,105 赞
- URL：https://x.com/karpathy/status/2039805659525644595
- 原文：
  > "I index source documents... into a raw/ directory, then I use an LLM to incrementally 'compile' a wiki, which is just a collection of .md files... The wiki includes summaries of all the data in raw/, backlinks, and then it categorizes data into concepts, writes articles for them, and links them all."
- 中文：原文进 `raw/` 不动，模型增量产出 md  wiki（摘要 + 反链 + 概念文章），人只看编译产物；后续问答基于这个 wiki。
- 适用：调研 / 知识管理 / 长报告；适用：长上下文模型（Claude、Gemini 类）+ 本地文件 agent。
- 可改写规则：**长材料先落 `raw/`，再让模型按「摘要 / 反链 / 概念条目」三层增量编译，禁止直接对原文做一次性总结。**

### 7. 用一句话授权，压掉模型的过度谨慎 [全文]
- 来源：@simonw，2026-11-10，4,734 赞
- URL：https://x.com/simonw/status/2120029347948220500
- 原文：
  > "here's an entertaining tip to make Fable 5.2 less likely to be cautious in how it improves existing code: tell it 'This codebase is yours'"
- 中文：说「这个代码库是你的」，模型会更主动重构，而不是只做最小保守改动。
- 适用：开发 / 重构；适用：Claude 5 代（Anthropic 官方 prompting guide 里的技巧）。
- 可改写规则：**重构类任务加一句归属授权（「这是你的代码库，按你的判断改」），并在验收里要求列出改动理由。**

### 8. 用固定 schema 替代形容词堆砌 [全文]
- 来源：@IamEmily2050，2026-03-11
- URL：https://x.com/IamEmily2050/status/2031879748834771302
- 原文：
  > "Something wrong with your JSON prompt, try to double check, there are so many AI slop word's."（随后给出 `frame / subject / left_panel / right_panel / environment / lighting` 的紧凑 JSON 结构；每个字段只放可判定的值，如 `"Single 3200K tungsten spotlight"`、`"Camera-left, 45 degrees above subject"`）
- 中文：提示词质量不看字数，看**控制信号密度**；能落到枚举/数值/位置的就不要写形容词。
- 适用：图像/设计类提示、结构化抽取、任何要可复现的输出；适用：通用。
- 可改写规则：**结构化输出先定 schema 再填值；每个字段必须是可判定值，形容词一律替换为参数。**

### 9. 少写规则，多给判断（context engineering 的新规则）[二手]
- 来源：@trq212（Claude Code 团队 Thariq），2026-07-24；原帖未抓到（搜索故障），依据解读：https://explainx.ai/blog/claude-5-context-engineering-thariq-doctor-july-2026
- 要点：Anthropic 为 Opus 5 / Fable 5 **删掉了 Claude Code 系统提示词的 80%+，评测无下降**；结论是「judgement over rules」、渐进披露（progressive disclosure），旧写法属于「过度约束」。
- 同源中文解读（含具体删减清单）：https://www.uisdc.com/claude-code-10
- 适用：Claude 5 代 + Claude Code；**不要无差别迁移到旧模型**。
- 可改写规则：**规则库按「模型代际」分版本；新模型上线先做一次「删 50% 规则」的对照测试，再决定保留。**

### 10. 用用户故事当提示，而不是技术方案 [仅摘要/转译]
- 来源：@dotey（宝玉），2026-11-12，转译《软件工程师现在该怎么办》
- URL：https://x.com/dotey/status/2120961974519398535
- 原文（译文）：
  > "现在给模型写一段用户故事作为提示词，效果甚至比一份严谨的技术方案还要好。"
- 中文：描述「谁在什么场景下要完成什么」，比描述实现方案更能得到对人有用的结果。
- 注意：这是转译内容，非作者原创结论；仅作中文语境的旁证。
- 适用：写方案 / 产品需求；适用：通用。

---

## 模型/harness 差异

### 11. 旧模型时代的 CLAUDE.md 会把新模型锚回旧习惯 [全文]
- 来源：@alexalbert__，2026-06-09（同条目 2 的帖）
- URL：https://x.com/alexalbert__/status/2064467657483829441
- 原文：
  > "Rework your skills and CLAUDE.mds. Instructions written for prior models anchor Fable to stale patterns, let it use its own judgment first."
- 中文：每次换模型都要重写 skills / CLAUDE.md；给旧模型打的补丁会变成新模型的天花板。
- 适用：Claude Code / Codex / 任何带持久规则文件的 harness。
- 可改写规则：**规则文件带「适用模型版本」字段；换模型强制走一次规则复审。**

### 12. 每换代先读官方 prompting guide，官方自己也常被新模型吓到 [全文]
- 来源：@simonw，2026-11-10
- URL：https://x.com/simonw/status/2120029347948220500 ；同帖回复 https://x.com/simonw/status/2120029567616458900
- 原文：
  > "When Anthropic release a new model it's always worth taking a look at their updated prompting guide"
  > "it's VERY clear from reading them that Anthropic are just as surprised by the idiosyncrasies of their new models as we are"
- 中文：官方 guide 是「这一代的怪癖清单」，不是通用原理；换代必须重读。
- 适用：Claude / GPT 全系；适用：所有写规则库的人。
- 可改写规则：**规则库里每条 tip 标注「来源模型 + 日期」，超过一次大版本即降级为待复测。**

### 13. Claude Code 的典型失效模式：替你假设、不澄清、过度设计 [全文]
- 来源：@karpathy，2026-01-26，40,717 赞
- URL：https://x.com/karpathy/status/2015883857489522876
- 原文：
  > "The most common category is that the models make wrong assumptions on your behalf and just run along with them without checking. They also don't manage their confusion, they don't seek clarifications, they don't surface inconsistencies, they don't present tradeoffs, they don't push back when they should..."
  > "They will implement an inefficient, bloated, brittle construction over 1000 lines of code and it's up to you to be like 'umm couldn't you just do this instead?' and they will be like 'of course!' and immediately cut it down to 100 lines."
  > "Things get better in plan mode, but there is some need for a lightweight inline plan mode."
- 中文：错误不再是语法错，而是「悄悄替你做了错误假设」；先规划（plan mode）能显著缓解。
- 适用：Claude Code / Codex；可迁移到任何 agent。
- 可改写规则：**默认先出计划（含假设清单与权衡），人确认后再执行；禁止在未列假设的情况下直接改多文件。**

### 14. 多 agent 蜂群在当年（2026-02）是「一团乱」[全文]
- 来源：@karpathy，2026-02-27
- URL：https://x.com/karpathy/status/2027521323275325622
- 原文：
  > "here's 8 agents (4 claude, 4 codex), with 1 GPU each running nanochat experiments... The TLDR is that it doesn't work and it's a mess... but it's still very pretty to look at :)"
- 中文：多 agent 并行做研究当时不可用；单 agent + 明确验收仍是主线。
- 适用：agent 编排 / 自动化研究；适用：Claude Code + Codex 混合。
- 可改写规则：**不要用「多开 agent」当质量手段；先证明单 agent 在同一验收下不达标。**

### 15. 中文模型（DeepSeek/Kimi）对「隐含意图」的补全更弱 [二手]
- 来源：实践者博客，2026-05-06（非 X，X 端未抓到一手帖，记为缺口）
- URL：https://docs.bswen.com/blog/2026-05-06-chinese-ai-model-prompting-tips/
- 要点：从 GPT/Claude 迁到 DeepSeek/Kimi 后，原来「一句话让模型自己补布局、校验、错误处理」的写法会产出不完整实现；需要把约束、边界、示例显式写出。
- 中文：同一段提示在「强推断」模型上够用，在中文开源模型上要补显式规格；这不是模型变差，是提示假设变了。
- 适用：DeepSeek / Kimi / 国产模型；适用：跨模型复用的规则库。
- 可改写规则：**规则分「强推断模型版」与「显式规格版」；跨模型复用时自动降级到显式版。**

---

## 反模式

### 16. AI slop words：形容词越多，控制力越弱 [全文]
- 来源：@IamEmily2050，2026-03-11（同条目 8）
- URL：https://x.com/IamEmily2050/status/2031879748834771302
- 原文：`"there are so many AI slop word's"` —— 被批评的父帖把视觉约束、情绪叙事、氛围词、negative prompt 全塞进一段 JSON。
- 中文：堆砌「电影感、氛围感、极致细节」这类词，看似更具体，实则不可判定、不可复现。
- 可改写规则：**提示词里出现无法判定真假的形容词就报错；要求替换为参数、枚举或排除项。**

### 17. 过度验证指令会反噬 [二手]
- 来源：@trq212 / Anthropic 对 Opus 5 的官方提示建议，经二手整理
- URL：https://github.com/maxritter/pilot-shell/blob/f3c5bee78489125d28c5c174c226ff0d59d83e69/docs/docusaurus/blog/2026-07-29-claude-5-context-engineering.md
- 原文：
  > "if your prompt contains explicit verification instructions, remove them. Instructions like those 'cause over-verification on Claude Opus 5, and removing them reduces wasted tokens with no loss in quality.'"
- 中文：「改完请复查」「再读一遍文件确认」这类叠起来的谨慎话，会让新模型把预算花在重复确认上。
- 适用：Claude 5 代；**旧模型上未必成立**。
- 可改写规则：**验证只写一条可执行的验收命令；禁止追加「double-check / verify your work」类泛化叮嘱。**

### 18. 「Prompt engineering is dead」——过度提示的反面信号 [全文]
- 来源：@goodside，2026-10-23
- URL：https://x.com/goodside/status/2113639196254671259
- 原文：
  > "Prompt engineering is dead. Prompt however you want. Have fun."
- 中文：对强模型而言，精心设计的提示词边际收益在下降；把精力放在验收与上下文，而不是措辞。
- 适用：通用（作者语境为强模型 + 多模态生成）。
- 可改写规则：**规则库设「收益复核」：连续两代模型上无显著提升的措辞技巧，标记为可选而非必填。**

### 19. 上下文里塞什么，模型就用什么（RAG 污染）[全文]
- 来源：@karpathy，2026-03-25
- URL：https://x.com/karpathy/status/2036841069636370467
- 原文：
  > "(I cycle through all LLMs over time and all of them seem to do this... maybe during training, a lot of the information in the context window is relevant to the task, so the LLMs develop a bias to use what is given, then at test time overfit to anything that happens to RAG its way there via a memory feature)"
- 中文：模型有「用了再说」的偏置，检索进来的无关内容会被当成任务约束。
- 可改写规则：**检索结果必须带相关性阈值与来源标注；低置信片段宁可不进上下文。**

### 20. 规则堆到第 15 条就开始失效 [二手]
- 来源：agentpedia 对 Karpathy 风格 CLAUDE.md 模板的实测整理
- URL：https://agentpedia.codes/blog/karpathy-claude-md-rules-extended
- 原文：
  > "More than 14 rules. Mnimiy tested up to 18. Compliance dropped from 76% to 52% past 14. The 200-line ceiling Anthropic d…"
- 中文：规则数量本身会稀释遵守率；「从社交媒体收集来的规则」大多只是换词重述。
- 注意：二手实测，未在 X 找到原始数据帖。
- 可改写规则：**规则文件设硬上限（≤14 条 / ≤200 行），新增必须先删一条。**

---

## 可验证方法

### 21. 用 baseline 对照迭代 skill，直到「达到我 80% 的品味」[全文]
- 来源：@danshipper，2026-11-15
- URL：https://x.com/danshipper/status/2122091033001337134
- 原文：
  > "this weekend i made a skill to help us write context window summaries, and used autoresearch to iterate until it hit 80% of my taste on summaries vs. a no-skill baseline"
- 中文：把「品味」变成一个可对比的基线：无 skill vs 有 skill，同一批输入，人打分到 80% 收敛。
- 适用：skill / 规则 / 提示模板的迭代；适用：任何可批量生成的任务。
- 可改写规则：**每个提示模板上线前必须有 no-skill baseline 对照与人工评分记录；无对照不上线。**

### 22. 规格里写清「怎么判分」，否则模型会钻空子 [全文]
- 来源：@_jasonwei，2025-06-11
- URL：https://x.com/_jasonwei/status/1932878500865978859
- 原文：
  > "A relatively short spec (e.g., <1000 words of instructions saying what problems to create and how to grade them) often gets expanded... into thousands of datapoints. Just one sentence in the spec can be the difference between a perfect post-trained model versus one with crazy hacking."
- 中文：不到 1000 字的规格，只要能说清「生成什么问题、怎么打分」，就能扩成数千条数据；一句评分口径的差别决定模型是否 reward hacking。
- 适用：评测集 / 数据合成；适用：任意模型。
- 可改写规则：**写评测提示必须先写 rubric（维度 + 分值 + 判分依据），再写任务。**

### 23. 用「二选一 + 大规模重复」做廉价 eval [全文]
- 来源：@karpathy，2026-10-02
- URL：https://x.com/karpathy/status/2105909609487872075
- 原文：
  > "Simply ask an LLM 'Land or Water?' and give it a latitude and longitude coordinate as text. Ask 16,200 times, plot as image. The models know."
- 中文：把能力问题压缩成二元判断，跑上万次画图，就能看出模型内部表征；比精心设计的 benchmark 便宜得多。
- 可改写规则：**能做二元判定的能力点，优先用 1000+ 次重复统计而不是单次主观评价。**

### 24. 把提示词当实验变量，固定其余部分 [全文]
- 来源：@karpathy，2026-03-07（autoresearch）
- URL：https://x.com/karpathy/status/2030371219518931079
- 原文：
  > "the human iterates on the prompt (.md), the AI agent iterates on the training code (.py)... The goal is to engineer your agents to make the fastest research progress indefinitely and without any of your own involvement."
- 中文：人只改提示词（.md），agent 改代码（.py），每个点是一次完整训练运行——变量隔离得很干净。
- 可改写规则：**做提示对比时，只允许改一个变量（提示），其余（模型、温度、输入集）冻结并记录。**

### 25. 自检要产出「可审的差异」，不是「我已检查」[全文]
- 来源：@alexalbert__，2026-11-09（同条目 1）
- URL：https://x.com/alexalbert__/status/2119884951550386671
- 中文：模型自检的有效形态是「改了哪些、为什么、哪些没把握」，而不是一句「已确认无误」。
- 可改写规则：**自检输出格式固定为三列：改动 / 依据 / 未决项；缺列视为未自检。**

---

## 来源清单

| handle | URL | 日期 | 一句话要点 |
|---|---|---|---|
| @alexalbert__ | https://x.com/alexalbert__/status/2119884951550386671 | 2026-11-09 | 全项目审计：确定的直接改，不确定的列清单待审 |
| @alexalbert__ | https://x.com/alexalbert__/status/2064467657483829441 | 2026-06-09 | 给目标不給任务；写清「完成长什么样 + 怎么验证」；换模型重写 CLAUDE.md |
| @karpathy | https://x.com/karpathy/status/2105819303471976479 | 2026-10-02 | 用 ASD-STE100（80% 程度）压掉啰嗦；输出可换图/HTML/视频 |
| @karpathy | https://x.com/karpathy/status/2040470801506541998 | 2026-04-04 | idea file：分享意图与约束，让对方的 agent 重建 |
| @karpathy | https://x.com/karpathy/status/2039805659525644595 | 2026-04-02 | raw/ 原文 + 模型增量编译 md wiki（摘要/反链/概念） |
| @karpathy | https://x.com/karpathy/status/2015883857489522876 | 2026-01-26 | Claude Code 典型失效：替你假设、不澄清、过度设计；plan mode 有用 |
| @karpathy | https://x.com/karpathy/status/2027521323275325622 | 2026-02-27 | 8 个 agent 并行研究「是乱的」，别把多开当质量手段 |
| @karpathy | https://x.com/karpathy/status/2036841069636370467 | 2026-03-25 | 模型会用上下文里给的一切，RAG 无关内容会污染任务 |
| @karpathy | https://x.com/karpathy/status/2105909609487872075 | 2026-10-02 | 二选一问题跑 16,200 次，廉价 eval |
| @karpathy | https://x.com/karpathy/status/2030371219518931079 | 2026-03-07 | 人改 prompt(.md)、agent 改代码(.py)，变量隔离 |
| @simonw | https://x.com/simonw/status/2120029347948220500 | 2026-11-10 | 「This codebase is yours」降低过度谨慎 |
| @simonw | https://x.com/simonw/status/2120029567616458900 | 2026-11-10 | 官方 prompting guide 是「这一代的怪癖清单」 |
| @IamEmily2050 | https://x.com/IamEmily2050/status/2031879748834771302 | 2026-03-11 | 反对 AI slop words，用紧凑 JSON schema 提高信号密度 |
| @goodside | https://x.com/goodside/status/2113639196254671259 | 2026-10-23 | 「Prompt engineering is dead」：措辞的边际收益在降 |
| @danshipper | https://x.com/danshipper/status/2122091033001337134 | 2026-11-15 | 用 autoresearch 迭代 skill 到「我 80% 的品味」vs 无 skill 基线 |
| @_jasonwei | https://x.com/_jasonwei/status/1932878500865978859 | 2025-06-11 | <1000 字规格写清「生成什么 + 怎么判分」，一句之差决定是否 hacking |
| @dotey | https://x.com/dotey/status/2120961974519398535 | 2026-11-12 | 转译：用户故事当提示词，效果胜过严谨技术方案（仅转译） |
| @trq212（二手） | https://explainx.ai/blog/claude-5-context-engineering-thariq-doctor-july-2026 | 2026-07-24 | Claude Code 删掉 80% 系统提示词无评测损失；judgement over rules |
| @trq212（二手） | https://github.com/maxritter/pilot-shell/blob/f3c5bee78489125d28c5c174c226ff0d59d83e69/docs/docusaurus/blog/2026-07-29-claude-5-context-engineering.md | 2026-07-29 | 显式验证指令会让 Opus 5 过度验证，应删除 |
| 中文解读（二手） | https://www.uisdc.com/claude-code-10 | 2026-07-26 | Claude Code 提示词删减 80% 的中文拆解与清单 |
| 实践者博客（二手） | https://docs.bswen.com/blog/2026-05-06-chinese-ai-model-prompting-tips/ | 2026-05-06 | 中文模型不吃「隐含意图」，要显式规格 |
| agentpedia（二手） | https://agentpedia.codes/blog/karpathy-claude-md-rules-extended | 2026-05-10 | 规则 >14 条遵守率从 76% 降到 52% |

---

## 抓取缺口（不要当成已验证）

1. **`twitter search` 完全不可用**：`twitter search "prompt engineering"` 等 6+ 组中英文查询全部返回 `HTTP 404`（X GraphQL 端点变更）。已按 skill 重试链执行：重试 1 次 → `pipx upgrade twitter-cli`（已是最新 0.8.5）→ OpenCLI 未安装。**因此没有做「按关键词覆盖中英文」的系统性采样**，样本偏向已知 KOL 时间线。
2. **@trq212 原帖未抓取**：其时间线接口返回错误（181 字节），只有二手解读；原帖的完整措辞（尤其「80%」的统计口径）未核对。
3. **DeepSeek / Kimi 的一手 X 帖未抓到**：只有实践者博客，作为「模型差异」的证据强度弱于其他条目。
4. **@AnthropicAI / @OpenAI 官方账号本次时间线未出现可用的提示词方法帖**（多为发布/研究公告），故未纳入。
5. 少数推文的图片内容（如 @alexalbert__ 提到的 prompt snippet 截图）未 OCR，只记录了文字部分。
