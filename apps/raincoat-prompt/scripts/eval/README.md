# 可复跑评测

从应用根目录执行，使用 Python 3 标准库、Swift Package 和本机已有 CLI，不安装依赖。同一 `--out` 可以增量追加版本或复次。已有 completed 的同 id（case/target/version/repeat）直接复用，新增调用使用独立下游会话。历史 failed 和已有提交但无终态的 id 也会跳过，以保留本轮失败不重试的记录。

```sh
export PATH="/Users/raincai/.nvm/versions/node/v24.14.0/bin:$PATH"
bash scripts/build-app.sh
python3 scripts/eval/validate_cases.py
python3 scripts/eval/run.py --only extended_pilot --targets bitto,workbuddy --versions A,C \
  --out .build/evaluation/round-02-new --dry-run
# 去掉 --dry-run，并用另一个新目录，真实运行 10×2×2=40 次
python3 scripts/eval/run.py --only extended_pilot --targets bitto,workbuddy --versions A,C \
  --out .build/evaluation/round-02-live
```

`--only` 支持 `pilot`（原4题）、`extended_pilot`（五场景各2题）、逗号分隔的题号/glob/中文场景/split。`--repeat 2` 覆盖 repeat=1 和 repeat=2，已有记录会跳过，`--seed` 固定矩阵及匿名顺序；`--timeout` 默认180秒，submit/wait共用同一绝对截止时间，超时后最多另用2秒请求取消本次job。每次最多60次新增提交，复用记录不占新增预算，超预算时保存缺口报告并返回1；此前受限环境已用45次；解除限制后的round-03按用户新授权另计60次预算，不能把单命令默认上限误当作额外预算。本次新增调用有失败时退出码为1。仅复用已有记录、dry-run和report-only成功返回0。

全五版本和 GPT 示例（每题5次，以下仅为命令示例，本阶段未执行）：

```sh
python3 scripts/eval/run.py --only data-v0 --targets bitto,workbuddy,gpt --versions A,B,C,D,E \
  --repeat 2 --out .build/evaluation/layers --dry-run
# E 按环境/场景/模型选择一条候选，也可 --rule deepseek-check 指定；不匹配时在调用前报错
python3 scripts/eval/run.py --only data-v0 --targets bitto --versions D,E \
  --rule deepseek-check --out .build/evaluation/model-rule --dry-run
```

`--model bitto=型号` 可覆盖请求模型。不匹配的模型规则不会套用；未知型号可跑 A–D。已观测到型号回退或与请求冲突的回答不进入质量配对；未取得可见型号的结果不能作为模型规则发布证据。`gpt` 表示 **Codex CLI**，生成器目标为 `codex`，不是 ChatGPT 网页。默认请求模型分别为 `deepseek-v4.1-flash`、`kimi-k2.5`、`gpt-6.1-sol`；请求标签与后端可见标签分开记录，不冒充供应商确证版本。

## 调用与落盘

Bitto/WorkBuddy 真实使用 `local-agent submit <backend> --prompt-file ... --model ... --cwd ... --wait-seconds 0`，随后 `local-agent wait` 等待同一个 job；不传 session-id。状态目录通过 CLI 支持的 `LOCAL_AGENT_MCP_STATE_DIR` 放在当前产物的 `backend-state/`。Codex 使用 `codex exec --ephemeral --json --sandbox read-only --model ... -o ... -`。同一后端串行，两个后端可同时运行。工作目录为各次运行的独立空目录。共同指令要求只据合成材料作答，不调用工具、读写文件或发送消息；权限仍由后端实际配置决定。取消只针对本运行器创建的超时 job，不操作用户 app 进程。

