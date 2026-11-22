# Prompt 效果评测（v0.3 结构回归）

> v0.3 起，发布门禁改为**结构回归**：槽位齐全、长度不超档位预算、无标记污染、无占位符、无编造数字、两次渲染一致、阻塞追问 ≤3。入口 `python3 scripts/eval/structure_check.py`，覆盖 60 题 × 6 个目标。盲评与 A–E 分层对照已归档到 `scripts/eval/legacy/`，仅作历史参考，不再参与发布判定。

# Prompt 效果评测

当前正式场景文案为0.2.0，发布门禁使用双评委顺序盲评；人工初评只作筛查与rubric校准。历史人工报告保留，不追改为盲评。协议、门禁差异及适配规则尚未接入的限制见[evaluation-protocol.md](evaluation-protocol.md)。

评测以实际交付为准。题库、改写规则、运行计划、后端原始输出、匿名评分和报告各自落盘；失败保留原文，不生成代答或分数。运行器已完成真实链路验证，环境解除限制后的回答与失败分别落盘。发布门禁为双评委双顺序盲评，人工初评只作筛查与 rubric 校准；已发布 harness 规则的工具面确定性门禁及其探索性限制另见 0.2.1 发布记录。

## 题库与对照

[题库](evaluation-cases.json) 共60题，调研10、数据分析12、开发13、写方案12、写报告13题；19题为保留题。每题包含原稿 input/original、子场景、共享合成材料、3项核心检查、1项加分及关键错误。兼容字段 checks 的前三项为 core_checks，第四项为 bonus_check，必须一致。optimized 是历史人工候选，不参与 A–E 的客户端版本比较。

`pilot` 保留首轮4题，`extended_pilot` 为五场景各2道开发集题。运行器不根据检查项改写请求，不将验收答案传给被测模型。保留题原则上不用于调模板；第2阶段已暴露的4题在第3阶段只能算回归回放，不能再作为未见泛化样本；尚未使用的保留题仍冻结。[JSON Schema](evaluation-cases.schema.json) 描述结构，`python3 scripts/eval/validate_cases.py` 用标准库执行等价字段检查及唯一ID、引用、数量、分布、一致性校验，已接入 `bash scripts/test.sh`。

| 版本 | 实际行为 | 独立收益配对 |
| --- | --- | --- |
| A | 原文不改；共同测试指令与材料仍相同 | 基线 |
| B | 本地通用整理，关闭场景/Agent/模型适配 | B/A：通用改写 |
| C | 原文整理与主场景文案，关闭 Agent/模型适配 | C/B：场景收益 |
| D | C 加匹配场景/输入条件的 Agent 候选 | D/C：Agent 适配 |
| E | D 仅增加一条匹配目标、场景和型号的模型候选 | E/D：模型规则 |

C/A 只反映通用与场景的合计收益，不能用它证明两者各自有效。输入限制使 D/C 或 E/D 文本相同时属于无操作对照，不能支持规则启用。窄格式任务仍保留原有“一行/仅正文”约束。

## 运行与复现

入口及完整参数见 [运行器 README](../scripts/eval/README.md)。在应用根目录：

```sh
export PATH="/Users/raincai/.nvm/versions/node/v24.14.0/bin:$PATH"
bash scripts/build-app.sh
python3 scripts/eval/run.py --only extended_pilot --targets bitto,workbuddy --versions A,C \
  --out .build/evaluation/expanded-plan --dry-run
python3 scripts/eval/run.py --only extended_pilot --targets bitto,workbuddy --versions A,C \
  --out .build/evaluation/expanded-live
```

一条命令展开「题目×目标环境×版本×repeat」，最多60次提交。两后端并行、同一后端串行，从新会话运行；先随机安排调用顺序。`--only` 缩小范围，`--repeat` 增加独立重复。同一目录可增量追加，completed、failed及已有提交无终态的id均跳过；相同id的提示词、材料、型号变化会拒绝执行。

Bitto/WorkBuddy 通过 `local-agent submit` 真实调用，GPT 目标通过 `codex exec`。GPT 在本运行器中明确为 **Codex CLI**，不是 ChatGPT 普通对话或 Deep Research；客户端也使用独立 `codex` 预设。ChatGPT 界面模式仍需另外实测。模型标签、请求型号、可见型号与权限条件分别记录，不能把不同 Agent 的不同模型结果当成同模型对照。

