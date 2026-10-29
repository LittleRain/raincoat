# raincoat-skill-health

`raincoat-skill-health` 是本地 skill inventory 与 health 报告 CLI。它可独立扫描本地 `SKILL.md` 目录；Hermes usage 导入是可选消费者能力，只有宿主显式写出 usage log 后才有 usage 数据。本 README 也记录可选 Hermes 宿主接入协议。

## 运行要求

- Python 3.10 或更高版本；仅使用 Python 标准库，无需 `pip install`。
- 通过 `scripts/raincoat-skill-health` 启动；可从任意当前工作目录调用。扫描、导入、状态和报告均为本地文件操作，不连接网络，也不修改宿主配置。
- 不提供 Windows 原生 shell 启动器；Python 脚本本身使用标准库。
- 许可尚待仓库维护者确认；本目录不包含单独的 `LICENSE`。

Windows 或无 Bash 环境可直接调用 `python scripts/raincoat-skill-health.py`，参数与包装器相同；原生 Windows 尚未实测。

示例：

```bash
SKILL_DIR=/path/to/raincoat-skill-health
"$SKILL_DIR/scripts/raincoat-skill-health" doctor \
  --root /path/to/skills \
  --language zh \
  --output-dir /path/to/local-report
```

`--host hermes --agent hermes` 会从 `HERMES_HOME`（未设置时为 `~/.hermes`）读取 skill inventory 和可选的 `skill_usage.jsonl`。没有 usage 文件时，CLI 仍可扫描 skills，并在报告中给出 `log_path_missing`；这表示没有可导入的记录，不表示 skills 从未使用。

## 可选 Hermes 宿主接入

本节面向负责修改 Hermes gateway / runtime / `skill_view` / loader 的 agent，以及部署 Hermes 的工程师。宿主集成不是 CLI 的运行前提。

## 结论

如果 Hermes 只安装了 `raincoat-skill-health`，但宿主没有按协议写 usage log，那么 `raincoat-skill-health` 只能：

- 正确扫描当前 Hermes profile 的 skills
- 正确读取 `<HERMES_HOME>/skill_usage.jsonl`
- 在没有 usage 数据时给出更准确的诊断

它**不能凭空创造 usage truth**，也不会自动修改 Hermes 宿主或伪造 usage。

要让报告里真正出现 usage events，Hermes 宿主必须补两条日志链路：

1. 成功加载 skill 后写 usage event
2. usage event 写失败时写 health warning

## 和 dashboard 的关系

`raincoat-skill-health` 现在有两个面向操作员的只读产物：

- `doctor`
  - 生成 health JSON / Markdown
  - 用来判断 usage、重复、弱触发、长期未使用等问题
- `dashboard`
  - 生成本地 `raincoat-skill-health-dashboard.html`
  - 用来直观看当前 Hermes skills inventory，并把最近一次 doctor findings 挂回每个 skill
  - 默认聚合 `~/.hermes/skills` 和 `~/.hermes/profiles/*/skills`
  - 展示每个 skill 安装在哪些 profiles；如果 usage event 带 `profile_name` 或 `profile_home`，也展示它被哪些 profiles 加载过

推荐流程：

1. 宿主先按本文实现 usage / health hook
2. 跑一次 `doctor`
3. 再生成 `dashboard`
4. 用 HTML 页面看 inventory、roots、doctor findings 是否一致

## 宿主必须实现的行为

### 1. 只在真实 skill load 成功后写 usage

写 usage 的时机必须固定在：

- `skill_view`
- skill loader
- skill resolver
- skill dispatcher

这些路径里，**成功拿到 skill 内容并把 skill 纳入当前执行上下文之后**。

以下情况不能记 usage：

- skills catalog render
- metadata render
- 候选召回但没有真正 load
- 模型只是提到了 skill 名字
- 只是“看起来像用了 skill”，但宿主没有走统一 loader 路径

### 2. 所有入口统一写同一种 event

需要覆盖四种入口：

