# Raincoat 一级目录迁移计划

日期：2026-10-28。状态：目录归位与旧业务数据归档已完成；浏览器与 Windows 等实测边界见验收记录。详见 [执行与验收记录](root-directory-migration-validation.md)。

本计划承接 [作品规范](../skills/conventions.md) 与 [体检记录](../skills/migration.md)，只解决一级目录归属、依赖归位及相关验证。全量 Skill 改名、Windows/其他 Agent 的完整适配与公开发布仍按作品逐项验收，不因目录整理自动视为完成。

## 目标与边界

将受版本管理的主要内容收敛为四个一级目录：

```text
raincoat/
├── README.md                      # 品牌与作品总入口
├── AGENTS.md                      # 唯一仓库协作规则
├── .gitignore
├── skills/                        # 可独立安装的 Agent Skills
│   ├── README.md                  # 仅列 Skills
│   ├── _templates/
│   └── <skill-name>/
├── apps/                          # 独立应用、CLI、浏览器插件
│   ├── football-ai-studio/
│   └── raincoat-wecom-clipper/
├── tooling/                       # 仓库维护、生成、校验与导出
└── docs/                          # 仓库级规范、决策与跨作品迁移计划
    ├── skills/
    └── plans/
```

`CLAUDE.md` 已按用户要求删除，不恢复兼容入口。产品文档归所属作品；根 docs 只保留跨作品内容及有价值的历史设计。`decisions/` 仅在确有架构决策时创建。

本地 `.git/`、虚拟环境、依赖、worktree 与 Agent 状态不属于对外作品结构，不为整理目录删除正在使用的环境。保留有用的共享 `.claude/` 配置，本地配置保持忽略；不把它扩展为另一份协作规范。

## 阶段 0：文档与依赖发现（本次已完成只读调查）

实施前再次读取以下真源，不依赖计划中的旧快照：

| 依据 | 已确认事实 | 对实施顺序的约束 |
| --- | --- | --- |
| [AGENTS.md](../../AGENTS.md) | 当前存在其他任务的未提交修改，尤其应用与羽毛球 Skill | 不清理、覆盖、切换分支或混入无关提交 |
| [根任务记录](../../apps/football-ai-studio/docs/history/p0/task_plan.md) | task_plan、progress、findings 属于 Football AI Studio P0 | 归入应用历史，保留日期和原验证范围 |
| [插件安装说明](../../apps/raincoat-wecom-clipper/README.md)、[manifest](../../apps/raincoat-wecom-clipper/manifest.json) | 是可独立加载的 Chrome MV3 插件，具备本地 verify 脚本 | 迁入 apps，更新安装说明并验证清单资源 |
| [抓取脚本](../../skills/raincoat-wxurl2md/scripts/wecom_capture_opendoc.js)、[归档脚本](../../skills/raincoat-wxurl2md/scripts/wecom_archive.py) | JS 依赖 Playwright，通过自身目录寻找 Python 归档脚本 | 两脚本作为一个依赖单元迁移 |
| [wxurl2md 包装器](../../skills/raincoat-wxurl2md/scripts/run-wecom-doc.sh) | 写死 tools 下作者路径，并使用 osascript | 先闭合调用与依赖，再撤销根 npm 依赖 |
| [交易周报测试](../../tooling/tests/trade-weekly-report.sh) | INPUT_DIR 直接指向 docs/周报生成器_v3/docs | 替代测试数据先通过，再拆解旧目录 |
| [报表脚手架说明](../skills/report-creator/history/reports-scaffold.md)、[设计稿](../skills/report-creator/history/reports-system-design.md) | tools/reports 目前只有说明，没有已实现注册平台 | 整理为历史设计，不能描述为已运行服务 |
| [打包工具](../../tooling/scripts/skill_tools.py) | 支持 Skill 内 package.json；过滤表格、CSV 与运行产物 | 合成测试数据优先由脚本生成到临时目录，不能因过滤丢资源 |