`plan.json` 固化提示词与版本哈希；`runs.jsonl` 含 case/version/target/model/repeat/耗时/token/回答/error；raw 保留命令 stdout、stderr、完整后端 state。token 不可得时为 null，不估造成本。固定材料任务不需要联网或写文件，开发题只评审建议与测试设计，不能声称已验证真实仓库实现。

## 匿名评分与报告

成功的同题/目标/模型/repeat 版本才进入配对。可见型号与请求冲突时排除该回答，报告同时列出请求与可见标签；型号未知的回答可评整体交付，但不能作为模型规则发布证据。`blind-review/` 只提供原始任务、材料、判据和随机 A/B 回答；真实版本保存在目录外的 private-mapping.json，评审不应接触计划或运行日志。样本不足或失败导致目录为空时，报告明确未覆盖，不生成占位回答。

[评分 schema](review-record.schema.json) 记录评审者、ISO日期、三项核心布尔值、加分、关键错误及证据。填写 review-template.json，按每行一记录写入 reviews.jsonl，再执行：

```sh
python3 scripts/eval/run.py --report-only --out .build/evaluation/expanded-live
```

报告先验证记录，再计算胜平负：先比较有无关键失败，再比较核心通过数，最后比较加分。未评不算平局，调用失败不算质量败。report.md 分列四层收益及 C/A 总收益，逐题列状态、时长、配对结果和覆盖缺口，保留运行错误原文。单人评分、未独立盲审或仅一次运行均不足以作稳定效果承诺。

## 当前证据（2026-11-17）

首轮 [round-01/report.md](../.build/evaluation/round-01/report.md) 保留原状：4题、2环境、3版本、24份有效输出，单人非盲评、单次。旧规则稿合并了场景及部分 Agent 提示，不能用于拆分 B/C/D/E 收益。

此前受限环境历史记录45次提交尝试，均 failed（以下不是当前状态）：

| 目录 | 次数 | 结果 |
| --- | ---: | --- |
| smoke-stage1 | 3 | Bitto/WorkBuddy默认状态路径不可写；Codex app-server初始化 `Operation not permitted` |
| smoke-local-state | 2 | 改用应用内状态目录后，进程发现 `ps` 被沙箱拒绝 |
| round-02 | 40 | 五场景×2题×2环境×A/C，全在启动阶段因 `ps` 被拒绝；有效回答0、有效配对0 |

[扩展报告](../.build/evaluation/round-02/report.md) 和 [原始记录](../.build/evaluation/round-02/runs.jsonl) 已落盘。四层独立收益均未覆盖，A/C 总收益也没有有效样本。没有评分记录，未把基础设施失败当成改写无效。之后执行限制解除，真实链路已跑通。round-03首轮38/40成功，第2阶段新增56/56成功；C/A首轮11-5-2，复次4-2-2，同向率62.5%；既有保留题3-1-4。详见阶段2交付记录。

## 规则发布与后续

场景基线与适配数据在 [规则文件](../Sources/PromptCore/Resources/prompt-rules.json)。基础场景文案来自0.1.4，扩展为五场景可回归基线，不声称五类均已证明有效；所有 Agent/模型候选目前 disabled。`validate_rules.py` 要求启用证据引用本地 runs、评分与匿名映射，并检查相邻版本、同模型、规则原文/版本、无新增关键错误、至少两个不同配对胜出、两个 repeat 和保留题；证据去重，模型规则还要求可见型号一致且匹配。构建与测试执行门禁，客户端仅使用 enabled 且具证据的精确匹配规则。

## 第3阶段 X 经验与候选对照

25条[X笔记](prompt-patterns-from-x.md)属于外部经验，保留全文/二手/摘要标记和抓取缺口；10条外部候选全部禁用。新增`x01`至`x06`六题覆盖不确定项、完成定义与验证、固定schema、多约束叠加、验证预算、受控语言。它们是针对已知弱点设计的开发题，不能当作随机总体或保留题。

