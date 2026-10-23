# Local Agent MCP

一个本地 MCP，通过必填参数 `backend="bitto" | "workbuddy"` 将完整任务交给对应 Agent 的原生运行时。模型与账户用量由对应后端处理；调用方自身的调度和验收仍消耗调用方额度。

## 返回速度

旧 Bitto 接口只返回任务 ID，建议调用方每 5–15 秒轮询。长任务中，调用方的等待/退避和重复读取完整工具历史会扩大延迟：实测旧任务的状态达到 130–251 KB，最终回复仅约 2 KB。

新接口的行为：

- `agent_submit_task` 默认保持至多 25 秒等待，任务完成即返回结果。
- 长任务超出单次等待时，立即调用 `agent_wait_task(job_id, timeout_seconds=25)`，持续等待；**不要 sleep 或指数退避**。
- 新 worker 通过私有 Unix socket 通知完成；先原子保存终态，再唤醒所有等待者，避免漏通知。
- 旧 Bitto worker 无需重启；兼容查询采用 50 ms 的有界回退检查。
- 默认仅返回最终文本与最近四条工具摘要；完整结果在 `result_path`。`include_details=true` 可取完整记录。
- 输出 `backend_completed_at`、`persisted_at`、`returned_at` 和 `completion_delivery_ms`，便于分清后端执行耗时与结果交付耗时。

MCP 工具调用结束后，不能保证主动唤醒已闲置的调用方模型。本方案通过保持有界等待，让后端结束时立即返回正在等待的工具调用，不宣称有跨客户端的主动回调。

本机真实 MCP 执行测试：Bitto 完成结果交付 **1.972 ms**（2026-10-22），WorkBuddy **1.261 ms**（2026-10-23）。数字从收到后端完成事件算起，不包含后端推理或调用方模型组织回复的时间，也不是任意负载下的保证。

## MCP 工具

| 工具 | 参数与用途 |
|---|---|
| `agent_status` | 必填 `backend`，检查对应运行时 |
| `agent_submit_task` | 必填 `backend, prompt`；可选 `model, cwd, title, project, session_id, timeout_seconds, wait_seconds, allowed_tools` |
| `agent_wait_task` | `job_id, timeout_seconds=25, include_details=false`，完成或需要授权时立即返回 |
| `agent_get_task` | `job_id, include_details=false`，立即读取快照 |
| `agent_cancel_task` | `job_id`，请求停止，需再等待实际终止 |
| `agent_respond_permission` | `job_id, request_id, allow`，回答 Bitto 的待处理授权，不记住全局授权 |

`timeout_seconds` 在提交接口表示任务执行上限，范围 1–86400 秒；在等待接口表示本次等待上限，范围 0–50 秒。本次等待超时不会取消后端任务。`wait_seconds=0` 可立即返回任务 ID。

旧工具 `bitto_status`、`bitto_submit_task`、`bitto_get_task`、`bitto_cancel_task`、`bitto_respond_permission` 由同一个服务器提供兼容入口。其中旧的 submit/get 也默认采用有界等待。旧 `job_id` 与记录目录保持可用，缺少 `backend` 的任务按 Bitto 读取。

## 后端边界

Bitto 连接已经运行的本机 sidecar，使用现有 Bitto 会话协议；任务在桌面端可见。`project` 支持名称或 ID，默认 `default`；`cwd` 可能被 Bitto 映射，请在任务中用绝对路径指定产物位置。不会将中间一条模型回复误判为整个任务结束。

WorkBuddy 使用应用自带的独立 Agent CLI，任务不会进入桌面客户端任务列表。`project` 不用于该后端。工具调用需要按用户授权在提交时显式指定 `allowed_tools`，空列表不开放工具，不会自动切换为跳过权限模式。`session_id` 可续接同一 CLI 会话；前序完成后的清理会短暂等待，仍在执行的同会话并发提交会拒绝。