- `plan.json` 为合并后的题目与运行清单。首次增量前的原计划保存在 `plan.initial.json`，每次请求的提示词、快照、哈希、待调用id和复用计数另存 `invocations/<id>.json`，新增运行通过 invocation_id 关联。
- `attempts.jsonl`：提交前的调用预约；中断后可确认哪些任务已尝试，增量执行会跳过这些id，可在后端状态中确认实际结果。
- `runs.jsonl`：case/version/target/model/repeat、完成状态、耗时、原始回答、可见模型、token 原始字段或 `null`、原始错误。local-agent 的 `succeeded` 映射为 completed；空回答、截断、失败或超时均 failed。失败也保留部分回答，不能参与质量配对。
- `raw/<id>/`：prompt.txt、全部命令 stdout/stderr 和后端完整 state；Codex 另留 answer.txt。后端 state 中的原始 usage 不统一猜算 token 或费用。
- `blind-review/`：成功配对的匿名 JSON，响应仅标 A/B，隐藏改写版本、模型、目标和运行 ID。无成功配对时目录为空。
- `private-mapping.json`：维护者保管的匿名映射；**不要交给盲评者**。同样不要交付 plan、runs 或 raw。
- `review-template.json`：待填评分模板；`reviews.jsonl` 是每行一条完成记录，见 [schema](../../docs/review-record.schema.json)。未评分不能计作平局。
- `report.md`：胜平负、逐题运行、四层独立收益、A/C 总收益、缺口及原始关键错误。

所有真实产物留在已忽略的 `.build/evaluation/`，不要提交凭据、状态库或原始业务材料。不要把 backend-state 当作可分享报告。

## 评分与报告

将 `blind-review/` 单独交给评审。按三项核心判据、一个加分项逐项判定，写下答案中的位置或短证据；记录关键错误。填 reviewer、reviewed_at（ISO8601）、status=completed，core 和 bonus 必须为布尔值。把完成的记录逐条写入 `reviews.jsonl` 后：

```sh
python3 scripts/eval/run.py --report-only --out .build/evaluation/round-02-live
```

报告入口验证评分并重新生成，不触发下游调用。比较顺序为有无关键失败、核心通过数、加分项；只改变排版不另加分。相邻配对 B/A、C/B、D/C、E/D 分别回答四层收益，C/A 仅为总收益。匿名材料可能从答案自身透露身份，不能保证完全去除自我介绍；不删改原始回答。

模型与 Agent 规则默认 disabled。启用前由 `validate_rules.py` 验证 evidence 指向的真实运行、匿名评分、相邻配对、同模型、无新增关键错误、至少两个不同配对胜出、两次 repeat 和保留题；同一证据不能重复计数，模型规则还要求双方可见型号相同并匹配规则。证据不能是手写一句“已验证”。构建及 `scripts/test.sh` 都执行证据门禁。数据文件中的基础场景模板是0.1.4文案的可复跑基线，不代表五场景均已证明有效。

## 本机结果与限制（2026-11-17）

此前受限环境提交尝试45次：`smoke-stage1` 3次（默认状态路径不可写及 Codex app-server 初始化失败），`smoke-local-state` 2次（修正状态路径后 `ps` 被拒绝），`round-02` 40次（同样 `Operation not permitted: 'ps'`）。全部 failed、无评分、无有效真实链路。完整原文在各目录 runs/raw；没有捏造回答或分数。

上述是此前受限执行环境的历史记录，原始失败保留不改。2026-11-17 执行限制解除后，`smoke-unblocked` 的 Bitto 真实链路以及 `smoke-gpt-unblocked` 的 Codex A/C 两次验证均已成功。本轮主矩阵写入 `round-03/`，最终成功/失败与逐题评分见该目录 report.md 和阶段交付记录，不再将当前状态记为沙箱阻塞。

首轮主矩阵命令如下，同目录重复执行将复用已记录id。

```sh
python3 scripts/eval/run.py --only extended_pilot --targets bitto,workbuddy --versions A,C \
  --repeat 1 --out .build/evaluation/round-03 --timeout 180 --max-calls 60
```

原轮40次A/C的初评快照保存在 `.build/evaluation/stage2-baseline/`。增量后继续使用 `run.py --report-only` 生成基础报告，第2阶段的本地汇总脚本见下方命令。既有评分随增量配对继续保留。

固定材料回放不能替代真实检索、SQL、开发落地及 ChatGPT 界面评测；GPT本轮只覆盖research-v0，不能称为五场景完整矩阵。

## 第2阶段增量示例

