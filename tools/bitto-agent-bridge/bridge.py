"""Local agents delegate whole tasks to the running Bitto sidecar."""
from __future__ import annotations

import argparse
import asyncio
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
import uuid

import websockets

TERMINAL = {"succeeded", "failed", "cancelled", "interrupted"}
STATE = Path(os.environ.get("BITTO_BRIDGE_STATE_DIR", "~/.local/state/bitto-agent-bridge")).expanduser()
BITTO = Path(os.environ.get("BITTO_HOME", "~/.bitto")).expanduser()
PREFIX = "bitto.gateway.v1."


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    with open(temp, "x", opener=lambda p, flags: os.open(p, flags, 0o600)) as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
    temp.replace(path)


def job_dir(job_id: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}", job_id):
        raise ValueError("Invalid job_id")
    return STATE / "jobs" / job_id


def token() -> str:
    try:
        value = read_json(BITTO / "credentials/auth.json")["accessToken"]
    except (OSError, KeyError, ValueError) as e:
        raise RuntimeError("Bitto 登录凭证不可用，请打开 Bitto 并登录。") from e
    if not value:
        raise RuntimeError("Bitto 登录凭证为空，请重新登录。")
    return value


def api(path: str, body: dict | None = None) -> dict:
    base = os.environ.get("BITTO_BRIDGE_API_URL", "https://bitto.bilibili.co/")
    parsed = urlparse(base)
    if parsed.scheme != "https" or parsed.hostname not in {"bitto.bilibili.co", "uat-bitto.bilibili.co"} or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("API URL must use an official Bitto HTTPS host")
    req = urllib.request.Request(base.rstrip("/") + "/" + path,
        data=None if body is None else json.dumps(body).encode(),
        headers={"Authorization": "Bearer " + token(), "Accept": "application/protojson", "Content-Type": "application/protojson"})
    # Do not forward the account bearer through an HTTP redirect.
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=20) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise RuntimeError("Bitto 登录已过期或无权限，请在 Bitto 客户端重新登录。") from None
        raise RuntimeError(f"Bitto API returned HTTP {e.code}") from None


def discover_ws() -> str:
    override = os.environ.get("BITTO_BRIDGE_WS_URL")
    if override:
        p = urlparse(override)
        if p.scheme != "ws" or p.hostname not in {"127.0.0.1", "localhost", "::1"} or p.username or p.password or p.query or p.fragment:
            raise ValueError("WebSocket URL must be a local loopback ws:// address")
        return override
    result = subprocess.run(["/usr/sbin/lsof", "-nP", "-a", "-c", "bitto-ser", "-iTCP", "-sTCP:LISTEN", "-Fn"], capture_output=True, text=True)
    ports = set(re.findall(r"^n(?:127\.0\.0\.1|\[::1\]):(\d+)$", result.stdout, re.M))
    if len(ports) != 1:
        raise RuntimeError("未发现唯一的 Bitto 本地运行时。请打开 Bitto；多个实例时设置 BITTO_BRIDGE_WS_URL。")
    return "ws://127.0.0.1:" + ports.pop()


def settings_model() -> str:
    return read_json(BITTO / "settings.json").get("model", {}).get("defaultModel", "deepseek-v4.1-flash")


def status() -> dict:
    ws = discover_ws()
    token()
    return {"runtime": "Bitto local sidecar", "ws_url": ws, "default_model": settings_model(),
            "state_dir": str(STATE), "credential_present": True,
            "note": "本地发现检查；实际连接与认证在提交任务时验证。"}


def get_task(job_id: str) -> dict:
    directory = job_dir(job_id)
    result = read_json(directory / "state.json")
    worker_pid = result.get("worker_pid")
    if not worker_pid and (directory / "worker.json").exists():
        worker_pid = read_json(directory / "worker.json")["pid"]
    if result["status"] not in TERMINAL and worker_pid:
        try:
            os.kill(worker_pid, 0)
        except ProcessLookupError:
            result.update(status="interrupted", error="桥接 worker 已退出；Bitto 任务可能仍在执行，请先检查会话，勿自动重提交。")
    return result


