# 一级目录迁移执行与验收记录

日期：2026-10-28。分支：`codex/raincoat-directory-migration`。基于迁移前已有工作区继续，迁移相关文件单独形成提交检查点，不推送或发布；应用与羽毛球 Skill 的其他任务修改保留。本文记录实际结果，不替代 [原计划](root-directory-migration.md) 或各作品的使用说明。

## 已完成的归位

| 原位置 | 当前位置 | 结果 |
| --- | --- | --- |
| 根 task_plan / progress / findings | apps/football-ai-studio/docs/history/p0/ | 已归位并增加历史索引，不改变当前应用实现 |
| tools/wecom-obsidian-clipper | apps/raincoat-wecom-clipper | 已归位；名称及安装说明更新，运行时代码与权限保持一致 |
| tools 中两份企微脚本、根 npm 清单 | skills/wxurl2md/scripts/ 及 Skill 根目录 | 已归位；保留锁文件版本及 integrity，声明 Chrome 与 Python 依赖 |
| docs/周报生成器_v3 的生成器、app.js 和使用说明 | skills/trade-weekly-report/scripts/legacy/ | 生成器与 app.js 原字节保留；不同合同不互相覆盖 |
| tools/reports 与 docs/tools 的设计稿 | docs/skills/report-creator/history/ | 已归档并标明未实现平台能力 |

根 README 展示应用与插件，skills/README 仅列 Skill；AGENTS 更新实际目录边界。CLAUDE.md 保持删除。根 npm 清单不再存在；根 node_modules、虚拟环境、worktree 与其他本地状态未删除。tools 可能仅余本地忽略的 .DS_Store；它不再承载受版本管理的实现。

## 必要实现修正

- wxurl2md：用脚本自身位置解析归档器，浏览器 Profile 使用可配置的专用目录，输出默认系统临时目录；Python 解释器可指定。命令帮助及参数检查不需启动浏览器。可选 Bash 包装器不再调用 AppleScript，批次内有失败返回非零。
- 插件富文本验证：用随包合成 fixture 代替 /tmp 下真实文档，检查顺序、金额、百分比、负责人和噪声过滤。未为测试改动解析器。
- trade-weekly-report：修复作者 assets 路径，将原先安装副本中实际使用的 base-report.css、chart-defaults.js 纳入 Skill；补 numpy 显式依赖。CSS 保留原安装版本，JS 与仓库已有设计系统相同，不改变其样式定义。默认入口增加 Python 参数校验，保留 Bash 与旧位置参数，不自动联网安装。
- 周报测试：旧 shell 测试的参数与实际入口原本不一致，且依赖旧 docs 的业务数据。现在临时生成六份合成 Excel；历史入口另生成 CSV 验证，不依赖私有输入。
- 打包器：忽略输入/输出树中的本地链接，不跟随或读取目标；真正进入包的链接仍拒绝。新增对应回归，避免本地输出中的输入链接阻断合法导出。

## 实际验证

| 检查 | 结果与范围 |
| --- | --- |
| 插件 3 个 Node verify 脚本 | 通过；合成富文本、剪贴板转换和 vault helper |
| 插件清单与原版本比对 | 资源引用存在，权限未增加，非测试运行时代码逐字节一致 |
| tooling unittest | 11 项通过，包含排除运行产物链接的新回归 |
| wxurl2md unittest | 5 项通过，覆盖 CLI、Python 配置、离线归档、原文/数字保持与批次失败 |
| wxurl2md 独立安装 | 仓库外临时副本，锁定 tarball 来自本机已有 npm 缓存，临时缓存执行 npm ci --offline --ignore-scripts；3 个包安装完成，Playwright 解析位置在临时包内，5 项测试通过 |
| trade-weekly-report unittest | 3 项通过：缺文件失败、默认六文件合同和旧四文件合同；小店 GMV 均为 15000→30000，默认输出环比 +100% |
| 两个 Skill 的过滤后导出 | 使用 --draft 导出至仓库外，分别运行自身 5 项与 3 项测试通过；这是草案包验证，不是正式发布许可 |
| 定向 lint | raincoat-meeting-summary、trade-weekly-report、wxurl2md 通过基础检查；会议纪要样板发布检查通过 |
| 文档与差异检查 | 52 个本地链接有效，git diff --check 通过；迁移验收当时全仓基础检查剩 circle-content-analyzer 的 triggers 和无入口的 skill-panel 两项既有问题；后续处理见下节 |
| 无关改动保护 | 与本轮前哈希记录核对，应用与羽毛球 Skill 的 50 个既有改动文件保持一致 |

