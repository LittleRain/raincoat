"""Antigravity CLI adapter exposing the locally authenticated Antigravity agent as ``agy``."""
from __future__ import annotations

import asyncio
from contextlib import ExitStack
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from . import dependencies, shared

SANDBOXES = ('read-only', 'workspace-write', 'danger-full-access')


def status():
    binary = dependencies.agy_binary()
    return {
        'installed': bool(binary),
        'runtime': 'Antigravity CLI (agy headless) with saved local login',
        'execution_ready': bool(binary),
        'agy': binary,
        'desktop_task_visible': False,
        'default_model': '',
        'default_sandbox': 'read-only',
        'note': ('复用本机 Antigravity CLI 登录；agy 无头模式默认软拒绝写入类工具，'
                 '需要写文件时用 workspace-write 或 danger-full-access（两者都映射到 --dangerously-skip-permissions）。'
                 '未传 cwd 时在家目录执行。'),
    }


def authentication():
    binary = dependencies.agy_binary()
    if not binary:
        return {'authenticated': False, 'error': '未找到 agy；安装 Antigravity CLI（https://antigravity.google/cli）后运行一次 agy 登录。'}
    home = Path.home() / '.gemini/antigravity-cli'
    markers = (home / 'jetski_state.pbtxt', home / 'installation_id', home / 'presence', home / 'conversations')
    if any(marker.exists() for marker in markers):
        return {'authenticated': True, 'method': 'saved Antigravity login', 'verified': False}
    return {'authenticated': False, 'error': '未发现 Antigravity 登录凭据；先在终端运行 agy 完成登录。'}


def command(request):
    sandbox = request.get('sandbox') or 'read-only'
    args = [
        dependencies.agy_binary() or 'agy',
        # Prompt 走 stdin（--input-format text），不出现在 argv 里。
        '--output-format', 'stream-json', '--input-format', 'text',
    ]
    if request.get('model'):
        args.extend(['--model', request['model']])
    if request.get('session_id'):
        args.extend(['--conversation', request['session_id']])
    if sandbox != 'read-only':
        # Antigravity 目前只有两档：默认 request-review（headless 下软拒绝写入）与
        # --dangerously-skip-permissions（always-proceed）。--mode auto 对该账号不可用，
        # permissions.allow 规则经 --settings 不生效，因此写权限统一走 skip-permissions。
        args.append('--dangerously-skip-permissions')
    return args


def _consume_step(state, step):
    state['status'] = 'running'
    stage = step.get('state')
    delta = step.get('text_delta') or ''
    step_type = step.get('step_type')
    if step_type == 'agent_response':
        if delta:
            state['streaming_text'] = state.get('streaming_text', '') + delta
        return
    if step_type not in {'tool', 'checkpoint'}:
        return
    index = step.get('step_index')
    info = step.get('tool_info') or {}
    call = next((entry for entry in state['tool_calls'] if entry['id'] == index), None)
    if call is None:
        call = {'id': index, 'name': info.get('tool_name') or step_type, 'status': 'running'}
        state['tool_calls'].append(call)
    if info.get('tool_name'):
        call['name'] = info['tool_name']
    if delta:
        call['result'] = ((call.get('result') or '') + delta)[-4000:]
    if stage == 'ACTIVE':
        call['status'] = 'running'
    elif stage == 'DONE':
        verdict = str(info.get('status') or '').upper()
        call['status'] = 'failed' if verdict in {'FAILED', 'ERROR', 'DENIED'} else 'succeeded'


def _denial_error(denied):
    names = sorted({str(item.get('action') or item.get('display_name') or 'tool')
                    for item in denied if isinstance(item, dict)}) or ['tool']
    return ('Antigravity 拒绝了 ' + ', '.join(names) + '：headless 模式无法弹出授权，任务没有执行。'
            '需要写文件或执行命令时，用 sandbox=workspace-write 重新提交。')


def consume_event(state, event):
    kind = event.get('event')
    if kind == 'init':
        info = event.get('init') or {}
        state.update(
            status='running',
            session_id=event.get('conversation_id') or info.get('conversation_id') or state.get('session_id'),
            provider='agy',
            permission_mode=info.get('permission_mode'),
        )
        if info.get('model'):
            state['model'] = info['model']
        if isinstance(info.get('tools'), list):
            state['tool_count'] = len(info['tools'])
    elif kind == 'step_update':
        _consume_step(state, event.get('step_update') or {})
    elif kind == 'result':
        result = event.get('result') or {}
        denied = result.get('denied_actions') or []
        text = result.get('response') or state.get('streaming_text') or ''
        finished = time.time()
        state.update(
            text=text,
            run_usage=result.get('usage') or {},
            backend_completed_at=finished,
            finished_at=finished,
        )
        state.pop('streaming_text', None)
        if result.get('conversation_id'):
            state['session_id'] = result['conversation_id']
        if denied:
            state['denied_actions'] = denied
        if result.get('status') == 'SUCCESS':
            if denied and not text.strip():
                state.update(status='failed', error=_denial_error(denied))
            else:
                state['status'] = 'succeeded'
        else:
            error = result.get('error') or result.get('status') or 'Antigravity run failed'
            state.update(status='failed', error=str(error))


async def run(ctx):
    request, state = ctx.request, ctx.state
    lock = None
    process = None
    reader_task = None
    try:
        if request.get('session_id'):
            lock = await shared.acquire_session_lock(ctx, 'agy', request['session_id'])
        shared.atomic_json(ctx.directory / 'launch.json', {
            'command': command(request), 'sandbox': request.get('sandbox') or 'read-only',
            'resume': bool(request.get('session_id')),
        })
        if ctx.cancelled():
            state.update(status='cancelled', finished_at=time.time())
            ctx.save()
            return
        # agy 使用本机保存的登录；清掉 API key 类环境变量，避免覆盖已有凭据。
        env = {key: value for key, value in os.environ.items()
               if key not in {'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'GOOGLE_GENAI_API_KEY'}}
        with ExitStack() as stack:
            log = stack.enter_context(open(ctx.directory / 'runtime.stderr.log', 'a',
                                           opener=lambda path, flags: os.open(path, flags, 0o600)))
            stdin = asyncio.subprocess.PIPE
            if shared.IS_WINDOWS:
                stdin = stack.enter_context(tempfile.TemporaryFile())
                stdin.write(request['prompt'].encode())
                stdin.seek(0)
            process = await asyncio.create_subprocess_exec(
                *command(request), stdin=stdin, stdout=asyncio.subprocess.PIPE,
                stderr=log, cwd=request.get('cwd') or str(Path.home()),
                **shared.spawn_options(), limit=16 * 1024 * 1024, env=env,
            )
        if process.stdin:
            process.stdin.write(request['prompt'].encode())
            await process.stdin.drain()
            process.stdin.close()
        state.update(status='submitted', runtime_pid=process.pid,
                     sandbox=request.get('sandbox') or 'read-only')
        if (request.get('sandbox') or 'read-only') != 'read-only':
            state['sandbox_effective'] = 'danger-full-access'
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
                raise RuntimeError(
                    f'Antigravity CLI exited before final result (exit code {process.returncode}); '
                    'inspect runtime.stderr.log')
            reader_task = asyncio.create_task(process.stdout.readline())
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            ctx.log_event(event)
            consume_event(state, event)
            if event.get('event') == 'init' and lock is None and state.get('session_id'):
                # 会话 ID 只在续接锁持有后对外可见。
                lock = await shared.acquire_session_lock(ctx, 'agy', state['session_id'])
            ctx.save()
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