候选C'运行器名`Cprime`，必须显式提供`--candidate-catalog docs/candidates/scene-v0.2.0.json`及支持候选CLI的独立构建，不改dist。候选只改变三类场景文案，保留所有旧A/C回答及评分，新增调用预算60：主集20、复次8、既有保留回放8、新题A/Cprime24。Cprime/C与Cprime/A分别计数；相同提示词的Cprime/C不计收益。不同时间复用旧回答存在时间漂移，不能冒充同期随机实验。

`run.py --report-only`生成各目录匿名包与基础报告；第3阶段本地汇总额外记录候选对照、逐场景/逐题、两次独立Cprime对已有相应repeat基线的同向率、既有保留回放与发布判断。匿名包并未令本轮评分成为独立盲审，必须标注“单人、非盲、同模型初评”。评分人会接触原始运行，旧回答沿用已记录分数；失败配对不评，未覆盖不计平局。

发布门槛和限制见[prompt-generation.md](prompt-generation.md)候选段及运行前记录；结果与实际命令见[stage3-delivery.md](../.build/evaluation/stage3-delivery.md)。D/C、E/D及大部分GPT、真实工具任务仍需下一轮补证。

## 第4阶段：Cdoubleprime最小修复

题库现47题，新增开发集`x07-hard-gate`，区分硬租户隔离验收与允许后补的按钮阴影，禁止将未经批准的提议当门槛豁免。Cdoubleprime是独立v0.2.1候选，只向Cprime追加三条通用边界，不使用题库判据或期望答案生成提示。

矩阵为主集20次、四题复次8次、既有保留回放8次、新组x07/x03/x04/x06的16个A/Cdoubleprime格子。已有6份A复用，预计新增46次，最多60；失败原样保留不自动重试。相邻Cdoubleprime/Cprime、Cdoubleprime/A与回放Cdoubleprime/C分别评分，原评分冻结复用。评审仍单人、非盲、同模型初评。

门禁沿用第3阶段：两轮所选复次题Cdoubleprime/A各胜多于负，同向率至少75%；既有保留Cdoubleprime/A胜多于负、Cdoubleprime/C胜不少于负；不得新增关键错误。关键错误本轮核对全部新候选成功对照；缺失完整样本时标证据不足。四题保留已经暴露，只能称回归回放，未见泛化仍未覆盖。实际结果、失败、命令与是否发布见stage4-report.md及stage4-delivery.md（本地`.build/evaluation/`），未通过前dist保持0.1.4。

第4阶段实际新增46次、46成功、0失败（6份既有A复用，覆盖全部52个本轮计划格子），未重试。Cdoubleprime/A复次8-0-0→7-0-1，同向率87.5%；既有保留回放4-2-2。原WorkBuddy无障碍豁免在本次回放中未再出现，但方案r2新增工期确定化关键错误，未达发布门禁，dist保持0.1.4。新组A/Cdoubleprime为1-6-1；x07单独0-2-0，两版本均守住硬门槛。详细口径、原文与逐题结果见本地stage4-report.md，不能称独立盲审或未见泛化验证。

## 第5阶段：模型规则隔离验证

三组各4题、两次repeat、Cdoubleprime/E两版本，共48格；8条旧基线严格复用，40次新增真实调用全部成功，没有重试。E使用冻结v0.2.1场景快照，关闭Agent层，仅追加一条匹配目标、场景、型号的模型规则；不是默认 E/D，报告独列 E/Cdoubleprime。计划校验去掉规则后提示词与基线逐字相同。

格式组显式手选通用并保留题目原始场景，不能复用原开发/报告场景同id评分。新分按规则组/run_id区分；仅有 reused_from 的记录沿用旧分。每组8对均完成3核心+1加分+关键错误初评，匿名包与映射独立，仍为**单人、非盲、同模型初评**。

| 规则 | E/Cdoubleprime 胜-平-负 | repeat1 / repeat2 | 保留题 | 判定 |
| --- | --- | --- | --- | --- |
| kimi-plan-consistency | 4-2-2 | 2-1-1 / 2-1-1 | 3-0-1 | 两对质量败，disabled |
| kimi-format-discipline | 2-5-1 | 2-1-1 / 0-4-0 | 0-1-1 | 一对质量败，disabled |
| deepseek-numeric-consistency | 0-8-0 | 0-4-0 / 0-4-0 | 0-4-0 | 不足两胜，disabled |