```sh
# 在40次A/C记录上只新增20次B
python3 scripts/eval/run.py --only extended_pilot --targets bitto,workbuddy --versions B \
  --out .build/evaluation/round-03 --timeout 180
# 下列四题的repeat=1已有，只新增repeat=2共16次
python3 scripts/eval/run.py \
  --only report-01-meeting,plan-02-build-buy,data-v0,r03-attachment-scope \
  --targets bitto,workbuddy --versions A,C --repeat 2 \
  --out .build/evaluation/round-03 --timeout 180
```

相同id若对应不同提示词、材料或请求型号，命令会指出冲突，现有原始回答与评分继续保留。同目录以文件锁防止并行提交同一任务。增量添加B不会改变既有A/C的匿名配对id和评分映射。dry-run保存本次调用计划，已有输出目录的主计划和运行记录保持原样。

`build-app.sh` 在构建成功后重新创建dist的Resources目录，再复制当前Swift Package资源并签名，因此旧的model-rules.json不会残留。清理范围为生成的app资源目录。

第2阶段本机产物包含完整逐份回答评分与汇总脚本，可按以下命令重新生成本轮报告。汇总脚本读取已记录评分，不调用模型。

```sh
python3 scripts/eval/run.py --report-only --out .build/evaluation/round-03
python3 .build/evaluation/stage2-assessment.py
```

主报告包含B/A、C/B、D/C、E/D、C/A、复次同向率与保留题结果。基础运行明细另存 `round-03/report-base.md`。保留题与GPT两个子目录继续保留各自的原始运行报告。三条下一阶段候选保存在 `stage2-rule-candidates.json`，enabled均为false。

## 第3阶段候选（不替换dist）

`Cprime`代表未发布的场景文案，不是模型规则E。先用`bash scripts/test.sh`构建`.build/debug/RaincoatPrompt`并校验候选，再显式选择：

```sh
python3 scripts/eval/run.py --only extended_pilot --targets bitto,workbuddy \
  --versions C,Cprime --composer .build/debug/RaincoatPrompt \
  --candidate-catalog docs/candidates/scene-v0.2.0.json \
  --out .build/evaluation/round-03 --timeout 180 --max-calls 20 --dry-run
```

去掉dry-run后复用旧C，仅新增20次Cprime。复次对四题用`--versions Cprime --repeat 2`，已有r1自动复用。新题用`--only 'x0*' --versions A,Cprime`，新目录`.build/evaluation/round-05-x`共24次。既有保留4题Cprime8次，复次8次，合计60，不能再额外调用GPT或重试失败。主计划的初始规则哈希来自旧轮，新增候选快照在对应invocations中；runs通过invocation_id关联。不同候选提示词不得沿用同id。

运行器追加Cprime/C、Cprime/A匿名配对，提示词完全相同的Cprime/C被排除，不能把随机输出差异归因于改写。评分和报告重生成仍使用现有schema及`--report-only`。阶段3汇总见`.build/evaluation/stage3-assessment.py`，读取已落盘的逐回答评分，不自动生成语义分数，不调用模型。

## 第4阶段候选

`Cdoubleprime`对应独立`docs/candidates/scene-v0.2.1.json`；用法与Cprime相同，但版本名与快照必须匹配。先执行测试构建debug生成器，保持dist不动：

```sh
python3 scripts/eval/run.py --only extended_pilot --targets bitto,workbuddy \
  --versions Cdoubleprime --composer .build/debug/RaincoatPrompt \
  --candidate-catalog docs/candidates/scene-v0.2.1.json \
  --out .build/evaluation/round-03 --max-calls 20 --dry-run
```

新X组选择`x07-hard-gate,x03-fixed-schema,x04-stacked-constraints,x06-controlled-language`，沿用round-05-x，已有6份A复用。因此第4阶段预计新增46次，未用完的预算不是自动重试许可。原始失败保持，新增候选相邻配对的评分仍用现有schema。

