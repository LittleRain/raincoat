# Prompt 生成规则

当前正式场景文案0.2.0，文本与冻结Cdoubleprime逐字一致；模型与Agent专属规则全部disabled。客户端仍在本机改写，不调用改写模型。浮窗与 `--compose` 使用同一个 PromptComposer；评测 `--eval-compose` 显式开关各层，避免另写一套“评测专用优化稿”。

## 数据与执行路径

共享数据为 [Sources/PromptCore/Resources/prompt-rules.json](../Sources/PromptCore/Resources/prompt-rules.json)，由 Swift Package 作为资源打包。dist 内带同一资源 bundle，离开源码目录也能使用；不存在依赖开发机 `.build` 才能读取规则的交付要求。旧 `assets/model-rules.json` 空文件不再读取。

| 数据 | 用途 | 证据含义 |
| --- | --- | --- |
| templates | 六类基底（含通用）及比较、排名、估算、归因、会议等子场景文案；按有序条件取第一条 | 从0.1.4提取的可复跑基线；不等同于五场景均已证明有效 |
| signals | 现有分类逻辑未命中时的词汇补充，含目标、版本与来源记录 | 只影响场景建议，不证明改写收益 |
| research_web/materials | 按用户是否限制来源选择证据要求 | 不替 Agent 确认联网能力 |
| rules | kind=harness/model，含 id、target、scene、version、evidence、enabled、instruction；模型规则另含型号 | 所有候选目前 disabled；启用需通过真实运行证据门禁 |

先保留原任务中的事实、数字、路径、格式、限定来源和排除条件；仅去掉明确的目标路由前缀，例如“这条发给 Bitto”。场景选择以主任务为准；数据分析、开发等明确动作仍优先于末尾“写成报告”。场景文案补充方法与可验收交付，不填造缺失事实。

| 场景 | 基线文案关注点 |
| --- | --- |
| 调研 | 相同条件比较、硬要求、一手证据与日期，或者仅从用户材料引用与标缺口 |
| 数据分析 | 指标、分子分母、粒度、期间、可比基线、复算与归因边界；排名核对平台、窗口、代理指标及来源；估算核对样本和假设 |
| 开发 | 目标行为、允许修改范围、实际入口及检查结果，不声称运行过没有执行的测试 |
| 写方案 | 可行路线、取舍、依赖、最小试点与成效判据 |
| 写报告 | 受众、篇幅、结论、材料依据与行动；会议任务列负责人和截止日期，未知项待确认 |
| 通用 | 保留已有材料和输出格式，说明会改变结果的具体缺口，先完成可确认部分 |

“一行/仅正文/只回复”等窄输出限制继续走保守整理，不强行加入长场景模板。仅用材料、禁止联网等限制会关闭公开核验要求。未知工具只在规则明确启用且满足条件时给条件式指令；候选规则不能因识别到某个应用就默认生效。

## Agent 与模型匹配

当前仍可识别 Bitto、WorkBuddy、ChatGPT，并手选 Deep Research。可选 OCR 只从支持窗口的模型控件区域读取单帧，多个型号信号冲突则未知；不将正文里提到的模型当成当前型号。用户手选与显式路由优先，其次当前窗口与最近确认。场景信号和模型标签均为本机处理。

为区分自动评测环境，新增独立 `Codex CLI` 目标预设；不把 Codex 窗口自动当成 ChatGPT。GPT 运行器使用该预设，ChatGPT 网页、普通对话、Deep Research 的能力不能由 CLI 结果代替。档案见 [harnesses.md](harnesses.md) 与 [models.md](models.md)。

普通客户端只加载 enabled=true 且 evidence 非空的规则；必须精确匹配 target、scene、标准化 model 标签及输入条件。没有规则时使用场景基线。模型表达改动只允许一条。当前 Agent/模型候选均未启用，浮窗的“新增内容”只显示实际插入的场景要求。

发布前 `validate_rules.py` 还校验 evidence 对应的原始运行与匿名评分：规则版本及文案一致、同模型相邻版本、至少两次胜出、两个 repeat、有保留题、无新增关键错误。测试和构建都执行校验，不能仅填写一个非空 evidence 就随包发布。

## 评测开关

```sh
printf '%s\n' '这两周退货率是不是变高了，问题主要出在哪？' |
  'dist/Raincoat Prompt.app/Contents/MacOS/RaincoatPrompt' --eval-compose C bitto dataAnalysis deepseek-v4.1-flash
```