两种可见型号均精确匹配请求（kimi-k2.5、deepseek-v4.1-flash），每组有两次repeat及保留题，E均无关键错误。全部成功配对一起调用同一个validate_rules.py；原门禁还要求引用证据不得有质量败，本轮不放宽、不挑胜例。数字组基线原判据已满分，增加等式或减少附加笔误不另加分。

方案回退包括把材料的权限集成预计6周错放成部署6周、遗漏答案来源验证，以及用待定周期替代可执行的放量观察/回滚。格式的两个首轮胜出来自去围栏，但复次均平；保留API误触发控制未被强制JSON，却额外返回started_at，违反只新增status要求。未达到逐规则启用门禁，dist不重建，仍0.1.4，Cdoubleprime继续候选。固定材料没有验证真实harness工具执行；GPT与D层仍未覆盖。完整逐题、原文、门禁错误见本地stage5-report.md与stage5-delivery.md。

## 第6阶段：收窄模型规则与针对性证据

新增7道固定材料题：分母切换、单位/表文合计2题；开发与报告各裸JSON正例/接口字段反例4题；工期预算保留题1题。4道新题在运行前无模型输出，split=holdout，先冻结材料与3核心+1加分+关键错误，不改旧题旧分。候选模型规则版本0.2.0-candidate，场景候选与原validate_rules.py均不改。

矩阵42次、上限44：plan三题各r1/r2/r3两版本18次；format开发/报告各两题r1/r2两版本合计16次；numeric两题r1/r2两版本8次。所有基线同期新跑，失败原样保留不重试。E在冻结Cdoubleprime上只加一条匹配模型规则，无Agent变量。

格式使用真实Scene.detect的development/report，Swift测试四题路由，不能用通用override替代。现有规则与门禁只允许单个scene，故format同文案分为kimi-format-discipline（development）与kimi-format-discipline-report（report），分别判定，不跨域凑胜例。接口反例仍插入条件性规则段，条款明确无整条形态要求则不施加格式、不增加响应字段；测语义不干扰，不声称匹配器完全不插入文本。

逐条用全部成功配对运行同一个validate_rules.py，型号精确匹配、单规则差异、至少两胜/两repeat/保留、E无关键错误且无质量败均不变。匿名包与映射分开，评审仍单人、非盲、同模型初评。预先记录、原始运行、初评与结果在本地stage6-preregistration.md、stage6/、stage6-report.md与stage6-delivery.md。场景Cdoubleprime不随模型规则发布；若模型候选通过，发布范围只限其精确target/model/scene。

## 第7阶段：正式盲评与场景发布

复用round-03与round-04-holdout的Cdoubleprime/A回答，两个评委各完成27+8对、两种顺序；没有新生成任何答题回答。主集两评委均17-5-5，一致23/27=85.2%；既有holdout两评委均4-2-2，一致6/8=75%。holdout就是这份既有保留回放，不再重复当未见泛化样本。

新通道严格校验整条JSON，失败/缺失不记平；旧记录采用标明来源的迁移兼容，不补造observed_model/usage。额外Bitto空闲后端核验全部35对的关键错误清单、两个顺序，逐字引用有效，未见新增关键错误；这是一个错误核验评委，不冒充两个。原非盲工期关键错误被独立复核排除，原评分不覆写。

按第7阶段预注册，场景C''通过主集净收益、顺序一致率、既有保留非负及无新增关键错误，发布正式0.2.0。没有将适配校验器逐对不得败额外套到场景门禁。模型规则旧版盲评未过，当前收窄候选未完整验收，均disabled。正式场景构建/测试现在校验封存盲评与原始回答哈希；[发布记录](releases/0.2.0.md)列明单评委错误核验、旧导入型号未确证及固定材料边界。

## 第8阶段：harness D/C 独立候选