真实 Chrome 登录抓取、插件重新安装/目录授权、Windows、跨 Agent 和报告全部图表交互均未实测。Luna 实施子 Agent 因额度限制未启动，后续由主 Agent 执行，未声称完成独立 Agent 审阅。

## 业务数据归档已完成

17 个旧周报文件（表格、备份、Excel 锁文件、生成报告），共 174378549 字节，已归档至用户选定的 `/Users/raincai/Documents/raincoat-local-archive/2026-10-28`，保留原相对目录。获得目录写入授权后先复制，再逐文件比对 SHA-256 与大小；全部通过后才移除仓库内原件。`docs/周报生成器_v3/` 已清空并移除，迁移提交范围包含对应删除；Git 历史未改写。

归档根目录的 `archive-manifest.json` 记录复制核验结果与原位置；仓库内被忽略的 `.migration/legacy-archive-manifest.json` 另记录源文件已移除。归档副本与清单保留，执行用临时脚本已删除。

阶段 4 的数据归档和阶段 5 的目录收敛已完成。本次续做重新核验 17 个归档副本、50 个受保护文件及差异格式；未因数据搬迁重复运行已通过的代码测试。其他 Skill 中仍有 7 个已跟踪业务表格和 2 个 pyc，保留在原位置，属于后续存量治理范围。真实浏览器与 Windows 等未实测项仍如上所列，不影响本轮文件归位结果。

## 后续：基础检查遗留项已修复

`circle-content-analyzer` 移除非标准顶层 `triggers`，保留 description 与正文的触发条件，新增 `metadata.status: draft`；四处旧 worktree 引用及 README 链接改为包内相对路径。入口和 README 明确未随包提供正式运行脚本，不将结构通过描述为报告生成能力已验收。

`skill-panel/` 没有受版本管理的文件，仅有两份本地 pyc。目录已移至被 Git 忽略的 `.migration/local-cache/skill-panel/`，移动前后 SHA-256 一致，本地清单保存在 `.migration/skill-panel-cache-manifest.json`。未更改 lint 的扫描规则，也未补造 Skill 入口。

本次验证：全仓 11 个 Skill 基础 lint 通过；skill-creator quick_validate 检查 circle-content-analyzer 通过；修改文件的本地链接与 git diff --check 通过。未新增运行时代码，不重复迁移代码测试；50 个其他任务文件仍保持原哈希。

## 后续：剩余业务表格与已跟踪缓存

2026-10-29，将 report-circle-weekly 的 7 个 Excel 与 gongfang-weekly-report、report-circle-daily 的 2 个 pyc 复制至此前选定的仓库外归档根目录，保留仓库相对路径。9 个副本均通过大小和 SHA-256 校验，清单为归档根目录 `remaining-data-manifest.json`，本地忽略目录另存同名清单。

仅停止 Git 跟踪，保留磁盘原件；周报 docs 下 Excel 增加定向忽略规则，pyc 使用既有忽略规则。运行代码与输入参数未改动，仓库克隆后由使用者提供私有输入，不分发这些表格。未改写历史。

本次验证：圈子周报合成 CSV 回归生成 HTML 通过；全仓 11 个 Skill 基础 lint 通过；9 个原件与归档副本哈希一致且全部被忽略，Git 索引不再跟踪 XLSX 或 pyc；50 个受保护文件哈希保持一致；工作区与暂存区 diff --check 通过。

2026-10-29 后续名称与独立性迁移已完成，当前入口及实测边界以 [剩余迁移验收](remaining-migration-validation.md) 为准；上文保留实施当时记录。