第4阶段评测与评分已完成：新增46次、成功46、无失败重试；已有新组A复用6份。`python3 .build/evaluation/stage4-assessment.py`根据已落盘人工分数重生成总报告，不调用模型。运行器`--report-only`先生成基础报告；阶段汇总再将主报告写入round-03/report.md并保留report-base.md。历史stage2/3汇总脚本不包含Cdoubleprime评分，不应再对增量后的当前目录直接运行；当前使用stage4汇总，历史报告冻结于stage4-baseline。

## 第5阶段：单条模型规则与冻结场景对照

默认 E/D 路线继续保留。`--base-version Cdoubleprime` 使 E 在冻结 v0.2.1 候选上只增加 `--rule` 指定的一条模型规则，不加入 Agent 规则。必须提供候选文件与含新评测入口的 debug 生成器。计划生成时校验 E 去掉该规则段后逐字等于 Cdoubleprime；disabled 不妨碍显式评测，也不等于启用。

```sh
export PATH="/Users/raincai/.nvm/versions/node/v24.14.0/bin:$PATH"
bash scripts/test.sh
python3 scripts/eval/run.py \
  --only plan-02-build-buy,x04-stacked-constraints,plan-04-rollout,plan-03-seasonal \
  --targets workbuddy --versions Cdoubleprime,E --repeat 2 \
  --base-version Cdoubleprime --rule kimi-plan-consistency \
  --candidate-catalog docs/candidates/scene-v0.2.1.json --composer .build/debug/RaincoatPrompt \
  --out .build/evaluation/stage5/kimi-plan-consistency --timeout 180 --max-calls 40 --dry-run
```

格式组使用 `--scene-override general`，两版都选择通用，run 同时记录 `scene=通用` 与 `source_scene`。不同场景的同 id 回答不能直接复用或沿用评分。格式规则限定“整条回答要求固定形态”，API 新增字段是误触发控制，不能一律强制 JSON。未覆盖默认开发/报告场景收益。

本轮三个目录共40次新增调用，40成功、0失败、没有重试；另有8条旧基线按逐字提示词和来源哈希复用。预算按三组总量计算，不能将示例的单命令上限当成每组各40次。`stage5-seed.py` 是本次旧基线迁移记录，不应对已有目录重复执行。原始目录、旧分和冻结快照均保留。

```sh
python3 scripts/eval/run.py --report-only --out .build/evaluation/stage5/kimi-plan-consistency
python3 scripts/eval/run.py --report-only --out .build/evaluation/stage5/kimi-format-discipline
python3 scripts/eval/run.py --report-only --out .build/evaluation/stage5/deepseek-numeric-consistency
python3 .build/evaluation/stage5-assessment.py
```

汇总读取逐份已记录的3核心+1加分+关键错误评分，不自动推断语义分数。全部成功配对一起交给原证据门禁试启用，不挑胜例。门禁除两胜、复次、保留题和精确型号外，还拒绝任何引用的 E 关键错误或质量败；证据写为 `{run_dir,pair_id,run_ids}`。结果方案4-2-2、格式2-5-1、数字0-8-0，均不启用；dist保持0.1.4，Cdoubleprime仍候选。详见本地 `stage5-report.md` 与 `stage5-delivery.md`。

## 第6阶段：收窄模型候选与新题

题库54题。三类模型候选升级为独立`0.2.0-candidate`文案，开始评测时全部disabled；不改场景快照或validate_rules.py。格式规则因现有门禁精确限定单一scene，分为开发`kimi-format-discipline`和报告`kimi-format-discipline-report`两条作用域，分别判断和启用，不合并胜例。

两域各有一题裸JSON正例和一题接口字段反例，各跑r1/r2；不使用scene-override，Swift测试验证真实Scene.detect路由。反例仍注入带条件的规则段，但明确不施加整体格式要求，观察是否干扰原任务；不声称底层匹配器完全不插入文本。

```sh
export PATH="/Users/raincai/.nvm/versions/node/v24.14.0/bin:$PATH"
bash scripts/test.sh
python3 scripts/eval/run.py --only s6-dev-json-status,s6-dev-api-example \
  --targets workbuddy --versions Cdoubleprime,E --repeat 2 \
  --base-version Cdoubleprime --rule kimi-format-discipline \
  --candidate-catalog docs/candidates/scene-v0.2.1.json --composer .build/debug/RaincoatPrompt \
  --out .build/evaluation/stage6/kimi-format-discipline --timeout 180 --max-calls 8 --dry-run
```