在正式C0.2.0上分别追加一条精确匹配target/scene的harness规则，候选位于[candidates/harness-v0.1.0.json](candidates/harness-v0.1.0.json)，正式catalog不变。四道开发题含未见holdout dev-04-security及阶段6新增未见s6-dev-api-example，每组r1/r2。相同C跨规则共享，不匹配target的D逐字等于C时只保存无操作控制、不伪造回答或算作效应样本。四条历史Cdoubleprime与新正式C完整prompt等价后复用，来源与旧版本仍保留。

预注册每条规则两个评委各自净胜>0、顺序一致≥75%、两repeat及未见holdout、无新增关键错误。两个评委双顺序、每批四配对，联合输出总体verdict和原判据的关键错误编号/原句，再分别保存pair与critical记录；同job只计一次调用。与第7阶段逐对评审不同，批量/联合输出可能带来干扰，不能称两路独立错误核验。格式失败整批保留failed、缺失不算平、失败不重试，不能挑有效胜例发布。

实际44/48次新增提交：28份答题全部成功，16评审批次9有效/7失败（4超时、3schema）。bitto-readonly两个评委分别1-3-0、2-1-1，一致3/4与4/4，但各仅完成4/8配对；workbuddy-workspace分别0-1-3（3/4一致）、无完整配对。每组答题覆盖两repeat/未见holdout，盲评复次与错误核验缺失；已核子集未发现新增关键错误，不能确认全量没有。两条保持disabled，dist0.2.0不动。完整逐题、失败和门禁见本地stage8-report.md。

该轮仍是固定材料测试，禁止工具/写文件，因此没有测试WorkBuddy授权落盘分支；Bitto是否只读也必须由会话权限确认。先修评审可靠性，再设计真实权限差异任务，才有条件判断harness收益。8配对和重复四题不足以分辨10个百分点净收益；后续独立配对量按非平率20%/50%/100%约157/392/784对每规则每评委规划（α5%、80%power的近似），不事后加为本轮发布门槛。

## 第9阶段：补齐缺失盲评

仅评既有Stage8回答，保留原36个成功有序评审及所有旧失败，不生成新回答、不重评成功项。新通道每批2对、timeout240秒、精确ID与四字段模板；critical_flags仍需原错误编号/逐字引文。ID可归一前后说明，重复/缺字段/非法引用不补默认；合法项逐项保留。只有超时/网关错误最多自动重试一次，每次单独记账。详见[运行器](../scripts/eval/README.md)与[协议](evaluation-protocol.md)。

发布判定完全沿用Stage8预注册，通过有效投影中的全量两评委双顺序结果重算；attempt-records和batch-results保留首次失败、部分成功与重试，不能只报最终成功率。因保留旧成功顺序，新旧批大小/理由长度混合可能与顺序效应混杂，需要披露，不能事后通过重评有利项修一致率。全部未过时保持正式0.2.0；下一轮只写冻结微仓库/真实权限/实际diff的预注册，不在本轮启动。

第9阶段实际新增14次评委调用，失败/部分成功0次、重试0次，0次新答题。全量双评委结果与原门禁重算见本地stage9-report.md；两条未过、保持disabled，dist0.2.0不动。stage10-preregistration已写冻结文本/真实权限前置/产物rubric/样本及成本，本轮未执行。

## Stage11 独立确认

这是相对于 Stage7 的第二次独立复跑：重新生成 C/A 回答，并对20个独立配对做双评委、双顺序盲评；不是把 Stage7 的旧回答再算一次，也不把两个评委的票计成40个独立配对。

| 评委 | C/A胜-平-负 | 顺序一致率 | holdout胜-平-负 |
| --- | --- | --- | --- |
| Bitto / deepseek-v4.1-flash | 9-6-5 | 15/20＝75% | 6-4-2（12对） |
| WorkBuddy / kimi-k2.5 | 9-4-7 | 17/20＝85% | 5-3-4（12对） |

质量结果支持正净收益，但16个批量关键错误审计在中断时尚无有效完成（0/16）；未完成不能解释为“无新增关键错误”。因此 Stage11 不是又一次完整安全门禁通过，已发布场景仍沿用 Stage7 的封存发布证据。本次0.2.2只同步版本与文档，复用0.2.1的harness证据，不改场景或规则。原始结果见[Stage11最终报告](../.build/evaluation/stage11-final/report.md)和[未完成的关键错误审计](../.build/evaluation/stage11-critical/report.md)。
