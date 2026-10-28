# Raincoat 体检与迁移记录

日期：2026-10-28。范围：当前工作目录，包含尚未提交的其他任务改动；不代表 main 或线上状态。

## 本轮完成

- 建立品牌、命名、独立性、兼容性声明、版本与发布规范；重整首页与作品目录，移除不存在的作品条目。
- `rain-meeting-summary` 迁为 `raincoat-meeting-summary`，入口与专用插件清单同步；附独立 README、MIT 许可证及合成输入/参考输出。仅该作品采用此许可证。
- 最小模板只保留 SKILL 与 README，不再强制目录、skill.json 或空资源。新建强制 raincoat- 前缀。
- Python 3.10+ 工具统一新建、检查、导出，保留原 Bash 命令作可选兼容入口；显式声明 PyYAML 依赖。
- 导出使用允许目录与根文件清单，过滤本地数据与运行产物、拒绝符号链接、保留原忽略规则，并重新检查过滤后的包。旧的失效导出测试改为独立临时样例。
- 补充缓存、Skill 输出与本地 Agent 状态的忽略规则；旧周报目录的 17 个数据与报告文件已在仓库外复制核验后移除原件；其他存量文件保留，未改写 Git 历史。

## 已执行的验证

- `python3 -m unittest discover -s tooling/tests -p 'test_*.py'`：11 项通过，覆盖实际创建、导出与拒绝错误输入等行为。
- `python3 tooling/scripts/skill_tools.py lint raincoat-meeting-summary --release`：通过。
- 当前本机 skill-creator 的 `quick_validate.py` 检查样板：通过。
- 将样板导出到仓库外临时目录，从临时工作目录再次运行 quick_validate：通过；包包含 SKILL、README、LICENSE、plugin.json、两个示例和补充的 .gitignore。临时包已自动清理。
- 当前 Codex/macOS 会话人工逐条复核合成任务：周明确承诺写说明，截止“下周三”保留原文；林明确决定先上线 Markdown；PDF 与上线日期不补全；兼容性检查仍未分派。参考输出保存在样板 examples/summary.md。这不是独立 Agent 盲测或自动发现测试。
- `git diff --check`：通过。

未执行 Windows、其他 Agent、全新安装和插件宿主集成测试；纯文本格式与无系统调用不能代替这些实测。

一级目录调整的具体顺序、文件映射与验收条件见 [一级目录迁移计划](../plans/root-directory-migration.md)。代码与文档归位已实施，详细状态见 [执行与验收记录](../plans/root-directory-migration-validation.md)；下表为本轮更新后的遗留项。

## 存量问题与下一步

| 项目 | 下一步与验收条件 |
| --- | --- |
| 全仓基础检查 | 当前剩 2 个目录报错：circle-content-analyzer 顶层 triggers；skill-panel 无 SKILL.md。trade-weekly-report 的元数据已整理。保留可见失败，不为获得绿灯掩盖存量问题。 |
| tracked 数据 | 旧周报 17 个文件已归档移出工作区；当前仍有 7 个 xlsx 和 2 个 pyc 留在其他 Skill，后续确认表格可公开范围并决定归档或合成替换。忽略规则不会移除已跟踪文件，也不会清除历史。 |
| 许可证 | 其他作品尚未完成权属与第三方资源许可梳理，不能因样板使用 MIT 就认为整个仓库采用 MIT。 |
| wxurl2md | 脚本与 npm 依赖已移入 Skill，已去除作者路径和 AppleScript；离线独立安装与导出测试通过。真实浏览器与 Windows 实测仍待完成。 |
| circle-content-analyzer | 整理 frontmatter、修正旧 worktree 链接；README 说明运行时尚待恢复，不能把协议层当完整工具发布。 |
| trade-weekly-report | 元数据、路径、随包样式和实际输入合同已整理；新旧生成器的合成数据回归通过。业务完整口径、图表交互、许可与品牌改名仍待验收。 |
| report-circle-weekly / daily | 将必要需求与契约纳入 Skill 自身，去掉本机绝对路径；确认业务资料许可，独立导出复验。 |
| skill-health | 明确通用核心与 Hermes usage 接入边界，分别列出实测能力与依赖。 |
| 其他存量 Skill | 补齐适用许可证、输入输出、依赖、独立安装和实际兼容性证据后再改名。 |
| 开发中的应用与羽毛球 Skill | 保留本轮前已有修改，由各自开发任务按新规范完成发布验收。 |

目标名称默认采用 `raincoat-` 加原能力名；现有 `rain-` 前缀替换为 `raincoat-`。不要为命名整齐直接迁移正在开发的目录或用户已安装的副本。改名时需同步代码、文档、清单、测试、安装说明及实际调用入口。

目录迁移在 `codex/raincoat-directory-migration` 上进行。迁移相关文件单独形成提交检查点，不推送、发布、清理其他 worktree 或变更用户本机已安装的 Skill。
