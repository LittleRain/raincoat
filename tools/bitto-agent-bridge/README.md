# Bitto Agent Bridge

让 Codex、DeepSeek Harness 或其他本地 agent，将完整任务交给 **Bitto 本地运行时、Bitto 模型及其 token 计量链路**。桥接本身不调用其他模型。调用方的调度与验收仍消耗调用方自己的额度。

已验证 Bitto 1.8.1。本实现使用该版本的内部 REST / WebSocket 协议，客户端升级后需要重新验证兼容性。

## 前置条件

- macOS，本机 Bitto 已打开、已登录，且本地运行时已启动。
- Python 3.11+，依赖：`python3 -m pip install -r requirements.txt`。本机已有可用依赖，无需重复安装。
- 调用进程须能读取 Bitto 登录文件、连接本地运行时和 Bitto 后端。
- 本机默认路径 `~/.bitto`；不会把 accessToken 写入 MCP 配置、任务记录或日志。登录过期时应在 Bitto 重新登录。

## MCP 接入

通用 stdio 配置见 `config/mcp.json`；已生成当前机器的绝对路径和 Python 路径。

Codex 对应配置见 `config/codex.toml`，或用 CLI：

```sh
codex mcp add bitto -- /absolute/path/to/python3 /absolute/path/to/bridge.py mcp
```

DeepSeek Harness 使用内置 `@deepseek-ai/dsh-mcp-client`，配置见 `config/deepseek.patch.yml`。已注册到本机桌面 profile 的 `~/.dsh/profiles/desktop/cordis.patch.yml`。桌面 profile 由 Electron 应用专管，不能直接通过 CLI 启动。其他 profile 可使用独立覆盖层，例如：

```sh
dsh --profile web --patch /absolute/path/to/config/deepseek.patch.yml
```

DeepSeek 中工具名为 `mcp__bitto__bitto_submit_task` 等。配置修改后在客户端重新加载 MCP 或重启客户端。

| MCP 工具 | 用途 |
|---|---|
| `bitto_status()` | 发现本地运行时，读取默认模型；不产生模型调用，不代表认证已通过 |
| `bitto_submit_task(prompt, title?, project?, model?, cwd?, session_id?, timeout_seconds?)` | 异步提交完整任务，返回 `job_id` |
| `bitto_get_task(job_id)` | 读取进度、`session_id`、最终文本、工具摘要、provider/model、token usage |
| `bitto_cancel_task(job_id)` | 请求停止，之后查询任务，等待 Bitto 返回终止确认 |
| `bitto_respond_permission(job_id, request_id, allow)` | 回答待处理的 Bitto 工具授权；调用方应遵守用户授权，桥接不会自动批准或记住授权 |

`project` 默认 `default`，可传项目名称或 ID；不传 `model` 时读取 Bitto 当前默认模型。`session_id` 为空时新建会话，传入已完成任务返回的 ID 时继续该会话。相同会话不能同时运行多个桥接任务，也不会接管正在客户端执行的会话。

调用示例：

```json
{
  "prompt": "执行 Bitto 当前安装的某个工作流，参数……，将结果保存到 /absolute/path/result.json，回复路径与摘要。",
  "title": "本地 Agent 委派任务",
  "project": "default",
  "timeout_seconds": 10800
}
```

提交后保存 `job_id`，每 5–15 秒查询一次。`succeeded` 是正常完成；`failed` 为已知失败；`cancelled` 是已确认终止；`interrupted` 表示桥接失联或状态未知，Bitto 任务可能仍在执行，先检查会话，**不要自动重新提交**。执行超时会请求取消，只有终止确认后才标记 `cancelled`，同时返回 `timeout_expired: true`。

工具调用、运行时技能和插件由 Bitto 自己处理，执行时读取 Bitto 当前安装的内容。桥接不复制业务脚本。需要在会话中指定精确工作流和参数；这不会自动带上其他历史会话里的上下文。

## CLI

```sh
./bitto-agent status
./bitto-agent submit '请用你的工具执行任务，并回复结果'
./bitto-agent submit --prompt-file /absolute/path/task.txt --project default
./bitto-agent get JOB_ID
./bitto-agent submit '继续上一步……' --session-id SESSION_ID
./bitto-agent cancel JOB_ID
```

## 数据与边界

- 状态默认保存到 `~/.local/state/bitto-agent-bridge/jobs/JOB_ID/`，包含请求、进度、最终结果和原始事件；后台 worker 独立于 MCP 调用进程，调用方断开不取消任务。桥接 worker 不是开机自启服务，机器重启或 worker 崩溃后不会自动重发任务。
- 结果中的 `message_usage` 保留每条模型回复的用量；`run_usage` 原样保留 Bitto 终止事件的数值。本次观察到终止事件值与最后一条回复一致，不能将两者相加，且不能据此推算实际金额或账户扣款。
- `cwd` 由 Bitto 解释，可能映射到其工作区。输出位置需要明确时，请在任务中指定绝对路径，并让 Bitto 执行后读取确认。
- 仅连接现有的本地 sidecar，不启动第二个运行时、不切换 Bitto 模型设置、不修改全局授权策略。安装桥接后，本地 agent 可以提交 Bitto 任务；实际工具授权仍由 Bitto 和调用方处理。
- 不注册 Bitto 桌面端 UI 工具。依赖桌面专用工具的任务可能显示 `waiting_desktop_tool`，可取消后从 Bitto 客户端执行；运行时自带 `bash` 等工具已实际验证。
- `BITTO_BRIDGE_WS_URL=ws://127.0.0.1:PORT` 可指定本机多实例中的一个；否则通过 `lsof` 自动发现，端口变化不需要改配置。
- 可设置 `BITTO_HOME`、`BITTO_BRIDGE_STATE_DIR`；测试环境可设置 `BITTO_BRIDGE_API_URL=https://uat-bitto.bilibili.co/`。后端只允许 Bitto 官方 HTTPS 域名，WebSocket 只允许本机 loopback。

## 验证

```sh
python3 -m unittest discover -s tests -v
# 会创建 Bitto 测试会话并消耗其模型额度：
python3 tests/integration_mcp.py
```

集成测试真实验证 MCP 工具发现、Bitto 执行并生成文件、调用方退出后继续执行、同会话续接和取消确认。2026-10-22 本机均通过：provider 为 `bitto`，模型为 `deepseek-v4.1-flash`，平方和为 3219，取消返回 `STOP_REASON_ABORTED`。

DeepSeek 自带 MCP SDK 也已单独验证：协议自动协商、发现五个工具、调用 `bitto_status` 均通过。桌面应用当前会话尚未重新加载配置，重启或重载后生效。
