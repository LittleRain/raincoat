# Raincoat Agent MCP

在 macOS 或 Windows 设备上，通过 MCP 把完整任务交给已安装的本机 Bitto、WorkBuddy 或 Codex CLI。调用方可以是 Codex、DeepSeek Harness，或支持 stdio MCP 的其他客户端；被调用的后端通过 `backend` 参数选择。Bitto 在 Windows 上还需要提供本地 WebSocket sidecar 的桌面版本。

> **分发状态：** 当前版本为 0.2.0，尚未发布到 PyPI。要让别人安装，需要向对方提供构建好的 `.whl` 文件，或提供可访问的源码仓库。安装包不含你的登录信息；每台设备都要单独安装、登录和配置。Windows 上的 Bitto 需要手动提供本地连接地址，见下文。

## 先确认你的设备

- macOS 或 Windows 10/11、Python 3.11+、[uv](https://docs.astral.sh/uv/getting-started/installation/)。
- 至少安装并登录一个要调用的后端。只用 GPT 时安装 Codex CLI；只用 Bitto 或 WorkBuddy 时不需要 Codex CLI。
- 安装时需要联网获取 Python 依赖。使用 WorkBuddy 时，还需要 Node.js 22.19+（22 系列）或 24+、npm，并在准备后端的步骤中安装辅助模块。
- 调用模型使用这台设备上对应产品的账号和额度，不使用发布者的账号。

| `backend` | 本机运行时 | 提交前要做什么 | 默认模型 |
| --- | --- | --- | --- |
| `bitto` | Bitto 桌面端 sidecar | 打开 Bitto 并登录；Windows 需配置 `BITTO_HOME` 和 `BITTO_BRIDGE_WS_URL` | Bitto 当前设置 |
| `workbuddy` | WorkBuddy 自带 CLI | 安装并登录 WorkBuddy；安装辅助模块 | `deepseek-v4.1-flash` |
| `gpt` | Codex CLI | 安装 Codex CLI，运行 `codex login` | Codex CLI 默认模型 |

Linux 尚未适配。

## 安装到自己的设备

拿到发布者提供的 wheel 后，在终端执行，替换成真实文件路径。Windows 在 PowerShell 中使用相应的磁盘路径，例如 `C:\Downloads\raincoat_agent_mcp-...whl`：

```sh
uv tool install --python 3.11 /path/to/raincoat_agent_mcp-0.2.0-py3-none-any.whl
local-agent --version
```

如果拿到的是仓库源码，在仓库根目录执行：

```sh
uv tool install --python 3.11 ./tools/raincoat-agent-mcp
local-agent --version
```

若终端提示找不到 `local-agent`，运行 `uv tool update-shell` 后重新打开终端。若 `uv` 找不到 Python 3.11，可按其提示安装，或将 `--python 3.11` 换成这台设备已有的 Python 3.11+。

### 准备一个后端

只运行你要使用的命令。检查不会调用模型；`doctor --backend all` 要求三个后端都可用，因此只装了一个后端时不要用它判断安装是否成功。

```sh
# Bitto：先打开并登录桌面端
local-agent doctor --backend bitto

# WorkBuddy：先打开并登录桌面端；此命令用 npm 安装固定版本的辅助模块
local-agent doctor --backend workbuddy --install-deps

# GPT：先安装 Codex CLI 并运行 codex login
local-agent doctor --backend gpt
```

WorkBuddy 的辅助模块是 `dsh-workbuddy-connect@0.7.9`，安装在用户目录下的 `.local/share/raincoat-agent-mcp/workbuddy/`。macOS 默认查找 `/Applications/WorkBuddy.app`；Windows 默认查找 `%LOCALAPPDATA%\Programs\WorkBuddy`。非默认安装位置可设置 `WORKBUDDY_APP` 为应用根目录。`doctor` 不验证 WorkBuddy 登录是否仍有效，提交任务时才验证。GPT 的 `doctor` 会运行 `codex login status`，不会调用模型。安装辅助模块后可用 `local-agent doctor --backend workbuddy` 再次检查。

Windows 上的 Bitto 不自动扫描监听端口。先确认安装版本带有本地 WebSocket sidecar，再把 `BITTO_HOME` 设为含 `credentials/auth.json`、`device.id` 的本机数据目录，把 `BITTO_BRIDGE_WS_URL` 设为本机 `ws://127.0.0.1:<port>` 地址。可在 PowerShell 中为当前终端设置后运行 `local-agent doctor --backend bitto`；使用桌面 MCP 客户端时，要让该客户端也能读取这两个环境变量并重启客户端。若 Windows Bitto 没有该 sidecar，这个后端无法调用。

```powershell
$env:BITTO_HOME = 'C:\Users\你的用户名\.bitto'
$env:BITTO_BRIDGE_WS_URL = 'ws://127.0.0.1:实际端口'
local-agent doctor --backend bitto
```

### 接入 MCP 客户端

以 Codex 为例，先预览将写入的配置，再应用：

```sh
local-agent setup --client codex
local-agent setup --client codex --apply
```

随后重载 MCP 或重启 Codex。配置位于 `~/.codex/config.toml`。如果使用 DeepSeek Harness：

```sh
local-agent setup --client deepseek --apply
# 非默认 profile：local-agent setup --client deepseek --dsh-profile web --apply
```

其他 stdio MCP 客户端可生成标准 JSON，并把内容放入该客户端的 MCP 配置：

```sh
local-agent setup --client generic
# 或保存为文件：
local-agent setup --client generic --output ./mcp.json --apply
```

`setup --apply` 写入前会备份原文件为 `*.before-local-agents-<时间戳>`；它只替换旧 `bitto` 和 `local_agents` 注册。自动检测已存在客户端目录时可用 `local-agent setup --apply`。配置中的 Python 路径指向安装环境，后续升级不需要重新填写源码路径。

## 发起第一个任务

客户端加载后，应能看到 `agent_status`、`agent_submit_task`、`agent_wait_task` 等工具。先用 `agent_status(backend="gpt")` 检查运行时，再提交任务，例如：

```json
{
  "backend": "gpt",
  "prompt": "读取当前目录并总结项目结构",
  "cwd": "/absolute/workspace"
}
```

GPT 默认使用 `read-only` 沙箱。确需在 `cwd` 写文件时，为该次任务加 `"sandbox": "workspace-write"`。WorkBuddy 的工具权限由该次任务的 `allowed_tools` 指定；空列表不开放工具，例如 `"allowed_tools": ["Bash(python3:*)"]`。Bitto 使用其运行时的交互授权。

`agent_submit_task` 默认等待最多 25 秒。若返回的任务尚未完成，立即用返回的 `job_id` 调用 `agent_wait_task`；单次等待超时不会取消任务。若状态为 `interrupted`，先检查后端会话，避免重复提交可能仍在执行的任务。

也可直接用 CLI 验证调用链；以下 `submit` 会实际调用模型：

```sh
local-agent status gpt
local-agent submit gpt '总结当前目录' --cwd /absolute/workspace
local-agent wait JOB_ID
```

## 常见问题

| 现象 | 检查和处理 |
| --- | --- |
| `local-agent: command not found` | 运行 `uv tool update-shell` 并重新打开终端，确认 `uv tool list` 中有此包。 |
| `doctor --backend all` 失败 | 只安装了部分后端时，改用 `doctor --backend bitto/workbuddy/gpt` 检查要使用的那个。 |
| WorkBuddy 显示缺少 Node 或辅助模块 | 使用受支持的 Node/npm，运行 `local-agent doctor --backend workbuddy --install-deps`；确认应用路径，非默认位置设置 `WORKBUDDY_APP`。 |
| WorkBuddy 提交失败但 doctor 通过 | 打开 WorkBuddy 重新登录；`doctor` 只检查安装，登录在提交时验证。 |
| GPT 显示未登录 | 在同一用户下执行 `codex login`，再运行 `local-agent doctor --backend gpt`。 |
| Bitto 找不到本地运行时 | 打开 Bitto；macOS 多实例或 Windows 上用 `BITTO_BRIDGE_WS_URL` 指定本机 loopback WebSocket。 |
| 客户端看不到工具 | 确认已执行对应的 `setup --apply`，再重载 MCP 或重启客户端。 |
| 安装 wheel 时依赖解析失败 | 确认能访问 Python 包索引；wheel 不包含 `mcp`、`websockets` 等第三方依赖。 |

## 更新与回退

现在通过文件分发时，先拿到新 wheel，再更新：

```sh
local-agent update --from /path/to/new.whl
```

若未来发布到 PyPI，可用 `local-agent update --check` 查询公开版本，再运行 `local-agent update`。目前 `--check` 会因尚未发布而报告错误。回退时保留旧 wheel，执行 `local-agent update --from /path/to/old.whl`。Windows 上的 `update` 会输出 `powershell_command`；复制该命令到 PowerShell 执行，避免安装目录被当前进程占用。更新前需完成或取消仍在执行、等待授权的任务；更新后重载 MCP。任务记录、登录状态和客户端配置不会随包升级删除。

## 运行边界

- 本机使用各后端原有的运行时和登录。Bitto 任务在其桌面端可见；WorkBuddy 和 GPT 的 CLI 任务不在桌面任务列表。
- GPT 使用 `codex exec --json`，默认只读；`model` 留空时使用 Codex CLI 默认模型。`project` 对 GPT 和 WorkBuddy 不生效。WorkBuddy 只接受其官方模型 ID。
- 任务请求、输出和事件保存在本机 `~/.local/state/bitto-agent-bridge/`，可用 `LOCAL_AGENT_MCP_STATE_DIR` 改路径。请按本机数据管理习惯处理这些记录。
- `agent_get_task` 读取状态，`agent_cancel_task` 请求取消；仅 Bitto 支持 `agent_respond_permission`。旧的 `bitto_*` 工具名仍保留。
- MCP 工具调用结束后不会主动唤醒客户端模型；调用方需要持续调用 `agent_wait_task` 等待终态。

## 维护者：构建与发布

在仓库根目录运行：

```sh
python3 -m unittest discover -s tools/raincoat-agent-mcp/tests -v
uv build tools/raincoat-agent-mcp --out-dir dist-raincoat-agent-mcp
python3 tools/raincoat-agent-mcp/tests/distribution_smoke.py dist-raincoat-agent-mcp/raincoat_agent_mcp-0.2.0-py3-none-any.whl
```

分发验收会在临时用户目录中安装 wheel、完成 MCP 握手、从已安装包启动后台 worker、升级和回退，不调用模型；需可访问 Python 包索引。`.github/workflows/raincoat-agent-mcp-release.yml` 在 macOS 和 Windows 运行检查并上传构建产物。当前工作流未自动提供面向使用者的下载入口，且未发布到 PyPI；正式开放前需要确定交付 wheel 或源码的渠道。

版本只在 `src/raincoat_agent_mcp/_version.py` 维护。标签格式为 `raincoat-agent-mcp/v<version>`；只有配置好 PyPI Trusted Publisher 和仓库变量 `LOCAL_AGENT_MCP_PYPI_ENABLED=true` 时，标签工作流才会发布到 PyPI。真实 Bitto、WorkBuddy、GPT 集成测试会调用模型并消耗各自账号额度，不属于上述无模型验收。