只接受产品配置中的官方模型 ID（默认 `deepseek-v4.1-flash`），拒绝相同 ID 的自定义模型覆盖，避免转入调用方自己的 API 路由。凭证读取使用 `dsh-workbuddy-connect` 0.7.9 的现有桌面登录解密能力，令牌仅传给本地 CLI 子进程，既不放入任务记录也不放入 MCP 配置；包装层输出按令牌值脱敏。经用户明确授权，允许 `www.codebuddy.cn` 桌面凭证向 `www.workbuddy.cn` 认证。凭证过期时失败，需在 WorkBuddy 中重新登录，不自动刷新。

`agent_status` 只检查安装和 Node 可用性，不验证登录。安装时记录 Node 路径，兼容桌面客户端未加载 shell PATH 的环境；可用 `LOCAL_AGENT_NODE` 显式指定。凭证模块默认从本机 DeepSeek Harness desktop/web profile 发现，可用 `WORKBUDDY_CREDENTIAL_HELPER` 指定兼容版本模块的绝对路径。取消会停止 CLI 进程组，并确认其中可执行的后代都退出后才返回 `cancelled`。

## 安装与配置

要求 macOS、Python 3.11+ 和 `requirements.txt` 中的依赖。WorkBuddy 另需 Node.js 22+、已安装并登录的 WorkBuddy，以及本机的 `dsh-workbuddy-connect` 0.7.9 凭证读取模块。

本机安装并迁移 Codex 与 DeepSeek Harness desktop 配置：

```sh
python3 install.py          # 预览涉及的文件
python3 install.py --apply  # 安装、备份、替换注册
```

运行时安装到 `~/.local/share/local-agent-mcp/releases/<内容哈希>`，通过 `current` 稳定路径访问，不依赖开发 worktree 存活。两个客户端各保留唯一的 `local_agents` 注册；原配置和旧 CLI 入口会保存带时间戳的备份。重载 MCP 或重启对应客户端后使用新工具。`~/.local/bin/local-agent` 提供统一 CLI，旧 `bitto-agent` 仍可使用。

如只需为其他 MCP 客户端生成当前 checkout 的绝对路径配置：

```sh
python3 configure.py
```

配置写入被 Git 忽略的 `config/generated/`，包含通用 `mcp.json`、Codex TOML 和 DeepSeek Harness patch。不将开发机用户名或绝对路径提交成配置模板。

迁移时用唯一的 `local_agents` 注册替换旧的 `bitto` 注册，勿同时保留两个实例；旧工具名兼容入口仍在此服务器中。修改客户端配置前备份原文件；回滚时恢复备份。重载 MCP 或重启客户端后生效。

```sh
./local-agent status bitto
./local-agent submit bitto '执行一个任务并回复结果'
./local-agent wait JOB_ID
./local-agent get JOB_ID
./local-agent cancel JOB_ID
```

状态目录默认仍为 `~/.local/state/bitto-agent-bridge`，以兼容旧任务，可用 `LOCAL_AGENT_MCP_STATE_DIR` 指定独立目录。每个任务保存 `request.json`、`state.json`、事件和 worker 日志，后台任务不依赖 MCP 调用进程存活。私有 socket 在 `/private/tmp/local-agent-mcp-UID/`，目录权限 0700，worker 结束后清理。

`interrupted` 表示执行状态未知，后端可能仍在执行；先检查会话，勿自动重提交。相同 `backend + session_id` 通过锁串行化，不能同时提交两次续接。

## 验证

```sh
python3 -m unittest discover -s tests -v
# 以下会创建真实测试任务并消耗对应后端的模型额度：
python3 tests/integration.py bitto
python3 tests/integration.py workbuddy
# 用上一条输出的证据目录验证续接与真实子命令取消：
python3 tests/lifecycle.py /private/tmp/local-agent-integration-EXAMPLE
```

源码中的 `PLAN.md` 记录本分支的实施与验收范围。
