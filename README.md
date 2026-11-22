# raincoat

我是 raincoat，一个持续做产品与插件的 builder。这里汇总我的作品，并孵化可独立使用的 Agent Skills、CLI、本地应用和浏览器插件。

优先把可复用工作流做成 Skill；每个新作品与本轮迁移作品使用 `raincoat-xxx` 命名，明确输入输出、依赖与实测兼容范围。

- [作品目录与当前状态](skills/README.md)
- [作品与 Skill 规范](docs/skills/conventions.md)
- [发布与独立导出流程](docs/skills/publishing.md)
- [体检结果与迁移清单](docs/skills/migration.md)
- [一级目录迁移计划](docs/plans/root-directory-migration.md)

## 开始使用

第一个按新规范整理的样板是 [raincoat-meeting-summary](skills/raincoat-meeting-summary/README.md)：把会议文本整理为结论、行动项与关键决策。无脚本或账号依赖；其他 Agent 和 Windows 的实测状态见它的 README。

存量作品仍处于孵化与迁移阶段，各自的说明和限制以对应目录为准。

## 本地 Agent 入口

[Buck（raincoat-buck）](apps/raincoat-buck/README.md) 是一个本地 MCP 服务：调用方只面对它一个，由它把任务派给本机已装的 Bitto、WorkBuddy、Codex CLI 或 Antigravity CLI。安装、客户端注册和各后端的权限边界见它的 README。

## 开发

需要 Python 3.10+；用系统可用的 `python` 或 `python3`：

```bash
python -m pip install -r tooling/requirements.txt
python tooling/scripts/skill_tools.py new raincoat-my-tool
python tooling/scripts/skill_tools.py lint raincoat-meeting-summary --release
python tooling/scripts/skill_tools.py export raincoat-meeting-summary /path/outside/repository/raincoat-meeting-summary
python -m unittest discover -s tooling/tests -p 'test_*.py'
```

新建命令只生成待填写的最小模板，不自动授予许可证或标记兼容性已验证。完整存量体检使用 `python tooling/scripts/skill_tools.py lint`，会报告尚未迁移的问题。

## 仓库结构

- `skills/`：Skill 与最小模板。
- `apps/`：独立应用与插件，包含 [Buck](apps/raincoat-buck/README.md)（本机 agent 派发 MCP）、[Sport Cut Studio](apps/football-ai-studio/README.md)、[raincoat-kb-desk](apps/raincoat-kb-desk/README.md)、[raincoat-prompt](apps/raincoat-prompt/README.md)、[raincoat-watch-recorder](apps/raincoat-watch-recorder/README.md) 和 [raincoat-wecom-clipper](apps/raincoat-wecom-clipper/README.md)。
- `tooling/`：脚手架、校验、导出与测试。
- `docs/skills/`：约定、发布流程与迁移记录。

许可证按作品指定。目前样板自带 MIT 许可证，不代表其他存量代码、业务资料或第三方资源也采用 MIT。