报告组换为`s6-report-json-decision,s6-report-api-example`及报告rule id/out；数字组为`s6-num-denominator,s6-num-units-ledger`、bitto、`deepseek-numeric-consistency`，8次；方案组为`plan-02-build-buy,plan-04-rollout,s6-plan-migration`、workbuddy、`kimi-plan-consistency`、repeat3，18次。总42次，上限44；失败不重试。所有基线同期新跑，旧评分不动。结果、逐题初评与发布判定写入本地stage6-report.md/stage6-delivery.md；报告汇总读取已记录分数，不调用下游。

## 第7阶段：正式双顺序盲评通道

先读[评测协议](../../docs/evaluation-protocol.md)，运行前固定本轮预注册。`judge.py`负责匿名prompt、严格JSON输出校验与顺序映射；`run_judge.py`只读取既有runs，完全不调用PromptComposer或重生成答题回答。两个评委默认配置为Bitto/deepseek-v4.1-flash与WorkBuddy/kimi-k2.5。新调用核对observed_model，原始输出、job、耗时、usage和错误保留。

```sh
export PATH="/Users/raincai/.nvm/versions/node/v24.14.0/bin:$PATH"
# research-v0目前有两个环境的原始配对，两个评委×两个顺序=8次；先出计划
python3 scripts/eval/run_judge.py --source .build/evaluation/round-03 \
  --base A --new Cdoubleprime --only research-v0 --judges bitto,workbuddy \
  --out .build/evaluation/judge-example --max-calls 8 --dry-run
# 检查计划后去掉--dry-run；不要和用户后台任务占用同一后端
# 导入既有结果，不发起模型调用；后台文件只读取已换行的完整记录
python3 scripts/eval/run_judge.py --source .build/evaluation/round-03 \
  --base A --new Cdoubleprime --out .build/evaluation/stage7/judged \
  --import-legacy /tmp/blindjudge/round-03-Cdoubleprime-vs-A-bitto.jsonl
python3 scripts/eval/run_judge.py --out .build/evaluation/stage7/judged --report-only
```

同一out有文件锁；已完成、已失败或已有提交预约的同一配对/评委/顺序/mode都不重复提交。`--only`可匹配case或完整new run id，`--judges`可仅选择空闲后端。每个submit只创建一个job，wait每次最多25秒（低于后端50秒上限）轮询该job，共用timeout；不是反复submit。新回答必须整条JSON且字段严格匹配[judge schema](../../docs/judge-record.schema.json)，解析失败记failed，不映射成tie。含失败的真实评审命令退出1。

产物为blind-review（只有任务、材料、原rubric、匿名A/B）、private-mapping、judges.jsonl、attempts.jsonl、raw、results.json和report.md。两种顺序映射回new/base后都指向new才胜、都指向base才负；其余有效双顺序记平。两个tie算一致平，胜+tie或相反方向不一致。缺失/失败不记平。报告分别给每个评委的胜平负、一致率和未完成数；两个评委的票不能当成两个新的答题样本。

旧脚本只保存了请求模型和截断reason；导入保留完整行快照/哈希与原文本，校验A1/A2映射、去重，不补造observed_model、job、tokens或耗时。旧前置分析/额外字段以迁移适配保留并标注，不能声称它们原本通过新严格schema。新通道不沿用旧脚本最多四次重试、parse_error当平局的行为。

关键错误独立于总体verdict：`--mode critical`要求每份回答给原critical_errors编号和逐字引文；错误引用或不在原清单的编号拒绝。批量通道只降低重复调用开销，不改判据：

```sh
python3 scripts/eval/run_critical_judge.py \
  --sources .build/evaluation/round-03,.build/evaluation/round-04-holdout \
  --out .build/evaluation/critical-example --judges bitto --batch-size 4 \
  --max-calls 18 --dry-run
```

