# 剩余迁移验收记录

日期：2026-10-29。执行分支：`codex/raincoat-directory-migration`。依据 [已确认计划](remaining-migration.md) 实施；本轮只做本地提交，不推送或发布。

## 名称与安装迁移

| 旧目录 | 当前目录 |
| --- | --- |
| create-report | [raincoat-create-report](../../skills/raincoat-create-report/README.md) |
| trade-weekly-report | [raincoat-trade-weekly-report](../../skills/raincoat-trade-weekly-report/README.md) |
| report-circle-weekly | [raincoat-report-circle-weekly](../../skills/raincoat-report-circle-weekly/README.md) |
| report-circle-daily | [raincoat-report-circle-daily](../../skills/raincoat-report-circle-daily/README.md) |
| gongfang-weekly-report | [raincoat-gongfang-weekly-report](../../skills/raincoat-gongfang-weekly-report/README.md) |
| circle-content-analyzer | [raincoat-circle-content-analyzer](../../skills/raincoat-circle-content-analyzer/README.md) |
| wxurl2md | [raincoat-wxurl2md](../../skills/raincoat-wxurl2md/README.md) |
| skill-health | [raincoat-skill-health](../../skills/raincoat-skill-health/README.md) |
| skill-quality-review | [raincoat-skill-quality-review](../../skills/raincoat-skill-quality-review/README.md) |

目录、SKILL name、已有清单、当前文档与测试调用方同步。脚本名包含旧作品名时也同步：报告脚手架 Bash 为 `raincoat-create-report-skill.sh`，健康 CLI 为 `raincoat-skill-health` / `raincoat-skill-health.py`。健康状态目录仍是 `~/.skill-health`，避免丢失用户本地状态；新报告文件名使用 raincoat 前缀，旧报告文件不会被自动删除。

用户已有安装未自动更改。更新时先备份自己的配置，按宿主方式移除旧安装，再安装新目录；同步自己的脚本调用路径，避免新旧入口同时触发。无第二份旧名 Skill 入口。开发中 `rain-badminton-cut`、football 应用及其他 worktree 保留原状。

## 独立性与必要修复

- create-report：新增 Python 3.10+ 标准库生成器，包内模板与本地向导随包携带；默认输出 cwd/skills，可指定 --output-root；拒绝已有目标，临时构建失败不留下半包。保留 Bash 包装与四个位置参数、等级与 evidence 选项；输出位置不再隐式指向 Raincoat。L0 明确只有文档，L1/L2 只标记证据已提供，不把文件存在当作验收真实通过。
- 报告合同：各报告所需业务需求与 normalized spec 归 references；交易当前与历史生成器合同保持分离，原 normalized-spec 未被另一合同覆盖。作者路径修复，日报补依赖清单。
- health：本地扫描不要求 Hermes；usage 只消费宿主显式日志，缺日志报告 log_path_missing，重复导入事件不重复计数；无网络或宿主配置修改。
- quality-review：明确 skill-creator 为评审标准依赖，宿主格式按实际目标判断。circle-content-analyzer 保留协议草案，不补造运行时。
- 导出器增加 skill-manifest.yaml 允许文件及回归；向导从不被导出的 tools 移到 assets。草案导出同样检查过滤后的本地链接和资源；正式导出仍受许可等发布检查约束。

## 实际检查

| 检查 | 结果 |
| --- | --- |
| 全仓基础 lint | 11 个 Skill 通过，包括保留原名的开发中 Skill |
| meeting-summary 发布 lint | 通过；Luna 独立任务证据已归包内 references/validation.md，保持 beta |
| skill-creator quick_validate | 九个迁移包与会议纪要共 10 个独立导出包通过 |
| 仓库外独立包 | 10 包导出与本地 Markdown 引用检查通过；9 个存量使用 --draft，未宣称正式可发布 |
| toolkit unittest | 11 项通过，含 manifest 携带及私有输入过滤 |
| create-report unittest | 2 项通过，验证生成清单计数、L0 拒绝执行、拒绝覆盖、无证据拒绝 L1，以及校验器拒绝缺图缺指标 |
| trade unittest | 3 项通过，当前六文件与历史合同已知数值回归 |
| wxurl2md unittest | 5 项通过，离线参数、Python 配置、归档与批处理失败 |
| health unittest | 2 项通过，无日志不造事件、显式日志去重；原 shell 行为套件通过 |
| gongfang unittest | 1 项通过，六文件周粒度合成输入，GMV 1000→3000、+200%、10% 转化率、16 图与 8 表 |
| daily / circle-weekly | 两份合成输入 shell 回归在独立包布局运行通过；移除日报测试向真实目录复制报告的副作用 |
| clipper | 三个 Node 离线 verify 脚本通过，未改权限或运行时 |
| 差异与保护 | git diff --check 通过；50 个受保护文件哈希保持一致；暂存范围单独审阅 |

工房原测试仍为旧四文件日粒度合同，现替换为当前六文件周粒度夹具，生成器算法未改。移除 health shell 测试对 README 标题/文案的逐字断言，保留实际扫描、日志、报告和状态行为检查。

## 本地数据

此前 17 个旧周报文件及 9 个表格/缓存的归档继续保留。9 个保留在磁盘的原件随作品目录迁移，哈希保持一致；Git 不跟踪这些输入和缓存。

审阅额外发现四份已跟踪的日报/周报 HTML 和 run.log，已复制到用户选定归档根目录 `/Users/raincai/Documents/raincoat-local-archive/2026-10-28`，保留当前相对目录，逐一 SHA-256 核验；本地原件保留并由忽略规则覆盖，不再随迁移提交。归档清单 report-artifacts-manifest.json 与此前清单均保留。没有改写 Git 历史。

## 发布与兼容性边界

九个存量包统一 draft，许可来源仍未确认，没有自动新增 LICENSE；保留既有版本，不提升 stable。会议纪要单独有 MIT，仍是 beta。第三方图表资源的权属与图表交互仍需正式发布前检查。

本次独立测试是在 macOS/Python/Node 环境中完成；Windows、跨宿主原生安装与自动发现、Bitto 集成、真实企微登录抓取、插件重新安装与目录授权未实测。不修改用户已安装副本或真实账号。静态结构、草案导出和合成测试通过不等于这些集成完成。

本轮迁移实施与本地验证完成；以上未实测或许可项保留为作品发布条件，不作为迁移已实现能力。执行用临时包与日志清理，必要本地归档清单保留。