- `slash`
- `preloaded`
- `cron`
- `intent_match`

不要把 slash 单独埋点、自然调用单独埋点、cron 再单独埋点。  
必须走同一个写入函数，否则统计口径会分裂。

### 3. 使用当前 profile 的 `HERMES_HOME`

所有路径都要基于 `HERMES_HOME` 解析：

- skill root: `<HERMES_HOME>/skills`
- usage log: `<HERMES_HOME>/skill_usage.jsonl`
- health log: `<HERMES_HOME>/skill_usage_health.jsonl`

不要写死：

- `~/.hermes/skills`
- `~/.hermes/skill_usage.jsonl`

默认 profile 才是 `~/.hermes`。  
命名 profile 会落到 `~/.hermes/profiles/<name>`，或者由启动脚本显式设置 `HERMES_HOME`。

## 必须写出的文件

### Usage log

文件路径：

```text
<HERMES_HOME>/skill_usage.jsonl
```

每次真实 skill load 成功后追加一行 JSON：

```json
{
  "skill_name": "raincoat-skill-health",
  "timestamp": "2026-04-29T12:00:00Z",
  "agent": "hermes",
  "session_id": "abc123",
  "profile_name": "default",
  "profile_home": "/Users/you/.hermes",
  "source": "hermes-host",
  "scenario": "audit local skills after repeated routing errors",
  "trigger_source": "intent_match",
  "outcome_signal": "success"
}
```

最少字段：

- `skill_name`
- `timestamp`
- `agent`
- `session_id`
- `profile_name`
- `profile_home`
- `source`
- `scenario`
- `trigger_source`
- `outcome_signal`

约束：

- `trigger_source` 只能是：
  - `slash`
  - `preloaded`
  - `cron`
  - `intent_match`
- `outcome_signal` 第一版统一写 `success`
- `source` 固定用宿主标识，例如 `hermes-host`

### Health log

文件路径：

```text
<HERMES_HOME>/skill_usage_health.jsonl
```

如果 usage 写失败，不要阻断 skill 执行。  
但必须追加一条结构化 warning：

```json
{
  "ts": "2026-04-29T12:00:01Z",
  "agent": "hermes",
  "source": "hermes-host",
  "code": "hook_not_enabled",
  "message": "skill_view completed but usage hook was not active"
}
```

推荐 `code`：

- `log_path_missing`
- `log_path_unwritable`
- `hook_not_enabled`
- `session_id_missing`
- `json_write_failed`

## 推荐实现方式

## 统一写入函数

在 Hermes 宿主里实现两个统一函数：

- `record_skill_usage(...)`
- `record_skill_usage_warning(...)`

要求：

- 所有入口都调用同一个 `record_skill_usage(...)`
- 所有写失败都走 `record_skill_usage_warning(...)`
- `record_skill_usage_warning(...)` 自己也要软失败，不能把主流程打断

示意结构：

```python
def get_hermes_home() -> Path:
    value = os.environ.get("HERMES_HOME")
    if value:
        return Path(value).expanduser()
    return Path.home() / ".hermes"


def record_skill_usage(
    *,
    skill_name: str,
    session_id: str,
    scenario: str,
    trigger_source: str,
) -> None:
    hermes_home = get_hermes_home()
    log_path = hermes_home / "skill_usage.jsonl"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "skill_name": skill_name,
            "timestamp": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "agent": "hermes",
            "session_id": session_id,
            "source": "hermes-host",
            "scenario": scenario,
            "trigger_source": trigger_source,
            "outcome_signal": "success",
        }
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event, ensure_ascii=False) + "\n")
    except Exception as exc:
        record_skill_usage_warning(
            code="json_write_failed",
            message=f"failed to write usage event: {exc}",
        )
```

warning 写法示意：

```python
def record_skill_usage_warning(*, code: str, message: str) -> None:
    try:
        hermes_home = get_hermes_home()
        path = hermes_home / "skill_usage_health.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "ts": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "agent": "hermes",
            "source": "hermes-host",
            "code": code,
            "message": message,
        }
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
```