35对、每批最多4对、两个顺序，空目录需18次调用。每批输出必须完整列出所有匿名id，无重复/漏项；每对仍保存独立规范记录及共享batch_id，usage按batch只计一次。`critical_findings`核对“候选错误减基线错误”的双顺序结果，不用reason或总体胜负替代。第7阶段已覆盖35对、单个空闲评委两顺序；两评委总体质量盲评则完整覆盖同一35对，独立列报。

成本按新submit计算：普通评审=配对数×2顺序×评委数；60次最多15对双评委新评，导入成本为0次新增提交。批量关键错误评审=ceil(配对数/批大小)×2×评委数。`--dry-run`给实际缺失调用数。金额估算用实际usage的输入/输出token乘用户所用服务的每百万token价格：`输入token/1e6×输入价 + 输出token/1e6×输出价`；缓存与harness计费另按服务账单，不猜价格。旧记录无usage，不能倒推出金额；新批量usage不能按对重复相加。本轮实测token与提交预算见stage7-delivery.md，不能把单目录上限当跨目录的新额度。

正式场景发布用`judge_release.py`重算预注册门禁，再由`validate_release.py`校验封存证据、原始回答哈希及正式模板与被评候选逐字一致。测试/构建都执行这项检查；已发布0.2.0从源码重新打包需要本地证据工件（与启用适配规则的本地证据要求一致），分发app本身不读取.build。模型/Agent校验器的逐对无质量败检查没有在本轮删除，也不拿它临时阻塞场景胜多于负门槛。

## 第8阶段独立harness候选

候选文件docs/candidates/harness-v0.1.0.json独立保存bitto-readonly与workbuddy-workspace的开发场景假设，不改正式catalog。`--harness-catalog`必须与D和显式`--rule`同用；生成器新增`--candidate-harness-compose`入口，只选择一条匹配的harness规则，禁止混入旧context候选或模型规则。运行器验证D去掉规则段后与C逐字相同；不匹配target/scene或规则未应用时在提交前拒绝。默认compose与旧D/E入口行为保持原样。

```sh
python3 scripts/eval/run.py   --only dev-01-regression,dev-02-migration,dev-04-security,s6-dev-api-example   --targets bitto --versions C,D --repeat 2 --rule bitto-readonly   --harness-catalog docs/candidates/harness-v0.1.0.json   --composer .build/debug/RaincoatPrompt --out .build/evaluation/stage8/bitto-readonly   --max-calls 16 --dry-run
```

WorkBuddy组换target为workbuddy、rule为workbuddy-workspace和独立out。完整逻辑矩阵仍为两规则×4题×两环境×两repeat×C/D=64格。16个C格跨规则共享，16个跨target D与C逐字相同、标skipped_noop且不生成回答或计收益；剩余32个独立答题格中4条历史C已核验等价并带reused_from复用。新增答题28次。双评委双顺序使用--batch-size 4联合输出总体verdict及原critical_A/B，每规则8次批量评审，合计16次；总44≤48。不是逐格独立提交，也不把共享/无操作项伪装completed。完整控制计划见stage8-matrix.json；候选、门禁和来源见stage8-preregistration.md、stage8-reuse-preflight.json。

Bitto不是按名称一律只读：CLI的sandbox仅适用GPT。WorkBuddy读写也须实际工具可用并获授权。当前固定材料共同指令禁止工具与写文件，因此该回放只评边界遵守/建议交付，不冒称已验真实文件落盘能力。原题rubric不加规则专属加分，不把未测规则记为平局或失败。

Stage8盲评示例（已完成答题后运行，同一out可先后用空闲的两个评委；不要并发写同out）：

```sh
python3 scripts/eval/run_judge.py --source .build/evaluation/stage8/bitto-readonly \
  --base C --new D --judges bitto,workbuddy --batch-size 4 \
  --out .build/evaluation/stage8/judge-bitto-readonly --max-calls 8 --dry-run
```

批量结果经相同严格JSON/原句校验，投影为pair与critical两种记录；两者共享同一个真实job，不重复统计token/调用。不合schema的批次保留失败，缺失不计平、不自动重试。每个raw/prompt.txt保留实际请求，ID传输格式澄清见stage8-transport-notes.md，不改rubric或阈值。

