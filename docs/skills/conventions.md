# Raincoat 作品与 Skill 规范

Raincoat 是 builder 的产品与工具品牌；本仓库汇总作品并孵化可独立发布的 Skill、CLI、应用及插件。Skill 是优先交付形式，不要求所有产品都包装成 Skill。

## 命名与结构

- 新作品与迁移完成的对外作品统一使用 `raincoat-xxx`；Skill 名称使用小写字母、数字和单连字符，总长不超过 64 字符，目录名与 frontmatter 的 `name` 一致。
- 存量作品保留旧名直至完成引用、安装入口与依赖迁移；进度记录在 [migration.md](migration.md)。不要仅改目录名就声称完成迁移。
- 一个 `skills/<name>/` 对应一个 Skill。通用格式只要求 `SKILL.md`；Raincoat 公开交付另需 `README.md` 和适用的许可证。
- `scripts/`、`references/`、`assets/`、`examples/`、`tests/` 按真实需要添加，不建空目录。`skill.json`、`plugin.json`、`agents/openai.yaml` 是可选适配或目录文件，已有时须与入口名称、版本一致。

## 格式与编写质量

以 [Agent Skills 格式](https://agentskills.io/specification) 为通用基线，以 `skill-creator` 的准确触发、范围约束和渐进披露原则审阅质量。宿主专用元数据与工具适配分离，不能把某一宿主的工具当作所有 Agent 的内置能力。

`SKILL.md` 的 frontmatter 包含 `name`、`description`；按需使用 `license`、`compatibility`、`metadata`、`allowed-tools`。项目版本、作者与状态放在 `metadata`，值使用字符串。脚手架默认 `draft`，不能据此当作可发布版本。

入口只保留目的、关键约束和工作流；长篇资料放入有明确使用时机的引用文件。输入、输出、失败条件应足够明确；不要用通用口号代替任务说明。

## 独立运行与兼容性

单独下载 Skill 后，按其 README 安装声明的依赖即可运行。不得依赖作者绝对路径、仓库其他目录或未声明的已安装 Skill。文档使用相对链接，脚本从自身位置解析资源。不得隐式下载或执行其他 Skill 来补齐缺失依赖。

正式发布以 Windows 与 macOS 为目标；逐项记录 Agent、系统、运行时版本、实际验证范围和限制。区分已验证、未实测、不支持；注明 Windows 原生支持还是 WSL。核心脚本优先 Python 或 Node.js，Bash 可作可选入口。当前仓库工具要求 Python 3.10+ 和 `tooling/requirements.txt`，可原生调用 Python。

声明网络、浏览器、账号、API、系统软件和宿主权限等依赖。说明是否上传输入、产生服务费用或修改外部数据；整理出行动项不等于授权发送消息或创建待办。

## 发布与验收

版本使用语义化版本，状态使用 `draft`、`beta`、`stable` 或 `archived`。状态描述维护成熟度，兼容性必须另行列出；破坏兼容的变更说明迁移方法。

每个公开作品提供最小使用示例及验收记录。有代码时测试实际行为；纯指令 Skill 至少复核一项真实任务，必要时使用合成输入。结构检查不能证明推理质量或跨平台行为。无实测依据不得在目录中写“全平台支持”。

许可证按作品明确，不自动给存量代码、第三方资源或业务资料套用新许可证。公开示例使用合成或获准公开的数据。具体流程见 [publishing.md](publishing.md)。
