# Raincoat Prompt

> **v0.3 起行为已变更**：按六槽位（角色/目标/材料与约束/衡量方式/边界/输出形态）生成纯文本 prompt，按模型档位控制长度（前沿 ≤4 句/≤120 字，中档 ≤7 句/≤220 字），只对阻塞槽位最多追问 3 个。需求真源见 [docs/product-v0.3.md](docs/product-v0.3.md)，变更见 [docs/releases/0.3.0.md](docs/releases/0.3.0.md)。

当前分发版本 **0.3.0**：浮窗与 `--v3-compose` 使用六槽位生成器；旧的场景模板、`PromptComposer` 与 A–E 盲评门禁已删除，盲评脚本归档在 `scripts/eval/legacy/`。

Raincoat Prompt 是一个 macOS 菜单栏应用。打开后直接输入任务，边输入边识别场景，按当前或最近使用的 Agent 组织一份可编辑的 Prompt。

## 构建与打开

适用于 macOS 14 及以上。从本目录使用 Xcode 或 Swift 6 Command Line Tools 构建。

```sh
bash scripts/build-app.sh
open "dist/Raincoat Prompt.app"
```

构建脚本生成本机签名的 `dist/Raincoat Prompt.app`。启动时显示输入浮窗，默认按 `⌃⌥Space` 或从菜单栏打开。点击浮窗的「唤起设置…」，或从菜单栏进入「设置唤起快捷键…」，按下想用的组合键并保存。也可恢复默认或切换到仅从菜单栏唤起。新组合注册失败时会继续使用已注册的旧组合。

1. 写下任务。场景标签会在输入停顿后自动更新。可手选场景、目标 Agent 和模型，覆盖调研、数据分析、开发、写方案、写报告。
2. 按 `⌘↵` 生成预览。也可以点击「优化 Prompt」。
3. 在预览中直接修改内容，再按 `⌘↵` 或点击「复制并关闭」。回到目标工具后自行粘贴。

改写在本机进行。应用整理常见口语表达，并按匹配场景补充交付要求。输入「给游戏IP list，按B站内的热度排序，用nomo」会补充统计时段、可比较的热度口径和排名表。未识别到专门场景时使用通用规则，文案润色和指定输出格式的任务仍可改写。预览可以直接编辑，点「返回修改」可回到原始输入后再优化。

点击浮窗左上角的红色关闭按钮，或按 `Esc`、`⌘W` 收起浮窗。再次唤起可继续编辑草稿。要退出应用，从菜单栏选择「退出 Raincoat Prompt」。

Bitto 与 WorkBuddy 可通过应用识别。ChatGPT 需要能从当前窗口识别其界面，Deep Research 可手选。其他窗口沿用最近确认的目标。默认在本机按场景整理原文；Agent 与模型候选规则按证据门禁启用；当前仅 WorkBuddy 的开发场景工具边界规则启用，模型规则仍禁用。可手选 Codex CLI，与 ChatGPT 环境分开。

菜单栏中的「截图识别目标模型」是可选功能。开启后按 macOS 提示授予屏幕录制权限。应用在唤起时按当前 Agent 窗口取一帧，在本机识别顶部工具栏及底部输入区的模型标签。用户输入、截图和 OCR 文本在本机处理。已复制的目标及已确认的模型作为下次选择参考。

## 验证

```sh
bash scripts/test.sh
printf '%s\n' '这两周退货率是不是变高了，问题主要出在哪？' |
  "dist/Raincoat Prompt.app/Contents/MacOS/RaincoatPrompt" --v3-compose bitto
```

命令行与浮窗使用同一个本地生成器。基础场景和候选适配统一由 `Sources/PromptCore/Resources/prompt-rules.json` 随应用分发。构建和测试校验证据门禁，目前仅启用 `workbuddy-no-tools`，模型规则仍禁用。发布模型规则前，按 [评测方案](docs/evaluation.md) 完成对照。生成方式及后续适配见 [产品设计](docs/product-design.md) 与 [改写规则](docs/prompt-generation.md)。

## 评测

题库共60题（调研10、数据分析12、开发13、写方案12、写报告13），19题保留；新增7道[X经验与硬门槛回归题](docs/prompt-patterns-from-x.md)。运行器使用客户端同一个生成器，支持 A原文 / B通用 / C场景 / D加Agent / E加一条模型规则；真实调用 Bitto、WorkBuddy 与 Codex CLI，原始输出和失败均落盘。