Stage8已预注册的harness门禁与旧模型门禁分开：两个评委各自净胜>0、顺序一致≥75%、四题/两repeat/未见保留覆盖、无新增关键错误，另外保留target/scene/型号与精确单规则差异结构检查。harness_release.py验证全套盲评证据，validate_rules.py仅对明确stage8协议走此通道；legacy/model的无质量败断言未删，也不临时挪作本轮harness门槛。通过才更新0.2.1清单与dist，否则正式0.2.0不动。

第8阶段实际44次：28份新增答题全部成功，4份历史C复用；16个评审批次9个有效、7个失败（4个超时、3个schema失败），均未重试。bitto-readonly两个评委有效子集为1胜3平0负、2胜1平1负，但各仅4/8完整配对；workbuddy-workspace为0胜1平3负、0/8完整配对。失败不记平，无法确认全量无新增关键错误，两个候选均未发布，dist保持0.2.0。原始匿名包/独立映射/失败、完整门禁见本地stage8-report.md与stage8-assessment.json。

只重算本地报告和发布判定，不发起下游调用：

```sh
python3 .build/evaluation/stage8-assessment.py
python3 .build/evaluation/stage8-verify.py
```

这两个本地交付脚本依赖对应工件；通用评审报告仍可用`run_judge.py --out <judge目录> --report-only`。候选与正式资源分别保存，普通`--compose`和浮窗不会加载外部候选。

## 第9阶段：仅补失败评审

`--repair-missing --batch-size 2 --retry-transient 1 --timeout 240`显式使用修复通道，原默认逐对/Stage8批量通道不改。先用两个评委dry-run冻结缺失计划，再可用`--judges bitto`或`workbuddy`在空闲后端分开执行。相同out有锁；同后端串行。以下只读旧回答，不运行compose或run.py，不重评已成功项：

```sh
export PATH="/Users/raincai/.nvm/versions/node/v24.14.0/bin:$PATH"
python3 scripts/eval/run_judge.py --source .build/evaluation/stage8/bitto-readonly \
  --base C --new D --out .build/evaluation/stage9/judge-bitto-readonly \
  --reuse-judgments .build/evaluation/stage8/judge-bitto-readonly \
  --repair-missing --batch-size 2 --retry-transient 1 --timeout 240 --max-calls 20 --dry-run
# 另组替换rule目录为workbuddy-workspace。检查计划后去掉--dry-run；跨目录总预算仍<=40。
```

传输格式见[judge-batch.schema.json](../../docs/judge-batch.schema.json)：每项仅pair_id/verdict/critical_flags/reason；critical_flags是A/B错误数组，必须原criterion编号与逐字quote，不是免核验布尔值。逐项模板含精确ID，reason建议短。ID前后说明仅在包含唯一一个本批24位ID时归一，原值另记；重复归一ID、缺字段/非法引用不选一条、不补默认。合法项保留；某项失败不拖累其他项。整条非JSON仍失败。

`prior-judges.jsonl`完整保存旧成功与失败；有效旧记录逐字复用，旧失败不追溯重解析。新调用每次有attempts.jsonl预约、raw原文、attempt-records.jsonl逐项结果、batch-results.jsonl调用统计；judges.jsonl是当前有效投影，每个配对/评委/顺序/mode唯一，不能把重试或质量/critical投影当多票。成功记录不覆盖，重试前的失败仍可审计。

仅后端超时或502/503/504网关错误最多自动重试一次，记录retry_of与不同job。schema/型号/权限错误不重试；命令行中的--timeout-seconds参数不构成超时错误。失败/部分成功都计入调用失败率，分别报首轮、含重试、逐项和最终缺失，不能只报重试后成功率。已有预约无终态的任务不擅自重发。修复计划冻结后不能通过重复运行对schema失败刷数，缺证据则门禁失败。

用户授权的第9阶段重试例外仅限此通道；第8阶段原始失败与封存证据不改。发布仍调用原stage8-harness-blind-v1净胜/一致/复次/holdout/关键错误门禁，没有追加或放宽条件。