def submit_task(prompt: str, title: str = "本地 Agent 委派任务", project: str = "default",
                model: str = "", cwd: str = "", session_id: str = "", timeout_seconds: int = 10800) -> dict:
    if not prompt.strip():
        raise ValueError("prompt must not be empty")
    if not 1 <= timeout_seconds <= 86400:
        raise ValueError("timeout_seconds must be between 1 and 86400")
    if session_id:
        uuid.UUID(session_id)
    directory = job_dir(uuid.uuid4().hex)
    ws = discover_ws()
    token()
    if cwd and not Path(cwd).expanduser().is_absolute():
        raise ValueError("cwd must be absolute")
    request = dict(prompt=prompt, title=title, project=project, model=model or settings_model(),
                   cwd=str(Path(cwd).expanduser()) if cwd else "", session_id=session_id,
                   timeout_seconds=timeout_seconds, ws_url=ws)
    atomic_json(directory / "request.json", request)
    initial = dict(job_id=directory.name, status="queued", session_id=session_id, model=request["model"],
                   created_at=time.time(), text="", tool_calls=[], message_usage=[], event_log=str(directory / "events.jsonl"))
    atomic_json(directory / "state.json", initial)
    with open(directory / "worker.log", "a", opener=lambda p, flags: os.open(p, flags, 0o600)) as log:
        worker = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "_worker", directory.name],
            stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
    atomic_json(directory / "worker.json", {"pid": worker.pid})
    # The worker owns state.json; the parent never overwrites its progress.
    return {"job_id": directory.name, "status": "queued", "worker_pid": worker.pid,
            "next": "调用 bitto_get_task(job_id) 查询进度和结果；需要授权时调用 bitto_respond_permission。"}


def cancel_task(job_id: str) -> dict:
    state = get_task(job_id)
    if state["status"] in TERMINAL:
        return state
    atomic_json(job_dir(job_id) / "cancel.json", {"requested_at": time.time()})
    return {"job_id": job_id, "status": "cancellation_requested", "note": "等待 Bitto SessionRunEnded 确认，尚未宣称取消完成。"}


def respond_permission(job_id: str, request_id: str, allow: bool) -> dict:
    state = get_task(job_id)
    pending = state.get("permission", {})
    if state["status"] != "waiting_permission" or pending.get("requestId", pending.get("request_id")) != request_id:
        raise ValueError("No matching pending permission request")
    atomic_json(job_dir(job_id) / "permission-response.json", {"requestId": request_id, "allow": allow, "remember": False})
    return {"job_id": job_id, "status": "permission_response_queued"}


def consume_event(state: dict, message: dict) -> None:
    kind = message.get("type", "").removeprefix(PREFIX)
    payload = message.get("payload", {})
    if kind == "SessionAccepted":
        state.update(run_id=payload.get("runId", payload.get("run_id")), status="running")
    # Only process the run accepted on this connection, never replayed prior turns.
    run_id = payload.get("runId", payload.get("run_id"))
    if not state.get("run_id") or (run_id and run_id != state["run_id"]):
        if kind == "ServerError":
            state.update(status="failed", error=payload.get("message", "Bitto server error"))
        return
    if kind == "SessionChatMessageStarted":
        state["streaming_text"] = ""
    elif kind == "SessionChatTextDelta":
        state["streaming_text"] = state.get("streaming_text", "") + payload.get("delta", "")
    elif kind == "SessionChatToolCall":
        call = payload.get("call", {})
        state["tool_calls"].append({"id": call.get("id"), "name": call.get("name"), "status": "running"})
    elif kind == "SessionChatToolResult":
        for call in state["tool_calls"]:
            if call["id"] == payload.get("toolCallId"):
                call.update(status="failed" if payload.get("isError") else "succeeded", result=str(payload.get("content", ""))[:4000])
    elif kind == "SessionChatMessageEnded":
        role = payload.get("role")
        if role not in (None, 2, "MESSAGE_ROLE_ASSISTANT"):
            return
        text = "\n".join(c.get("text", {}).get("text", "") for c in payload.get("contents", []))
        if text.strip():
            state["text"] = text
        meta = payload.get("meta", {})
        state.update(provider=meta.get("provider"), model=meta.get("model", state["model"]))
        if meta.get("usage"):
            state["message_usage"].append({"message_id": payload.get("messageId"), **meta["usage"]})
        if payload.get("isError"):
            state["error"] = payload.get("errorMessage", "Bitto assistant error")
    elif kind == "SandboxPermissionRequest":
        state.update(status="waiting_permission", permission=payload)
    elif kind == "SessionChatUiToolCall":
        state.update(status="waiting_desktop_tool", desktop_tool=payload,
                     note="此任务需要 Bitto 桌面端工具；本桥接只提供运行时工具，不模拟桌面工具。可取消后改从客户端执行。")
    elif kind == "ServerError":
        state.update(status="failed", error=payload.get("message", "Bitto server error"))
    elif kind == "SessionRunEnded":
        reason = payload.get("stopReason", payload.get("stop_reason", ""))
        error = payload.get("errorMessage", payload.get("error_message", ""))
        if error or "ERROR" in reason:
            outcome = "failed"
        elif any(x in reason for x in ("CANCEL", "ABORT")) or (state.get("cancel_sent") and "STOP" in reason):
            outcome = "cancelled"
        elif reason in ("STOP_REASON_STOP", "STOP_REASON_END_TURN") and not state.get("error"):
            outcome = "succeeded"
        else:
            outcome = "failed"
            error = error or state.get("error") or f"Bitto run ended with {reason}"
        state.update(status=outcome, stop_reason=reason, error=error, run_usage=payload.get("usage", {}), finished_at=time.time())


