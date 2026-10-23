# Raincoat Agent MCP

把完整任务交给本机 Bitto 或 WorkBuddy，使用对应产品的运行时、模型和登录账号。Codex、DeepSeek Harness 或其他支持 stdio 的 Agent 通过同一个 MCP 的 `backend="bitto" | "workbuddy"` 参数选择后端。

当前版本 **0.1.0**，后端仅支持 **macOS**。Python 包和发行流程已经准备好，**尚未发布到 PyPI**；现在可分发构建后的 `.whl` 文件。Windows/Linux 的运行时发现、认证和进程管理尚未适配，CLI 会给出明确提示。

## 给使用者：首次安装

需要 Python 3.11+、[uv](https://docs.astral.sh/uv/getting-started/installation/)，以及已安装并登录的 Bitto 或 WorkBuddy。使用 WorkBuddy 还需 Node.js **22.19+（22 系列）或 24+** 和 npm；这与固定版本凭证辅助模块的要求一致。

收到发布者提供的 wheel 后安装。以下路径替换为实际下载位置：

```sh
uv tool install --python 3.11 --force /path/to/raincoat_agent_mcp-0.1.0-py3-none-any.whl
local-agent --version
```

`uv` 找不到指定 Python 时可按其提示安装，或指定本机已有的 Python 3.11+。若终端找不到 `local-agent`，先运行 `uv tool update-shell`，再重新打开终端。

PyPI 正式发布后，首次安装可简化为：

```sh
uv tool install --python 3.11 raincoat-agent-mcp
```

这是本地程序：每台设备使用自己的客户端和登录状态，不共享发布者的账号或额度。调用方自身的调度和验收仍会消耗调用方模型额度。

### 准备后端

只使用 Bitto：打开并登录 Bitto，再检查本机运行时。

```sh
local-agent doctor --backend bitto
```

使用 WorkBuddy：打开并登录 WorkBuddy，然后单独安装固定版本的凭证辅助模块。

```sh
local-agent doctor --backend workbuddy --install-deps
```

这条命令通过 npm 将 `dsh-workbuddy-connect@0.7.9` 安装到 `~/.local/share/raincoat-agent-mcp/workbuddy/`，不需要安装 DeepSeek Harness，也不读取或复制其他人的凭证。失败会返回非零退出码和具体原因。未安装 Node/npm 时先安装上述受支持版本，再重试。

之后可随时运行只做本地检查的命令：

```sh
local-agent doctor --backend workbuddy
local-agent doctor                         # 同时检查两个后端
```

Doctor 检查安装、运行时、Node 版本和辅助模块入口，不调用大模型，不验证登录有效性。WorkBuddy 检查成功时会记住本机 Node 路径，避免桌面 Agent 未加载 shell PATH 导致找不到 Node。检查失败返回非零退出码；只启用一个后端时请指定 `--backend`。

### 接入 Agent

预览配置，然后写入：

```sh
# Codex
local-agent setup --client codex
local-agent setup --client codex --apply

# DeepSeek Harness desktop profile
local-agent setup --client deepseek --apply

# 其他 DeepSeek Harness profile
local-agent setup --client deepseek --dsh-profile web --apply

# 自动选择已存在的客户端目录，不创建未安装的 profile
local-agent setup --apply
```

Codex 配置位于 `~/.codex/config.toml`，DeepSeek Harness 配置位于 `~/.dsh/profiles/<profile>/cordis.patch.yml`。写入前保存 `*.before-local-agents-<时间戳>` 备份，替换旧 `bitto` 和 `local_agents` 注册，保留其他服务与设置。重复执行不会增加重复注册。`--client all` 可显式创建两者配置。

其他 MCP 客户端使用生成的标准 JSON；其中解释器路径来自实际安装环境，不需要手写开发机路径：

```sh
local-agent setup --client generic
local-agent setup --client generic --output ./mcp.json --apply
```

配置使用安装环境中的固定 Python 路径和 `-m raincoat_agent_mcp mcp`。后续升级不依赖源码目录，也不用修改客户端启动配置。

**配置写入后，重载 MCP 或重启对应 Agent。** 加载后可看到 `agent_submit_task`、`agent_wait_task` 等工具。

## 更新与回退

更新前完成或取消仍在执行、等待授权的任务。`update` 会检查原任务目录，有活跃任务时拒绝更新；它不会在 MCP 调用过程中自动安装新版本。

尚未发布到 PyPI，或通过文件分发时，下载新 wheel 后只需：

```sh
local-agent update --from /path/to/raincoat_agent_mcp-0.1.1-py3-none-any.whl
```

PyPI 发布后的常规用法：

```sh
local-agent update --check       # 查询 PyPI 的最新版本，不修改安装
local-agent update              # 使用 uv 重新安装最新公开包
```

`--check` 查询 `https://pypi.org/pypi/raincoat-agent-mcp/json`；尚未发布、网络不可用时会明确报错，现有 MCP 仍可使用。常规更新使用 uv 的索引配置；使用私有索引的维护者应通过 uv 配置来源，PyPI 版本检查不代表私有索引版本。

`update` 仅支持 `uv tool` 管理的安装，底层使用 `uv tool install --force` 并保留现有 Python 解释器，避免首次 wheel 或指定版本安装把后续更新一直固定在旧来源。更新失败不会报告成功；可用原 wheel 重新安装，因此请保留至少上一版发行文件。

更新完成后，再重载 MCP。更新 CLI 本身不会让已运行的 Agent 自动重连。

回退有两种方式：

```sh
# 文件分发：使用自己保留的上一版 wheel，可在依赖已缓存时离线重装
local-agent update --from /path/to/raincoat_agent_mcp-0.1.0-py3-none-any.whl

# 公开索引上已经存在该版本时
local-agent update --version 0.1.0
```

任务记录、登录状态和客户端配置不随包升级删除。配置若需要单独回退，恢复对应的 `before-local-agents` 备份，再重载客户端。

### 从此前的源码安装迁移

```sh
uv tool install --force /path/to/raincoat_agent_mcp-0.1.0-py3-none-any.whl
local-agent doctor --backend workbuddy --install-deps  # 仅使用 WorkBuddy 时需要
local-agent setup --apply
```

旧安装留下的 `~/.local/bin/bitto-agent` 可暂时保留。新配置只注册一个 `local_agents` 服务器；其中保留五个旧 Bitto MCP 工具名。旧任务目录默认仍是 `~/.local/state/bitto-agent-bridge`，已有 `job_id` 可以继续读取。

源码 checkout 中的 `python3 install.py --apply` 是兼容入口，会先用 uv 安装本地包，再配置已发现的客户端；它不再复制源码到旧 release 目录。

## MCP 用法与完成等待

```json
{
  "backend": "workbuddy",
  "prompt": "计算并校验指定文件中的结果",
  "cwd": "/absolute/workspace",
  "allowed_tools": ["Bash(python3:*)"]
}
```

调用 `agent_submit_task` 时传入这些参数。工具权限需要按用户对任务的授权显式给出，空列表不开放工具，不会自动使用跳过权限模式。

| 工具 | 用途 |
|---|---|
| `agent_status(backend)` | 本地发现检查，不调用模型 |
| `agent_submit_task(backend, prompt, ...)` | 提交并默认等待最多 25 秒 |
| `agent_wait_task(job_id, timeout_seconds=25)` | 完成或需要授权时立即返回 |
| `agent_get_task(job_id, include_details=false)` | 立即读取状态快照 |
| `agent_cancel_task(job_id)` | 请求取消，需再等待终止确认 |
| `agent_respond_permission(job_id, request_id, allow)` | 回答 Bitto 当前工具授权 |

提交还支持 `title, project, model, cwd, session_id, timeout_seconds, wait_seconds, allowed_tools`。提交的执行上限 `timeout_seconds` 范围 1–86400 秒；`wait_seconds` 和等待工具的 `timeout_seconds` 范围 0–50 秒。单次等待超时不会取消任务。

未完成时立即继续调用 `agent_wait_task`，不要 sleep 或指数退避。worker 在保存终态后通过私有 Unix socket 唤醒等待者；默认只返回最终文本和少量工具摘要，完整状态见 `result_path`，也可用 `include_details=true` 读取。

MCP 无法在工具调用已结束后主动唤醒闲置模型，需要调用方保持有界等待。此前真实执行中，收到后端终态到返回结果约 2 ms；这不包含模型执行和调用方组织回复的时间，也不是任意负载下的保证。

旧工具名 `bitto_status`、`bitto_submit_task`、`bitto_get_task`、`bitto_cancel_task`、`bitto_respond_permission` 在同一个服务器内继续提供。

CLI 也支持任务执行：

```sh
local-agent status bitto
local-agent submit bitto '执行任务并返回结果'
local-agent submit workbuddy '执行已授权的任务' --allowed-tool 'Bash(python3:*)'
local-agent wait JOB_ID
local-agent get JOB_ID
local-agent cancel JOB_ID
```

## 后端与数据边界

Bitto 连接本机 sidecar，任务在桌面端可见；`project` 默认 `default`，支持名称或 ID。Bitto 可能映射 cwd，产物宜在任务中指定绝对路径。整个任务以 `SessionRunEnded` 为完成依据，中间模型回复不代表完成。

WorkBuddy 使用应用自带 CLI，任务不出现在桌面任务列表。只接受官方模型 ID，默认 `deepseek-v4.1-flash`，拒绝同 ID 的自定义模型覆盖；`project` 不生效。`session_id` 可续接，活跃会话并发提交会拒绝，前序任务已完成但仍在清理时会短暂等待。取消确认覆盖 CLI 进程组中的可执行后代。

WorkBuddy 通过固定版本辅助模块只读获取当前用户的桌面登录令牌，在本地子进程内存中传给 `www.workbuddy.cn`；兼容桌面凭证标注的 `www.codebuddy.cn` 域名。包装层对令牌值脱敏，不写入 MCP 配置或任务文件；过期时需重新登录，不自动刷新。用户启用 WorkBuddy 后端即按本机账号执行其明确委派的任务。

非秘密的依赖路径保存在 `~/.config/raincoat-agent-mcp/runtime.json`。以下环境变量可覆盖发现：

| 环境变量 | 用途 |
|---|---|
| `LOCAL_AGENT_MCP_STATE_DIR` | 自定义任务目录；旧 `BITTO_BRIDGE_STATE_DIR` 仍兼容 |
| `LOCAL_AGENT_NODE` | Node 可执行文件绝对路径 |
| `WORKBUDDY_CREDENTIAL_HELPER` | 兼容的 0.7.9 辅助模块入口绝对路径 |
| `BITTO_HOME` | Bitto 本地数据目录 |
| `BITTO_BRIDGE_WS_URL` | 多实例时指定本机 loopback WebSocket |

`interrupted` 表示执行状态未知，先检查后端会话，勿自动重提交。包更新不会改动上述任务和登录目录。

## 给维护者：构建与发布

当前源码位于 `tools/local-agent-mcp`。所有以下命令都在该目录运行：

```sh
python3 -m pip install 'setuptools>=77' wheel build twine
python3 -m build
python3 -m twine check dist/*
```

产物为 `dist/raincoat_agent_mcp-0.1.0-py3-none-any.whl` 和源码包 `.tar.gz`，可以直接把 wheel 提供给别人。wheel 包含完整 Python 包和 `workbuddy.mjs`，不包含登录凭证、测试产物或开发机配置。

版本只在 `src/raincoat_agent_mcp/_version.py` 维护。修改版本、完成验证后，可使用仓库中的 `.github/workflows/local-agent-mcp-release.yml`：

- 手动触发只构建、测试和上传 GitHub Actions artifact，不发布 PyPI。
- 推送 `local-agent-mcp/v0.1.0` 格式标签时校验标签与包版本一致，生成发行包。
- 仅在仓库变量 `LOCAL_AGENT_MCP_PYPI_ENABLED=true` 且配置好 `pypi` environment 和 PyPI Trusted Publisher 后，标签流程才发布 PyPI。
- Trusted Publisher 需对应仓库 owner/name、工作流文件名 `local-agent-mcp-release.yml` 和 environment `pypi`。首次发布前需确认包名可用并完成 PyPI 关联；本次实现没有推送标签或发布公共包。

工作流使用 OIDC，不需要将 PyPI token 写入源码。参考：[Python 打包指南](https://packaging.python.org/en/latest/tutorials/packaging-projects/)、[PyPI Trusted Publishing](https://docs.pypi.org/trusted-publishers/using-a-publisher/)、[uv 工具管理](https://docs.astral.sh/uv/guides/tools/)。

### 验证

```sh
python3 -m pip install -e .
python3 -m unittest discover -s tests -v
python3 tests/distribution_smoke.py dist/raincoat_agent_mcp-0.1.0-py3-none-any.whl
```

分发验收使用临时 HOME 和独立 uv tool 环境，从非项目目录执行，覆盖真实 MCP 握手、后台 worker 包导入、0.1.0→测试版 0.1.1 升级、回退及配置保留，不读取真实登录或调用大模型。测试版只在临时目录构建。

下列测试会创建真实后端任务并消耗模型额度，需要单独授权后运行：

```sh
python3 tests/integration.py bitto
python3 tests/integration.py workbuddy
python3 tests/lifecycle.py /private/tmp/local-agent-integration-EXAMPLE
```
