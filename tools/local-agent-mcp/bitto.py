"""Bitto protocol adapter, extracted from the previously verified bridge."""
from __future__ import annotations
import asyncio, fcntl, json, os, re, subprocess, time, urllib.error, urllib.request, uuid
from pathlib import Path
from urllib.parse import urlparse
import websockets
import shared
BITTO = Path(os.environ.get("BITTO_HOME", "~/.bitto")).expanduser()
PREFIX = "bitto.gateway.v1."
TERMINAL = shared.TERMINAL
read_json = shared.read_json
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
        elif any(x in reason for x in ("CANCEL", "ABORT")) or (state.get("cancel_sent") and reason == "STOP_REASON_STOP"):
            outcome = "cancelled"
        elif reason in ("STOP_REASON_STOP", "STOP_REASON_END_TURN") and not state.get("error"):
            outcome = "succeeded"
        else:
            outcome = "failed"
            error = error or state.get("error") or f"Bitto run ended with {reason}"
        state.update(status=outcome, stop_reason=reason, error=error, run_usage=payload.get("usage", {}), finished_at=time.time())

async def run(ctx) -> None:
    directory, state, request = ctx.directory, ctx.state, ctx.request
    save = ctx.save
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
        lock = shared.lock_path("bitto", sid).open("a")
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
                    received = time.time()
                    log.write(json.dumps({**message, "bridge_received_at": received}, ensure_ascii=False) + "\n")
                    consume_event(state, message)
                    if message.get("type") == PREFIX + "SessionRunEnded":
                        state["backend_completed_at"] = received
                    save(streaming=message.get("type") in {PREFIX + "SessionChatTextDelta", PREFIX + "SessionChatReasoningDelta"})
                    if state["status"] in TERMINAL:
                        log.flush()
    except Exception as e:
        state.update(status="interrupted" if state.get("status") in {"submitted", "running", "cancelling", "waiting_permission", "waiting_desktop_tool"} else "failed",
                     error=str(e), finished_at=time.time())
        save()
    finally:
        if lock:
            lock.close()