async def run_worker(job_id: str) -> None:
    directory = job_dir(job_id)
    state = read_json(directory / "state.json")
    request = read_json(directory / "request.json")
    state.update(worker_pid=os.getpid(), status="starting")
    def save():
        state["updated_at"] = time.time()
        atomic_json(directory / "state.json", state)
    save()
    lock = None
    try:
        if (directory / "cancel.json").exists():
            state.update(status="cancelled", finished_at=time.time()); save(); return
        sid = request["session_id"]
        device = (BITTO / "device.id").read_text().strip()
        if not sid:
            projects = await asyncio.to_thread(api, "v1/bitto/studio/projects")
            project = next((x for x in projects.get("projects", []) if request["project"] in (x["id"], x.get("name"))), None)
            if project is None:
                raise ValueError("Bitto project not found: " + request["project"])
            created = await asyncio.to_thread(api, "v1/bitto/agent/sessions", {
                "title": request["title"], "status": "SESSION_STATUS_ACTIVE", "projectId": project["id"], "deviceId": device})
            sid = created["session"]["id"]
        uuid.UUID(sid)
        state["session_id"] = sid
        (STATE / "locks").mkdir(parents=True, exist_ok=True, mode=0o700)
        lock = (STATE / "locks" / sid).open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("该会话已有桥接任务在执行，请等待后再继续。") from None
        save()
        async with websockets.connect(request["ws_url"], additional_headers={"Authorization": "Bearer " + token()}, open_timeout=10, max_size=16*1024*1024) as ws:
            async def send(kind, payload):
                await ws.send(json.dumps({"type": PREFIX + kind, "sessionId": sid, "deviceId": device, "payload": payload}))
            # The sidecar needs its own canonical workspace. It may remap cwd.
            await send("OpenSession", {"sessionId": sid, "afterSequence": 0, "cwd": request["cwd"]})
            async with asyncio.timeout(20):
                while True:
                    opened = json.loads(await ws.recv())
                    if opened.get("sessionId") != sid:
                        continue
                    if opened.get("type") == PREFIX + "ServerError":
                        raise RuntimeError(opened["payload"].get("message", "OpenSession failed"))
                    if opened.get("type") == PREFIX + "SessionOpened":
                        if opened.get("payload", {}).get("agentRunning"):
                            raise RuntimeError("Bitto 会话正在执行，请等待结束再继续。")
                        break
            if (directory / "cancel.json").exists():
                state.update(status="cancelled", finished_at=time.time()); save(); return
            await send("SessionChat", {"contents": [{"text": {"text": request["prompt"]}}],
                "clientMessageId": uuid.uuid4().hex, "composerContext": {"mentions": [], "modelId": request["model"]}})
            state["status"] = "submitted"; save()
            deadline = time.monotonic() + request["timeout_seconds"]
            stop_deadline = None
            with open(directory / "events.jsonl", "a", opener=lambda p, flags: os.open(p, flags, 0o600)) as log:
                while state["status"] not in TERMINAL:
                    expired = time.monotonic() > deadline
                    if (expired or (directory / "cancel.json").exists()) and not state.get("cancel_sent") and state.get("run_id"):
                        await send("SessionStopRun", {"runId": state["run_id"]})
                        state.update(cancel_sent=True, status="cancelling", timeout_expired=expired)
                        stop_deadline = time.monotonic() + 20
                        save()
                    if stop_deadline and time.monotonic() > stop_deadline:
                        raise RuntimeError("停止请求已发送，但未收到终止确认；请在 Bitto 检查会话。")
                    if expired and not state.get("run_id"):
                        raise RuntimeError("任务接收超时；执行状态未知，请先检查 Bitto 会话。")
                    permission = directory / "permission-response.json"
                    if permission.exists() and state.get("permission"):
                        await send("SandboxPermissionResponse", read_json(permission)); permission.unlink()
                        state.pop("permission", None); state["status"] = "running"; save()
                    try:
                        raw = await asyncio.wait_for(ws.recv(), 0.5)
                    except asyncio.TimeoutError:
                        continue
                    message = json.loads(raw)
                    if message.get("sessionId") != sid:
                        continue
                    log.write(json.dumps(message, ensure_ascii=False) + "\n"); log.flush()
                    consume_event(state, message); save()
    except Exception as e:
        state.update(status="interrupted" if state.get("status") in {"submitted", "running", "cancelling", "waiting_permission", "waiting_desktop_tool"} else "failed",
                     error=str(e), finished_at=time.time())
        save()
    finally:
        if lock:
            lock.close()