本任务使用现有 Python、Node、Git 文件操作与项目验证入口，不引入新平台 API。具体命令见各阶段；需要修改浏览器交互时先读当前实现，不凭空假设宿主能力。

## 迁移映射

| 当前路径 | 目标路径或处置 | 所属阶段 |
| --- | --- | --- |
| task_plan.md / progress.md / findings.md | apps/football-ai-studio/docs/history/p0/ 下保留原文件名 | 1 |
| tools/wecom-obsidian-clipper/ | apps/raincoat-wecom-clipper/ | 2 |
| tools/wecom_capture_opendoc.js | skills/wxurl2md/scripts/wecom_capture_opendoc.js | 3 |
| tools/wecom_archive.py | skills/wxurl2md/scripts/wecom_archive.py | 3 |
| 根 package.json / package-lock.json | 依赖审计后迁入 skills/wxurl2md/，或合并必要依赖 | 3 |
| docs/周报生成器_v3/ 的运行代码与模板 | 与 skills/trade-weekly-report/ 逐文件比对，必要差异纳入该 Skill | 4 |
| 旧周报目录的输入、备份与生成报告 | 保存在仓库外指定的本地归档位置，核验后才移出 Git 跟踪 | 4 |
| tools/reports/README.md + docs/tools/ 的报表设计 | docs/skills/report-creator/history/，明确“历史设计、未实现” | 4 |
| bilibili-vipshop/ | 当前仅有 .DS_Store，无作品；不纳入版本管理，可在确认无新增内容后清理空壳 | 5 |
| tools/ / docs/tools/ | 所有文件完成归位、引用核验后撤销空目录 | 5 |

wxurl2md、trade-weekly-report 的名称暂不因归位自动更改，避免把目录重组与跨平台适配混成一个无法定位问题的大改动。后续品牌改名沿用体检记录。开发中的 football-ai-studio 与 rain-badminton-cut 同样不在本轮整体改名。

## 阶段 1：归位任务记录与确定迁移基线

**输入资料**：根 AGENTS、三个根任务记录，以及应用 docs/validation.md。

**实施**：

1. 重新记录 git status 与 worktree，辨别本任务文件和其他任务修改。按阶段建立文件清单；提交时仅包含已核对的本阶段文件，不使用全仓 git add。
2. 将三个任务记录移至应用 docs/history/p0/，保留原文与日期，不覆盖现有 docs/plans/、validation.md 或其他活动记录。
3. 给历史记录补一个简短索引，说明记录仅对应当时 P0，后续实现以应用当前文档为准；修正移动导致的相对引用。

**验收**：根部不再有三个任务记录；历史内容可追溯；当前应用文档没有被覆盖；引用有效；git diff --check 通过。纯文档归位不要求重跑应用完整测试。

**回退**：按本阶段源目标清单将文件移回，同步恢复本阶段引用；不回滚其他人的文件。

## 阶段 2：浏览器插件成为独立作品

**输入资料**：插件 README、manifest、三个 verify 脚本与其资源引用。特别读取 verify-richtext-regression.js 的样本格式：它当前默认依赖 /tmp 下的外部 JSON，不能直接作为干净副本验收命令。

**实施**：

1. 将完整目录迁到 apps/raincoat-wecom-clipper/，保留脚本、图标、测试与现有权限。
2. 将 README、清单显示名称及作品入口统一到 raincoat-wecom-clipper；不因搬迁扩大权限或改写功能。
3. 根 README 展示该作品，skills/README 移除插件条目；更新安装路径、目录说明和需要的 AGENTS 结构描述。
4. 按现有富文本解析器的真实输入格式补合成 JSON fixture，给富文本回归脚本显式传参；不复制真实企微文档内容作为公开测试样本。
5. 说明目录变化要求重新“加载已解压的扩展程序”；授权的 vault 状态是否随加载路径变化保留须实际验证，不能承诺自动迁移。

