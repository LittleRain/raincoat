# Raincoat Prompt v0.3：按结构生成，不做长文案

日期：2026-11-18。本文件是 v0.3 的唯一需求真源；与旧 `product-design.md`、`evaluation.md` 冲突时以本文件为准。

## 定位

办公场景、多 agent 场景的**提示词强化器**。快捷键唤起 → 自动识别当前 agent 与模型 → 识别场景 → 按该模型需要的结构补齐 → 缺关键信息时最多问 3 个问题 → 纯文本交付到剪贴板。

不做：联网检索、替用户执行任务、给用户写长篇"专业模板"。

## 目标函数

给定（用户原话、agent、模型、场景），产出一份**结构完整、信息足够、长度克制、目标模型友好**的纯文本 prompt；判据是**槽位是否齐全、是否超预算、是否编造、是否可稳定复现**，不是下游回答的盲评胜率。

## 六槽位

| 槽位 | 含义 | 说明 |
|---|---|---|
| 角色 | 以什么身份做 | 需要专业判断时出现；改写、纪要可省 |
| 目标 | 交付什么、给谁用 | 永远必填 |
| 材料与约束 | 依据、口径、预算、合规、权限 | 有外部依据或硬限制时必填 |
| 衡量方式 | 完成长什么样、怎么验 | 分析、方案、调研、代码必填 |
| 边界 | 不做什么、未知怎么处理 | 有事实/权限/合规风险时必填 |
| 输出形态 | 长度、结构、格式 | 用户提了格式，或场景默认有交付物时必填 |

## 场景 × 必填槽位（阻塞项才追问）

| 场景 | 必填（缺则问） | 默认可省 |
|---|---|---|
| 写作与改写 | 目标、输出形态 | 角色、衡量方式 |
| 汇报与周报 | 目标（含受众）、材料与约束（周期/口径）、输出形态 | 角色 |
| 会议纪要与待办 | 目标、材料、输出形态（待办格式） | 角色 |
| 数据分析与归因 | 目标、材料与约束（口径/期间/分母）、衡量方式 | 角色 |
| 调研与竞品 | 目标、边界（来源范围/时点）、衡量方式 | 输出形态 |
| 方案与策划 | 目标、材料与约束（预算/时间/人）、衡量方式 | 角色 |
| 代码与调试 | 目标、材料（代码/报错/环境）、衡量方式（如何算修好） | 角色、边界 |

## 模型档位与长度预算

证据：OpenAI 官方把模型分成两类——"A reasoning model is like a senior co-worker. You can give them a goal to achieve and trust them to work out the details." 与 "A GPT model is like a junior coworker. They'll perform best with explicit instructions"（https://developers.openai.com/api/docs/guides/prompt-engineering，抓取 2026-11-18）。Anthropic 官方在迁移章节明确写 **Remove over-prompting**，并说明"For model intelligence and instruction following have advanced such that most use cases ... no longer require it"（https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices，抓取 2026-11-18）。这两条支持"越强的模型给越短的 prompt"。

| 档位 | 归属 | 长度预算 | 结构策略 |
|---|---|---|---|
| 前沿（reasoning） | GPT-6.x / Codex、Claude 5.x | ≤ 4 句、≤ 120 字 | 只给目标 + 验收 + 必要约束，其余交给模型判断；不写角色扮演、不写步骤 |
| 中档 | DeepSeek V4（Bitto）、Kimi K2.5（WorkBuddy）、DeepSeek 官方 App | ≤ 7 句、≤ 220 字 | 角色 + 目标 + 约束 + 验收 + 输出形态；一句话一个要求 |
| 受限 harness | 无工具执行的后端（如当前 WorkBuddy 桥接） | ≤ 10 句、≤ 320 字 | 中档结构 + 一句"没有工具执行能力，缺料就列清单"，不写步骤 |

DeepSeek 与 Kimi 未找到官方 prompt 结构指南（`api-docs.deepseek.com/guides/prompt_engineering` 404），档位按模型类别与实测行为归档，不冒充官方建议；后续拿到官方文档再校准。

## 渲染规则（纯文本）

1. 不用 Markdown 标题、加粗、编号列表、XML 标签；除用户明确要求格式。
2. 顺序：前沿 = 目标 → 验收 → 约束；中档/受限 = 角色 → 目标 → 约束 → 验收 → 输出形态。
3. 不重复用户已给的信息；不叠加同义要求；一句话只放一个要求。
4. 非阻塞缺失槽位**不写进 prompt**，也不用占位符；浮窗用一行提示"未包含：X"。
5. 渲染结果必须可复现：同输入同目标两次输出一致。

## 缺信息交互

只对**阻塞槽位**发问，一次问完，最多 3 个；每个问题附一个默认值（用户可直接回车采用）。用户不答则按默认值渲染，并在提示行标注"按默认：X"。

## 评测（替代 A–E 盲评门禁）

发布门禁改成机器可判的结构回归，覆盖 7 场景 × 5 目标：

1. 槽位覆盖：必填槽位在渲染文本中有对应表达（允许不同措辞，用关键词映射表）；
2. 长度预算：不超该档位句数与字数上限；
3. 无标记污染：不含 `#`、`**`、`<...>`、`1.` 等；
4. 无占位符：不含 `TODO`、`待补充`、`[请填写]`；
5. 无编造：材料外数字/人名不得出现（材料白名单校验）；
6. 稳定复现：同输入渲染两次完全一致；
7. 追问上限：阻塞问题 ≤ 3。

盲评与下游质量抽检降为季度抽查，不进发布门禁。

## 迁移

- 删除：`Assets`/catalog 里的场景长文案（0.2.0 templates）、A–E 盲评门禁入口、`docs/evaluation.md` 的盲评门禁描述。
- 归档：`.build/evaluation/**` 原样保留；`docs/evaluation-protocol.md` 标注"v0.2 历史，v0.3 起仅作参考"。
- 保留：快捷键、窗口 OCR 识别、剪贴板、菜单栏、`--compose` 调试入口。
