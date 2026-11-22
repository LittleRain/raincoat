# Harness 档案

记录日期：2026-11-17。以下依据本地源码、CLI 帮助与落盘运行记录，不将产品品牌当作工具或权限保证；本阶段没有重新做产品市场调研。

| 环境 | 可识别信号与运行入口 | 能力边界 | 候选改写要点与证据 |
| --- | --- | --- | --- |
| Bitto 桌面/本地桥接 | bundle ID `ai.bitto.desktop`；可选 OCR 仅匹配工具栏模型标签；评测 `local-agent submit bitto` | 桥接需发现正在运行的 Bitto、读取本机配置并建立新会话。SQL、联网、写入取决于当前工作区，不由标签推断 | 数据分析先确认只读工具、字段粒度和日期；不可读时列缺字段。0.1.4曾与场景合跑，未隔离 Agent 收益，故规则 disabled |
| WorkBuddy 桌面/CLI | bundle ID `com.tencent.workbuddy.mac` 或 `com.workbuddy.workbuddy`；评测 `local-agent submit workbuddy`，桥接调用本机 CLI | 桌面标签与 CLI 不是同一能力确证；知识库/连接器/工具授权需逐次核对 | 指定知识库确实可读时再引用文件及日期，不把工具存在当作授权。缺独立 D/C 证据，disabled |
| Codex CLI | 评测目标 `gpt`，使用 `codex exec --ephemeral --json --sandbox read-only`，客户端预设 `codex` | 独立于 ChatGPT；本轮运行在空工作目录，不含真实代码仓库。模型型号仅为请求值，JSON 不提供供应商确证 | 有可读项目时遵守项目规范；按用户授权修改；只报告实际检查。候选 disabled |
| ChatGPT 普通对话 | `com.openai.chat` 或受支持宿主的明确 `ChatGPT` 窗口标题；原文“发给…”或手选优先 | 本轮未自动调用；会话附件、搜索和连接器不能由 bundle ID 推断 | 使用对话中确实可读的表；未知时给所需字段与复算方法。候选 disabled |
| ChatGPT Deep Research | 显式目标或手选模式，不根据研究对象名自动切换 | 与普通对话分开；本轮未测。需确认上传/连接来源及公网访问 | 区分材料入口、已授权来源与公开核验；候选 disabled |
| 通用 | 无可靠当前窗口时回退最近确认目标或通用 | 不承诺工具、联网或文件能力 | 场景基线可用；不应用模型专属规则 |

## 运行证据与来源

- [识别代码](../Sources/PromptCore/PromptCore.swift)、[窗口 OCR](../Sources/RaincoatPrompt/WindowRecognition.swift)：可见标签仅是 UI 信号，多个模型名出现时返回未知。应用未启动 Codex 窗口检测，仅新增独立 CLI 预设，避免把它当 ChatGPT。
- 本机 `local-agent 0.2.0 submit --help`、`local-agent wait --help` 与源码 `apps/raincoat-buck/src/raincoat_buck/bridge.py` / `shared.py`：确认新会话参数、`LOCAL_AGENT_MCP_STATE_DIR`、终态 `succeeded` 及原始 state 格式。CLI 版本与命令也固化在新计划中。
- [首轮报告](../.build/evaluation/round-01/report.md)：两环境各12份有效输出，工具调用均0；模型和环境同时变化，不能分别归因。
- [扩展报告](../.build/evaluation/round-02/report.md)：40次启动失败；本地进程发现 `ps` 被当前沙箱拒绝，尚无本阶段有效回答。Codex 失败见 [探针](../.build/evaluation/smoke-stage1/report.md)。

此档案不声称已验证联网、SQL、实际工程写入或任何未跑过的组合；上游界面和权限变化后应复查信号、重跑受影响配对。

## 2026-11-18：D层候选的能力边界

Stage8选择独立候选文件harness-v0.1.0.json中的bitto-readonly（bitto/development）与workbuddy-workspace（workBuddy/development），未直接改正式规则。名称不代表权限事实：本机local-agent submit --help展示allowed-tool与sandbox，但安装代码bridge.py明确sandbox只适用GPT；WorkBuddy需allowed_tools授权，Bitto可有交互授权。没有证据说明Bitto所有会话只读、WorkBuddy所有会话均可写。

本轮固定材料共同指令禁止工具/读写文件。候选按已确认权限作条件式改写：只读时交付最小补丁与建议验证、不假称执行；确实可读写且用户授权时才交付实际落盘路径；仅材料时给建议路径、未知待确认。因此结果只支持该文本边界任务，不能冒称已验证检索/编辑/命令真实落地。各环境只测当前DeepSeek/Kimi标签，不能归因于脱离模型的harness独立能力。

来源：本机CLI help与 `apps/raincoat-buck/src/raincoat_buck/bridge.py` 权限参数校验、stage8-preregistration.md和真实raw记录；未联网补造工具能力。实际盲评与发布状态见本地stage8-report.md。

本轮28份新增答题工具调用数均0，与固定材料约束一致。候选不发布：只读规则有效子集净胜但缺完整盲评/错误核验；工作区规则有效子集回退且另一评委无完整配对。16个联合批次7次失败，不能把这种缺失当规则无收益。正式两条仍disabled，dist0.2.0不动；真实工作区读写能力应在另一个预注册的权限/产物实验验证。

## 2026-11-18：工具面探针与 0.2.1

前两轮把 harness 差异测成「措辞」，根因是题面统一写着「仅回复文字，无需调用工具」。两条真实调用确定了能力边界：

| 探针 | 请求 | 返回 | `tool_call_count` |
| --- | --- | --- | --- |
| bitto（deepseek-v4.1-flash） | 读取 `/tmp/harness-lab/probe.txt` 第二行 | `beta` | 1（真实执行） |
| workbuddy（kimi-k2.5） | 同上 | `Read with path="/tmp/harness-lab/probe.txt" line=2 line=2` | 0（把调用当文本吐出） |

据此新增 `docs/eval-cases-tools.json`：8 道工具面题，每题一个冻结小工作区，工作区里都埋着「文档说 A、代码是 B」的不一致；判据是机器可校验的，不看评委分：回答是否真的引用了工作区里的 `EVIDENCE_ID`、是否输出了伪造的工具调用块（`Grep with` / `Read with` / `Function Call` / `<Agent>` / `$Region:`）、是否改动了工作区文件。

结果：bitto 8/8 真实读文件并正确指出代码与文档冲突（工具调用 3–5 次，源码文件零改动，只多出 `__pycache__`）；workbuddy 在基线（C）下 4/4 局要么伪造工具调用、要么停在「让我先搜索」不动，改成「明说没有工具能力 + 禁止工具语法 + 缺料就列清单」之后 4/4 给出可用回答，探索集与 4 道 holdout 的改善分别为 4/4、3/4，0 回退。这条规则以 `workbuddy-no-tools` 随 0.2.1 启用；bitto 一侧因为已经会读文件，不加规则，避免无收益的提示膨胀。

限制：WorkBuddy 的「无工具」是当前桥接环境下的观测，后端升级后需重测；工具面判据是在看过基线之后才定的，holdout 是事后补的对照，不能当作预注册盲评。原始记录见 `.build/evaluation/stage10/tools-lane/runs.json`，门禁实现见 `scripts/eval/tools_release.py`。
