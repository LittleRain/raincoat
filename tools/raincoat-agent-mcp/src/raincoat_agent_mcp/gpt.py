"""Codex CLI adapter exposing the locally authenticated GPT agent as ``gpt``."""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import subprocess
import time

from . import dependencies, shared


def status():
    binary = dependencies.codex_binary()
    return {
        'installed': bool(binary),
        'runtime': 'Codex CLI with saved local login',
        'execution_ready': bool(binary),
        'codex': binary,
        'desktop_task_visible': False,
        'default_model': '',
        'default_sandbox': 'read-only',
        'note': '复用本机 Codex CLI 登录；默认使用内置 GPT 模型和只读沙箱。未传 cwd 时在家目录执行。',
    }


def authentication():
    binary = dependencies.codex_binary()
    if not binary:
        return {'authenticated': False, 'error': '未找到 codex；安装 Codex CLI 并执行 codex login。'}
    try:
        result = subprocess.run([binary, 'login', 'status'], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as error:
        return {'authenticated': False, 'error': str(error)}
    detail = (result.stdout + result.stderr).strip()
    return {
        'authenticated': result.returncode == 0,
        'method': 'ChatGPT' if 'ChatGPT' in detail else 'saved Codex login' if result.returncode == 0 else '',
        **({} if result.returncode == 0 else {'error': detail or 'Codex 未登录；请执行 codex login。'}),
    }


def command(request):
    args = [
        dependencies.codex_binary() or 'codex', 'exec', '--json', '--skip-git-repo-check',
        # Do not recursively load this bridge or other user-configured MCP servers/hooks.
        # CODEX_HOME authentication remains available with this flag.
        '--ignore-user-config', '--sandbox', request.get('sandbox') or 'read-only',
        '--cd', request.get('cwd') or str(Path.home()),
    ]
    if request.get('model'):
        args.extend(['--model', request['model']])
    if request.get('session_id'):
        args.extend(['resume', request['session_id']])
    args.append('-')
    return args


def _tool_name(item):
    kind = item.get('type', 'tool')
    if kind == 'command_execution':
        return 'Bash'
    if kind == 'mcp_tool_call':
        return f"{item.get('server', 'MCP')}/{item.get('tool', 'tool')}"
    return {'file_change': 'FileChange', 'web_search': 'WebSearch'}.get(kind, kind)


def _tool_result(item):
    for key in ('aggregated_output', 'result', 'error', 'changes', 'query'):
        if item.get(key) not in (None, '', []):
            return str(item[key])[:4000]
    return ''


def _consume_item(state, item, started=False):
    if item.get('type') == 'agent_message':
        if not started:
            state['text'] = item.get('text', '')
        return
    if item.get('type') in {'reasoning', 'plan'}:
        return
    item_id = item.get('id')
    if not item_id:
        return
    call = next((entry for entry in state['tool_calls'] if entry['id'] == item_id), None)
    if call is None:
        call = {'id': item_id, 'name': _tool_name(item), 'status': 'running'}
        if item.get('command'):
            call['command'] = item['command']
        state['tool_calls'].append(call)
    if not started:
        status = item.get('status', 'completed')
        call.update(
            status='failed' if status in {'failed', 'error'} or item.get('exit_code') not in (None, 0) else 'succeeded',
            result=_tool_result(item),
        )
        if item.get('exit_code') is not None:
            call['exit_code'] = item['exit_code']


def consume_event(state, event):
    kind = event.get('type')
    if kind == 'thread.started':
        state.update(status='running', session_id=event['thread_id'], provider='codex')
    elif kind == 'turn.started':
        state['status'] = 'running'
    elif kind in {'item.started', 'item.completed'}:
        _consume_item(state, event.get('item', {}), started=kind == 'item.started')
    elif kind == 'turn.completed':
        state.update(
            status='succeeded', run_usage=event.get('usage', {}),
            backend_completed_at=time.time(), finished_at=time.time(),
        )
    elif kind in {'turn.failed', 'error'}:
        error = event.get('error', event.get('message', kind))
        if isinstance(error, dict):
            error = error.get('message') or json.dumps(error, ensure_ascii=False)
        state.update(status='failed', error=str(error), backend_completed_at=time.time(), finished_at=time.time())


async def run(ctx):
    request, state = ctx.request, ctx.state
    lock = None
    process = None
    reader_task = None
    try:
        if request.get('session_id'):
            lock = await shared.acquire_session_lock(ctx, 'gpt', request['session_id'])
        shared.atomic_json(ctx.directory / 'launch.json', {
            'command': command(request), 'sandbox': request.get('sandbox') or 'read-only',
            'resume': bool(request.get('session_id')),
        })
        if ctx.cancelled():
            state.update(status='cancelled', finished_at=time.time())
            ctx.save()
            return
        env = {key: value for key, value in os.environ.items() if key not in {'CODEX_API_KEY', 'OPENAI_API_KEY'}}
        with open(ctx.directory / 'runtime.stderr.log', 'a', opener=lambda path, flags: os.open(path, flags, 0o600)) as log:
            process = await asyncio.create_subprocess_exec(
                *command(request), stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=log, start_new_session=True, limit=16 * 1024 * 1024, env=env,
            )
        process.stdin.write(request['prompt'].encode())
        await process.stdin.drain()
        process.stdin.close()
        state.update(status='submitted', runtime_pid=process.pid, sandbox=request.get('sandbox') or 'read-only')
        ctx.save()
        deadline = time.monotonic() + request['timeout_seconds']
        reader_task = asyncio.create_task(process.stdout.readline())
        while state['status'] not in shared.TERMINAL:
            if ctx.cancelled() or time.monotonic() >= deadline:
                expired = time.monotonic() >= deadline
                state['status'] = 'cancelling'
                ctx.save()
                await shared.stop_process(process)
                state.update(status='cancelled', timeout_expired=expired, finished_at=time.time())
                ctx.save()
                return
            done, _ = await asyncio.wait({reader_task}, timeout=0.05)
            if not done:
                continue
            line = reader_task.result()
            if not line:
                raise RuntimeError(f'Codex CLI exited before final turn result (exit code {process.returncode}); inspect runtime.stderr.log')
            reader_task = asyncio.create_task(process.stdout.readline())
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            ctx.log_event(event)
            consume_event(state, event)
            if event.get('type') == 'thread.started' and lock is None:
                # Do not expose the new session id until its resume lock is held.
                lock = await shared.acquire_session_lock(ctx, 'gpt', state['session_id'])
            ctx.save()
        # Publish the final turn before CLI housekeeping and process reaping.
    finally:
        if reader_task:
            reader_task.cancel()
            await asyncio.gather(reader_task, return_exceptions=True)
        try:
            if process:
                await shared.stop_process(process)
        finally:
            if lock:
                lock.close()