A 原文；B 通用；C 场景；D C 加 Agent 候选；E D 加显式选定的一条模型候选。E 的最后一个参数为 rule ID，运行器自动匹配，也可 `--rule` 指定。常规 `--compose bitto [model]` 不启用候选。窄格式或条件不匹配可能产生相同文本，此时不能主张适配收益。

执行环境已解除限制。第2阶段真实调用支持分层比较，但C/A的复次与既有保留题收益不稳定，不能声称场景文案已普遍有效。当前分发仍保留0.1.4文案。

## v0.2.0 场景文案候选（候选，未发布）

[scene-v0.2.0.json](candidates/scene-v0.2.0.json)是独立完整目录快照，只对调研、写方案、写报告的原模板追加最小边界；开发、数据分析、通用与路由、识别、交互均保持原样。它不会被普通客户端加载。评测用`--candidate-compose <catalog> <target> <scene> <model>`注入同一个PromptComposer，以C层开关生成；运行器版本名为`Cprime`。计划的invocations保留候选全文和SHA256，禁止用新的候选覆盖同id。

- 调研：核对已有事实，区分实际行为、条件意愿与计划；跨来源计算先核对人群、时间、粒度与分母；确定结论直接交付，不确定项待审并给最小验证方法。针对材料误读与跨粒度计算。
- 写方案：硬约束先满足；保留“预计”，工期不改成保证；未知费用和依赖列待审，写明完成定义及对应验证，建议门槛不冒充承诺。
- 写报告（含会议）：事实、提议、待确认分开；保留“疑似”“未发现”；不虚构负责人、日期、系统或采样信息；确定内容直接成稿，不确定项列清单，新增行动标建议。

这些文案吸收[X笔记](prompt-patterns-from-x.md) #1/#2/#13/#19/#25；外部说法只作为动机。本地回退对应关系记录在资源文件`external_candidates[].observed_failure`。10条外部候选与可执行的`rules`分区，全部`enabled=false`，Swift不会自动执行；校验器拒绝仅凭外部经验启用。#9/#17是二手来源，其他候选也没有因全文抓取而变成本地证据。受控语言和固定schema等技巧先补题，不塞入本次三类回退补丁。

发布判断在运行前固定于`stage3-preregistration.md`：两次Cprime/A均胜多于负、复次同向率至少75%；既有保留题Cprime/A胜多于负且无新增关键错误。只是探索性门槛，不能推导统计显著。已暴露的保留题用于回归，未见保留题泛化仍有缺口。未通过时保留候选，不重建或替换dist。

## v0.2.1 候选（第4阶段，未发布）

[scene-v0.2.1.json](candidates/scene-v0.2.1.json)保留Cprime完整文案，在每个模板末尾仅追加相同三条`candidate_guards`：硬前置不得自行豁免、固定输出形态优先、全文保留限定词与未知项。硬验收未满足时保持阻塞并说明不发版/不放量的后果；只有材料明确允许才调整。未知费用用变量/待定，角色、负责人和期限写待分配。JSON/固定字段/固定行数不允许模板额外加段落、围栏或小节。

运行器名`Cdoubleprime`，必须显式指定该候选快照；默认客户端仍加载原正式资源，父候选与dist均不改。两种候选名不能混用同一快照，计划校验型号、case、repeat及提示词一致性。新增x07硬发版门槛题与三道既有X题一起验证，发布判断固定在stage4-preregistration.md。只有满足全部第4阶段门禁才将这一候选以正式v0.2.0发布；候选编号不等于产品发布号。

第4阶段判定：**候选，未发布**。复次同向率87.5%、既有保留回放胜负条件通过，新增工期关键错误未过门禁；独立v0.2.1快照保留，未提升正式场景文案、未重建dist。硬前置改善与固定输出改善不等于全局遵守：WorkBuddy固定JSON仍带围栏，多份回答制造材料未给的阻塞，详见stage4报告及评分证据。

## 第5阶段模型候选（未发布）

`rules` 新增 `kimi-plan-consistency`（workBuddy/kimi-k2.5/plan）、`kimi-format-discipline`（workBuddy/kimi-k2.5/general）及 `deepseek-numeric-consistency`（bitto/deepseek-v4.1-flash/dataAnalysis），均 disabled，记录此前具体 run/失败模式。分别约束跨段工期与成本一致、整条回复的固定形态、数字分母单位一致与复算。固定形态规则不将 API 新增字段或 JSON 示例当作整条回复必须 JSON。

