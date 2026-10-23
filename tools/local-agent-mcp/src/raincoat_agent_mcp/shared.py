"""Persistent jobs and bounded completion waits shared by both runtimes."""
from __future__ import annotations
import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import uuid

STATE = Path(os.environ.get('LOCAL_AGENT_MCP_STATE_DIR', os.environ.get('BITTO_BRIDGE_STATE_DIR', '~/.local/state/bitto-agent-bridge'))).expanduser()
TERMINAL = {'succeeded', 'failed', 'cancelled', 'interrupted'}
ATTENTION = {'waiting_permission', 'waiting_desktop_tool'}


def read_json(path):
    return json.loads(Path(path).read_text())


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with open(temp, 'x', opener=lambda p, flags: os.open(p, flags, 0o600)) as f:
        json.dump(value, f, ensure_ascii=False)
    temp.replace(path)


def job_dir(job_id):
    if not re.fullmatch('[a-f0-9]{32}', job_id):
        raise ValueError('Invalid job_id')
    return STATE / 'jobs' / job_id


def lock_path(backend, session_id):
    root = STATE / 'locks'
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Keep mutual exclusion with workers started by the original Bitto bridge.
    if backend == 'bitto':
        return root / str(uuid.UUID(session_id))
    return root / (backend + '-' + hashlib.sha256(session_id.encode()).hexdigest())


def socket_path(job_id):
    # macOS sockaddr_un is short; do not put sockets under arbitrarily long STATE paths.
    root = Path('/private/tmp') / f'local-agent-mcp-{os.getuid()}'
    try:
        root.mkdir(mode=0o700)
    except FileExistsError:
        pass
    s = root.lstat()
    if not stat.S_ISDIR(s.st_mode) or s.st_uid != os.getuid() or stat.S_IMODE(s.st_mode) != 0o700:
        raise RuntimeError('Unsafe local completion socket directory')
    digest = hashlib.sha256((str(STATE.resolve()) + ':' + job_id).encode()).hexdigest()[:32]
    return root / (digest + '.sock')


def get_task(job_id):
    directory = job_dir(job_id)
    state = read_json(directory / 'state.json')
    state.setdefault('backend', 'bitto')  # v1 jobs did not have a backend tag.
    pid = state.get('worker_pid')
    if not pid and (directory / 'worker.json').exists():
        pid = read_json(directory / 'worker.json')['pid']
    if state['status'] not in TERMINAL and pid:
        try:
            os.kill(pid, 0)
            # Legacy workers may be unreaped children of a still-running MCP.
            probe = subprocess.run(['ps', '-p', str(pid), '-o', 'stat='], capture_output=True, text=True)
            if probe.returncode == 1 or probe.stdout.strip().startswith('Z'):
                raise ProcessLookupError
        except ProcessLookupError:
            state.update(status='interrupted', error='桥接 worker 已退出；后端任务可能仍在执行，请先检查会话，勿自动重提交。')
    return state


def ready(state):
    return state['status'] in TERMINAL | ATTENTION


def returned(state, transport):
    result = dict(state)
    result['returned_at'] = time.time()
    result['wait_transport'] = transport
    if result.get('backend_completed_at'):
        result['completion_delivery_ms'] = round(1000 * max(0, result['returned_at'] - result['backend_completed_at']), 3)
    if not ready(result):
        result['next'] = '立即调用 agent_wait_task(job_id, timeout_seconds=25) 持续有界等待；不要 sleep 或稀疏轮询。'
    return result


async def wait_task(job_id, timeout_seconds=25):
    if not 0 <= timeout_seconds <= 50:
        raise ValueError('wait timeout must be between 0 and 50 seconds')
    deadline = time.monotonic() + timeout_seconds
    while True:
        state = get_task(job_id)
        if ready(state) or time.monotonic() >= deadline:
            return returned(state, 'snapshot')
        remaining = deadline - time.monotonic()
        try:
            reader, writer = await asyncio.open_unix_connection(str(socket_path(job_id)), limit=16 * 1024 * 1024)
        except (FileNotFoundError, ConnectionRefusedError):
            # Covers worker startup and existing v1 jobs with no notification socket.
            await asyncio.sleep(min(0.05, remaining))
            continue
        try:
            writer.write(json.dumps({'timeout_seconds': remaining}).encode() + b'\n')
            await writer.drain()
            async with asyncio.timeout(remaining + 0.2):
                raw = await reader.readline()
            if raw:
                json.loads(raw)  # Only a notification crosses the socket, never the result body.
                return returned(get_task(job_id), 'unix_socket')
        except (TimeoutError, ConnectionResetError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()


class Worker:
    def __init__(self, job_id):
        self.job_id = job_id
        self.directory = job_dir(job_id)
        self.request = read_json(self.directory / 'request.json')
        self.state = read_json(self.directory / 'state.json')
        self.state.update(worker_pid=os.getpid(), status='starting')
        self.waiters = set()
        self.handlers = set()
        self.last_save = 0.0
        self.server = None
        self.path = socket_path(job_id)

    async def start(self):
        self.path.unlink(missing_ok=True)
        self.server = await asyncio.start_unix_server(self.handle_waiter, str(self.path), limit=1024)
        self.save()

    def save(self, *, streaming=False):
        now = time.monotonic()
        if streaming and now - self.last_save < 0.1:
            return
        self.last_save = now
        self.state['updated_at'] = time.time()
        if ready(self.state):
            self.state['persisted_at'] = self.state['updated_at']
        # Persist before signaling; waiting clients recheck after subscribing.
        atomic_json(self.directory / 'state.json', self.state)
        if ready(self.state):
            for event in self.waiters:
                event.set()

    async def handle_waiter(self, reader, writer):
        task = asyncio.current_task()
        self.handlers.add(task)
        event = asyncio.Event()
        self.waiters.add(event)
        try:
            async with asyncio.timeout(2):
                request = json.loads(await reader.readline())
            duration = max(0, min(float(request.get('timeout_seconds', 25)), 50))
            if not ready(self.state):
                try:
                    async with asyncio.timeout(duration):
                        await event.wait()
                except TimeoutError:
                    pass
            writer.write(b'{"state_available":true}\n')
            await writer.drain()
        except (ConnectionError, ValueError, TimeoutError):
            pass
        finally:
            self.waiters.discard(event)
            self.handlers.discard(task)
            writer.close()
            await writer.wait_closed()

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        for event in self.waiters:
            event.set()
        if self.handlers:
            await asyncio.gather(*list(self.handlers), return_exceptions=True)
        self.path.unlink(missing_ok=True)

    def log_event(self, message):
        message = {**message, 'bridge_received_at': time.time()}
        with open(self.directory / 'events.jsonl', 'a', opener=lambda p, flags: os.open(p, flags, 0o600)) as f:
            f.write(json.dumps(message, ensure_ascii=False) + '\n')

    def cancelled(self):
        return (self.directory / 'cancel.json').exists()
