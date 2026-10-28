# Raincoat 发布流程

## 验收顺序

1. 完成独立安装、依赖、输入输出和外部副作用说明；整理必须随包携带的业务契约。
2. 同步目录、`name`、可选清单与 UI 元数据；改名时说明旧安装迁移方式。
3. 明确许可证及第三方材料范围，使用合成或允许公开的示例。
4. 运行结构及发布检查，执行真实任务，记录各宿主与系统实测结果；未实测保留为限制。
5. 导出到仓库外的空目录，在独立环境复验，再更新 [作品目录](../../skills/README.md)。
6. 核对目标仓库、分支与产物后才提交、推送或发布。导出不等于已发布，结构通过不等于全部验收通过。

```bash
python -m pip install -r tooling/requirements.txt
python tooling/scripts/skill_tools.py lint raincoat-meeting-summary --release
python tooling/scripts/skill_tools.py export raincoat-meeting-summary /path/outside/repository/raincoat-meeting-summary
python -m unittest discover -s tooling/tests -p 'test_*.py'
```

在只有 `python3` 命令的系统替换上述 `python`。旧 Bash 入口继续支持；Windows 可直接运行 Python 入口，不依赖 Bash、Perl 或 WSL。

## 工具检查范围

`lint` 默认扫描整个 `skills/`，不强制旧名称加前缀，检查通用格式及名称一致性；现有问题会返回非零状态，不隐藏存量债务。可以传入一个或多个目录名缩小范围。

`--release` 额外要求 `raincoat-` 前缀、README、随包许可证、语义化版本、无遗留模板标记、Markdown 中无作者机器路径、相对文件链接有效且不越出包边界；可选 JSON 清单的名称与版本须一致。这是静态检查，不自动验收兼容性、许可证权属、代码里的隐含依赖或 Agent 的实际输出。

## 导出规则

导出默认执行发布检查，并对过滤后的包再次检查。`--draft` 只执行基础格式检查，供开发迁移使用，不能当作正式发布验收。

导出仅纳入以下根文件与目录：

- `SKILL.md`、`README.md`、`LICENSE` / `LICENSE.md` / `LICENSE.txt`、`.gitignore`。
- 可选 `skill.json`、`plugin.json`、`requirements.txt`、`pyproject.toml`、`package.json`、`package-lock.json`、`uv.lock`、`config.example.yaml`、`.env.example`。
- `scripts/`、`references/`、`assets/`、`examples/`、`agents/`、`tests/`。

排除输入输出目录、依赖目录、缓存、环境文件（保留 `.env.example`）、表格、CSV、媒体与数据库，并列出排除项；如作品确实依赖这些格式的合法资源，先扩展打包规则及测试，不把它们偷偷放入运行包。拒绝进入交付包的符号链接；已排除的本地输入/输出目录中的链接既不跟随也不打包。不覆盖非空目的地，不允许导出回本仓库。保留原有 `.gitignore` 并补充本地产物规则。

目录白名单不能识别允许目录中所有可能的凭证或业务内容，发布前仍需审阅实际包。HTML 只从允许的资源与示例目录携带，根目录临时报告不导出。

## Git 操作

当前仓库远端使用 SSH，避免本地 HTTPS credential helper 问题。操作前用 `git status` 与 `git worktree list` 核对现场，不清理其他任务文件。推送须等待 Git 明确成功，必要时查询远端分支；不要把已发出命令当成成功。独立仓库如需导出，仍由本仓库维护源文件，另行维护时应明确新的唯一真源，避免两边漂移。