**验收**：在新目录运行 `node verify-clipboard-markdown.js`、`node verify-richtext-regression.js tests/fixtures/synthetic-opendoc.json`（fixture 为本阶段新增，需符合现有解析器格式）、`node verify-vault-writer.js`；manifest 所引用资源均存在；静态检查与差异检查通过。能使用浏览器时验证加载、复制文本到 Markdown 和向临时目录写文件；仅有脚本通过时将浏览器安装复验列为未完成，不写成已通过。

**回退**：目录及本阶段名称/引用一起恢复；不删除或重置浏览器 Profile 与用户授权目录。

## 阶段 3：wxurl2md 闭合自身依赖，撤销根 npm 依赖

**输入资料**：两份 tools 脚本、wxurl2md 的 SKILL、runbook、包装器及根依赖清单。

**实施**：

1. 将抓取与归档脚本一起归入 Skill scripts，保留 JS 通过自身目录定位 Python 的关系；相对资源定位不依赖 cwd。
2. 为 Skill 增加自己的 package.json 与锁文件，保留现有依赖约束与锁文件解析结果；明确当前实现使用的 Chrome channel 及其安装前提，不把安装 Playwright 包等同于浏览器已经可用；审计根依赖是否还有其他调用者，确认后再撤销根清单。不要为目录搬迁顺带升级依赖。
3. 把作者绝对路径改为脚本相对定位。Python 解释器、输出目录与浏览器 Profile 的默认值改为可配置、平台合适的位置；延续现有环境变量覆盖方式并说明用途。
4. 文档优先给出直接 Node/Python 入口。包装器保留现有调用方式；对 osascript 标明 macOS 限制或添加条件处理，其他系统不能无提示执行失败。
5. 增加离线测试：CLI 参数、归档输入转换、JS 调用 Python 路径、不从根 node_modules 获得隐式依赖。使用合成输入或本地 fixture，不访问真实企微文档。
6. 在仓库外导出目录安装声明的依赖复验；如打包器与实际必需文件冲突，先补对应规则和测试，不绕过静态检查。

**验收**：离线转换结果与关键数据保持一致；Skill 所需实现与依赖不再跨出包；无作者路径和 tools 调用；从非仓库 cwd 可启动。真实登录态抓取仅在已有任务授权和可用环境内验证；Windows 无实测时保留限制，不把原生入口等同实测通过。

**回退**：脚本、依赖清单和调用路径作为一个单元恢复；不改写用户登录态、Profile 或业务输出文件。

## 阶段 4：拆解旧周报目录与归档报表设计

**输入资料**：旧周报 README、Python/JS 实现、trade-weekly-report 的入口、合同与现有测试；tools/reports 和 docs/tools 的设计稿。

**实施顺序**：

1. 比对旧生成器与当前 Skill 的实际差异，逐项记录有用能力、仍被调用的资源和可弃用的重复实现。不能仅凭名称判断旧版没有用途。只读核对已确认两处 generate_report.py、app.js 均非相同字节，且入口参数不同；Skill 生成器导入 numpy 而其依赖清单未显式列出，也需在独立安装验收中核对。
2. 在 Skill tests 中增加合成数据生成器，覆盖当前必需字段及关键计算；数据写临时目录。更新 tooling/tests/trade-weekly-report.sh 只使用合成输入，增加至少一个可检验数值结论，避免只检查标题。
3. 对现有脚本的固定 assets 路径做必要修正，再运行新旧入口的定向回归；差异必须说明，不能用移动目录掩盖原有实现错误。
4. 新测试独立通过后，将必要代码、模板与业务契约归入 Skill。仅有研究价值的旧说明放进对应 history，标注原路径与被谁取代；历史叙述中的旧路径可保留但不能作为运行命令。
5. 列出真实输入、备份、生成报告和已跟踪缓存。逐文件记录目标、大小和哈希；确认仓库外归档位置后复制并核验，才从 Git 跟踪中移除，避免误删唯一副本。公开示例使用合成数据，不把业务表格改名为 fixture 继续提交。
6. 将未实现的报表平台设计集中到 docs/skills/report-creator/history/，纠正 README 中暗示平台已实现的描述，更新相关引用。