```sh
export PATH="/Users/raincai/.nvm/versions/node/v24.14.0/bin:$PATH"
python3 scripts/eval/run.py --only extended_pilot --targets bitto,workbuddy --versions A,C \
  --out .build/evaluation/expanded-plan --dry-run
```

去掉 `--dry-run` 并使用新输出目录，运行五场景×2题×2环境×2版本，共40次。支持 `--only`、`--repeat`；每次最多60次。评分为匿名配对，人工填 `reviews.jsonl` 后用 `--report-only` 生成胜平负。完整用法见 [运行器 README](scripts/eval/README.md)，题库校验与运行器单测已接入 `bash scripts/test.sh`。

执行环境解除限制后，round-03 首轮38/40成功；第2阶段新增56次均成功。C/A首轮11胜5平2负，复次4胜2平2负，同向率62.5%，既有保留题3胜1平4负，尚不稳定。此前45次启动失败作为历史原文保留，不再表示当前环境状态。GPT仅覆盖少量Codex CLI题，型号未确证。

第3阶段将25条X笔记归档为外部经验，10条规则候选全部禁用。C'（运行器名`Cprime`）通过独立[候选文件](docs/candidates/scene-v0.2.0.json)评测，普通客户端仍使用0.1.4文案；只有复次和保留题均稳定胜出才发布。最新真实结果见 [.build/evaluation/stage3-delivery.md](.build/evaluation/stage3-delivery.md)。重建dist不会自动关闭或重启已运行应用。

第4阶段使用独立v0.2.1候选（`Cdoubleprime`），仅向Cprime追加硬前置、固定输出形态、限定词与未知项三条边界；主集、复次、既有保留回放与x07/x03/x04/x06对照见[阶段4交付记录](.build/evaluation/stage4-delivery.md)。正式发布前仍使用现有dist。

第4阶段已完成46次新增真实调用（复用6份A，覆盖52个本轮矩阵格子），全部成功；复次同向率87.5%，但新增工期关键错误未过门禁，未发布v0.2.0，dist仍保持0.1.4。评审为单人、非盲、同模型初评。

第5阶段对三条模型规则做单条增量验证，新增40次、40成功，另复用8条旧基线。E/Cdoubleprime方案4-2-2、格式2-5-1、数字0-8-0，型号标签全部匹配；前两条有质量败，数字不足两胜，均未通过原证据门禁，继续disabled。未发布0.2.0、未重建dist，Cdoubleprime仍为候选。逐题和命令见[阶段5报告](.build/evaluation/stage5-report.md)与[交付记录](.build/evaluation/stage5-delivery.md)。

第7阶段将盲评接入正式通道：两个评委C''/A主集均17胜5平5负、顺序一致23/27；既有holdout均4胜2平2负、一致6/8。原工期争议经独立结构化复核未触发新增关键错误，全量35对双顺序错误核验无新增，正式场景文案升0.2.0。模型规则旧版盲评未达标，阶段6收窄版未完整验收，均禁用；不以人工初评分数发布新规则。详见[协议对账](docs/evaluation-protocol.md)、[阶段7报告](.build/evaluation/stage7-report.md)和[交付记录](.build/evaluation/stage7-delivery.md)。

第8阶段增加独立harness候选评测通道，普通生成器行为不变。44次新增调用中28份答题全部成功，16个双顺序联合盲评批次9有效/7失败；bitto-readonly有效子集净胜但证据缺失，workbuddy-workspace有效子集回退。两条均disabled、dist保持0.2.0，未发布0.2.1。固定材料测试未覆盖真实工作区落盘，不能据此否定harness适配能力。详见[第8阶段报告](.build/evaluation/stage8-report.md)与[交付记录](.build/evaluation/stage8-delivery.md)。

第9阶段只补评委，未重生成答题。新增14次评委调用，失败/部分成功0次、重试0次；原36个有效有序评审保持，完整结果见[阶段9报告](.build/evaluation/stage9-report.md)与[交付](.build/evaluation/stage9-delivery.md)。两条harness仍未过净胜/顺序一致门禁，disabled，dist0.2.0不动。下一轮微仓库/真实权限实验只做预注册，未执行。