## 正确的挂载点

把 hook 放在 **skill load 成功返回之后**，不是挂在这些地方：

- catalog render 前
- candidate ranking 时
- 只要命中名字就立刻写
- skill 文本还没真正返回时就写

更具体地说，应该是这种语义：

1. Hermes 命中了某个 skill
2. Hermes 真正读取/解析了这个 skill
3. 该 skill 已经被纳入当前轮上下文或执行路径
4. 这时写 usage

如果第 2、3 步没发生，就不要写。

## 对 agent 的执行清单

如果你是一个正在改 Hermes 宿主的 agent，按这个顺序做：

1. 找到真实的 skill load 成功路径
   - 搜 `skill_view`
   - 搜 skill loader / resolver / dispatcher
   - 找“成功返回 skill 内容”的位置

2. 确认四种入口最终是否走同一条路径
   - `slash`
   - `preloaded`
   - `cron`
   - `intent_match`

3. 如果自然调用没有经过统一 loader，先收口路径
   - 不要在多个地方各自写日志
   - 先统一到真实 load 路径

4. 加 `record_skill_usage(...)`
   - 成功 load 后写
   - 补 `trigger_source`
   - `session_id` 缺失时写 warning，不要假造

5. 加 `record_skill_usage_warning(...)`
   - 对文件不存在、不可写、hook 缺失、session 丢失、JSON 写失败分别写不同 `code`

6. 重启 Hermes / gateway
   - 不重启的话，旧进程不会加载新的 hook

7. 用真实请求验收
   - 跑一次 slash skill
   - 跑一次自然调用 skill
   - 确认 `skill_usage.jsonl` 有新行
   - 确认 `trigger_source` 正确

8. 再跑 `raincoat-skill-health`

```bash
"$HERMES_HOME/skills/raincoat-skill-health/scripts/raincoat-skill-health" doctor \
  --host hermes \
  --agent hermes \
  --scan-scope local_only \
  --output-dir ~/.skill-health
```

9. 看报告中的关键字段
   - `resolved_hermes_home`
   - `effective_roots`
   - `usage_log_path`
   - `usage_logging_status`
   - `usage_events`

## 验收标准

最少要满足这些：

1. `skill_usage.jsonl` 写到了当前 `HERMES_HOME`
2. 自然调用如果真的 load 了 skill，会写 `trigger_source: intent_match`
3. slash / preloaded / cron / intent_match 四类入口都能落 usage
4. catalog render / metadata render / 只提 skill 名称不会误记 usage
5. 写 usage 失败时不会中断主流程
6. 写 usage 失败时会落 `skill_usage_health.jsonl`
7. `raincoat-skill-health doctor --host hermes --agent hermes` 能看到正确的 usage 计数

## 常见误区

### 误区 1：安装了 `raincoat-skill-health` 就应该自动有 usage

错。  
`raincoat-skill-health` 不是埋点器，它是 usage consumer。

### 误区 2：只要模型回答里体现了 skill 内容，就算 usage

错。  
只有宿主真正 load 了 skill，才算 usage。

### 误区 3：写 usage 失败就 `except: pass`

错。  
主流程可以软失败，但 warning 不能吞掉，否则后面只能看到 `usage_events = 0`，看不到根因。

### 误区 4：自然调用单独做一套日志

错。  
自然调用也应该走统一 loader / resolver，再复用同一套 usage 记录函数。

## 相关文件

- 协议参考：[references/hermes-usage-protocol.md](references/hermes-usage-protocol.md)
- Skill 入口：[SKILL.md](SKILL.md)
- CLI 实现：[scripts/raincoat-skill-health.py](scripts/raincoat-skill-health.py)

## 迁移交付状态

当前为 `draft`。本轮完成包内路径与命名整理；许可来源尚未确认，不能正式发布。macOS 的具体检查见仓库迁移验收记录；Windows、其他宿主的原生安装与自动发现未实测。历史上标注 beta 的元数据不作为本轮验收结论。