def serve_mcp() -> None:
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("bitto", instructions="将整个任务委派给 Bitto 自己的本地运行时、模型及额度。submit 后保存 job_id，用 get_task 取回结果。status 只做本地发现检查。不要自动重提交状态未知的任务。需要 Bitto 桌面端工具的任务可能无法执行。")
    @mcp.tool(name="bitto_status")
    def tool_status() -> dict:
        """发现 Bitto 本地运行时，读取默认模型；不产生模型调用。"""
        return status()
    @mcp.tool(name="bitto_submit_task")
    def tool_submit(prompt: str, title: str = "本地 Agent 委派任务", project: str = "default", model: str = "", cwd: str = "", session_id: str = "", timeout_seconds: int = 10800) -> dict:
        """由 Bitto 执行完整任务并消耗 Bitto 模型额度。立即返回 job_id；用 get_task 查询。session_id 可继续既有空闲会话。cwd 可能被 Bitto 重映射，输出文件请指定绝对路径。"""
        return submit_task(prompt, title, project, model, cwd, session_id, timeout_seconds)
    @mcp.tool(name="bitto_get_task")
    def tool_get(job_id: str) -> dict:
        """查询持久任务状态、Bitto 最终回复、工具结果和逐消息 token usage。轮询建议间隔 5–15 秒。"""
        return get_task(job_id)
    @mcp.tool(name="bitto_cancel_task")
    def tool_cancel(job_id: str) -> dict:
        """请求停止此桥接任务；查询 get_task，收到 Bitto 终止确认后才标记完成。"""
        return cancel_task(job_id)
    @mcp.tool(name="bitto_respond_permission")
    def tool_permission(job_id: str, request_id: str, allow: bool) -> dict:
        """回答 Bitto 该任务的待处理工具授权；仅在调用方已有用户授权时允许，不记住授权、不更改全局策略。"""
        return respond_permission(job_id, request_id, allow)
    mcp.run(transport="stdio")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("mcp"); sub.add_parser("status")
    submit = sub.add_parser("submit")
    submit.add_argument("prompt", help="Use --prompt-file for long prompts", nargs="?", default="")
    submit.add_argument("--prompt-file")
    for name in ["title", "project", "model", "cwd", "session-id"]:
        submit.add_argument("--" + name, default={"title": "本地 Agent 委派任务", "project": "default"}.get(name, ""))
    submit.add_argument("--timeout-seconds", type=int, default=10800)
    for name in ["get", "cancel", "_worker"]:
        sub.add_parser(name).add_argument("job_id")
    args = vars(parser.parse_args()); command = args.pop("command")
    try:
        if command == "mcp": serve_mcp(); return
        if command == "_worker": asyncio.run(run_worker(args["job_id"])); return
        if command == "submit":
            file = args.pop("prompt_file")
            if file: args["prompt"] = Path(file).read_text()
            result = submit_task(**args)
        elif command == "get": result = get_task(args["job_id"])
        elif command == "cancel": result = cancel_task(args["job_id"])
        else: result = status()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