评测 `--candidate-model-compose <catalog> <target> <scene> <model> <ruleID>` 使用冻结 Cdoubleprime 模板与当前 bundled 适配规则；显式 E 只加入该模型规则、关闭 Agent 层。运行器 `--base-version Cdoubleprime` 校验精确单条增量。窄输出仍保留旧的保守整理文本，但允许匹配的模型规则追加；所有候选 disabled 时普通 CLI/浮窗输出保持旧行为。`evidence` 兼容候选字符串及正式 `{run_dir,pair_id,run_ids}` 结构，后者仍须通过构建前门禁，不能仅因能解码就启用。

第5阶段40次真实调用全部成功，单人、非盲、同模型初评。E/Cdoubleprime：方案4胜2平2负、格式2胜5平1负、数字0胜8平0负。方案与格式被现有“不得有质量败”门禁拒绝，数字不足两胜；三条继续 disabled，未发布0.2.0，dist与正式场景文案均保持0.1.4。型号精确匹配仅指 local-agent 可见标签。格式组手选通用，不能泛化为其他场景；模型规则在候选基底上的结果也不等于在正式旧场景上的验证。

## 第6阶段模型候选

仅修改三类模型规则文案，不改场景模板或信号。plan将限定词绑定原对象，材料已知工期不能移到别的对象或变未知，允许明示建议的周期/阈值，不把执行方案整体改成待定。format只约束明确指定的整条回复形态，接口字段/JSON片段/对比样例不构成整条格式要求；不向响应增加示例内的内部字段。numeric限定三个核对点：分母切换明示、先统一单位、表内合计与正文一致。

候选版本0.2.0-candidate。format因单场景数据与门禁契约拆为开发kimi-format-discipline和报告kimi-format-discipline-report，文案相同、证据和enabled状态独立。没有通过general证据启用开发或报告。当前评测精确E/Cdoubleprime通道保持；API反例会有条件性规则段，但内容明确不施加整体输出格式。发布前按既有门禁逐条判定，不改变校验器或候选场景，实际结论见本地stage6-report.md。

## 第7阶段正式0.2.0

Cdoubleprime的完整templates提升为正式0.2.0，候选快照仍保留为历史原件；不是让GUI加载外部候选。基础控制文案封存在scene-baseline-0.1.4.json，避免正式文案提升后把新场景误当旧候选的控制组。validate_rules.py仅调整这项历史基底定位，未删除适配收益的无质量败断言。

构建与测试另执行validate_release.py，校验正式模板与被评候选文字相同、匿名评审证据和原始回答哈希、预注册场景门禁。0.2.0没有启用模型规则，既有model候选仍独立保留，不能凭场景发布或旧版本盲评顺带启用。历史A/B/C等的提示词已冻结；新正式生成器的C不等于原0.1.4 C，复跑须使用匹配版本或新输出目录，增量冲突不会覆写旧回答。

## 第8阶段 harness 候选（未发布）

[harness-v0.1.0.json](candidates/harness-v0.1.0.json)独立保存两条开发场景候选。bitto-readonly只在已确认只读/固定材料时限制写入和虚构检查，不把Bitto名称当全局只读证明；workbuddy-workspace只在工作区工具可写且用户授权时要求实际落盘路径，否则完成材料任务并明确建议路径、尚未落盘/未运行。未知路径不补造。

显式`--candidate-harness-compose <catalog> <target> <scene> <model> <ruleID>`与运行器`--harness-catalog`为评测通道，D仅追加所选一条匹配harness规则；删除该段须与正式C逐字相同。不匹配target/scene不发起评测调用。默认参数仍为空，普通CLI/浮窗继续使用正式bundled资源，没有加载外部候选或改变交互。

两条候选44次新增调用后均未过预注册盲评门禁：只读规则有效子集净胜但缺完整复次/错误核验；工作区规则有效子集回退，另一个评委无完整配对。两条enabled仍false，正式场景和dist保持0.2.0，未发布0.2.1。`harness_release.py`仅对显式stage8协议验证全量盲评，不把模型门禁逐对零败要求套到本轮harness；legacy/model门禁不变。后续通过时，补丁发布只允许启用已验harness，保留已发布0.2.0场景和未发布模型候选。


第9阶段只修评委传输并补缺失顺序，不修改harness候选、正式场景、默认compose或答题回答。候选是否启用仍由原Stage8完整门禁决定；解析ID归一、短输出及超时有限重试不构成新的规则收益证据。当前候选和正式资源的版本/状态以Stage9最终交付与发布记录为准，不能用修前有效子集净胜替代全量结果。

第9阶段最终两条harness均未过门禁，候选与正式catalog逐字未变，仍disabled。补齐评委并不授权修改候选或场景；dist保持0.2.0，无0.2.1发布。