**验收**：交易周报测试不再依赖 docs 中真实输入；必需运行代码全部在 Skill 内；所有原文件都有归位/保留/移出记录；本地数据已核验保留；docs 无运行代码、用户输入和生成报告；原目录引用只剩明确历史出处。

**回退**：代码与测试按阶段清单移回。数据从已验证的本地归档恢复，不通过 Git 历史重写恢复，也不清理归档副本。

**归档结果**：17 个旧周报文件已复制至用户确定的 `/Users/raincai/Documents/raincoat-local-archive/2026-10-28`，逐文件核对大小和 SHA-256 后移除仓库内原件，旧目录已清空。清单保存在归档根目录与本地忽略的 `.migration/`；未改写 Git 历史。

## 阶段 5：收敛根目录与最终验证

**实施**：

1. tools 中所有实现与文档有接收位置后再撤销该目录；不强行删除仍有调用者的文件。bilibili-vipshop 重新检查无新增作品后处理。
2. 更新根 README、skills 目录、AGENTS、发布流程与迁移记录。AGENTS 描述实际生效结构，不提前把本计划目标写成现状。
3. 复查 ignore：本地依赖、虚拟环境、Agent 本地配置、输出、缓存与浏览器 Profile 保持忽略，公开示例配置仍可跟踪；不提交本机环境。
4. 重查根 npm 依赖是否已撤销或有书面保留理由。没有真实共享调用时，不新建 packages、plugins 或第二套 tools。

**最终验收**：

- 受版本管理的内容以 skills、apps、tooling、docs 为四个核心目录；无需删除本地环境才能满足该目标。
- 从干净副本按文档运行插件本地测试、企微离线测试、交易周报合成测试以及 `python3 -m unittest discover -s tooling/tests -p 'test_*.py'`。
- `python3 tooling/scripts/skill_tools.py lint raincoat-meeting-summary --release` 通过；全仓 lint 的已知失败逐项记录，新增失败必须处理，不能将原有三项问题计作本次全部通过。
- 检查活跃代码、测试和使用说明中没有 tools/wecom、旧插件路径和旧周报数据目录的运行依赖；历史来源和本迁移计划中的旧路径不要求机械清零；旧来源如变更位置，更新可点击链接到承接文件，原路径用文本保留。
- 验证相对链接、manifest 文件引用和独立安装；git diff --check 通过。
- 最终报告列出已迁移路径、测试结果、未验证系统与仍阻塞发布的事项；目录整理完成不等于正式发布。

**回退**：按各阶段记录反向恢复，若本任务已形成独立提交则可定向撤销该提交；不能 reset、clean 或批量覆盖共享工作区。

## 执行节奏与交付

顺序为 `1 → 2 → 3 → 4 → 5`；每阶段验收通过再推进。预计阶段 4 工作量最高，因为包含数据替代与重复实现核对，不按文件移动次数估计完成度。

实施时按阶段记录“待开始 / 进行中 / 已验证 / 受阻”及实际结果。每阶段适合作为一个独立审阅批次；本轮提交范围仅含迁移相关文件，不推送；独立阶段的实际结果见执行记录。

实施状态：阶段 1 完成；阶段 2 完成代码归位与离线验证，浏览器重新安装未实测；阶段 3 完成离线独立安装及导出验证，真实抓取未实测；阶段 4 已完成代码、测试、设计文档归位及数据归档；阶段 5 已完成入口、规则和旧数据目录清理。

2026-10-29 后续名称与独立性迁移已完成，当前入口及实测边界以 [剩余迁移验收](remaining-migration-validation.md) 为准；上文保留实施当时记录。
