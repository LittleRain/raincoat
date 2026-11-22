"""One local MCP delegates whole tasks to Bitto, WorkBuddy or GPT/Codex."""
from __future__ import annotations
import argparse
import asyncio
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time
import threading
from typing import Literal
import uuid
from . import bitto, management, shared

Backend = Literal['bitto', 'workbuddy', 'gpt', 'agy', 'codex']
BACKEND_NAMES = (*management.BACKENDS, 'codex')


def compact(state, include_details=False, *, legacy=False):
    result = dict(state)
    result.setdefault('backend', 'bitto')
    result['result_path'] = str(shared.job_dir(result['job_id']) / 'state.json')
    if not include_details:
        calls = result.pop('tool_calls', [])
        result['tool_call_count'] = len(calls)
        usage = result.pop('message_usage', [])
        result['message_usage_count'] = len(usage)
        if legacy:
            result['tool_calls'] = [{**x, 'result':str(x.get('result',''))[:1000]} for x in calls[-4:]]
            result['message_usage'] = usage[-3:]
        result.pop('streaming_text', None)
        if len(result.get('text','')) > 32000:
            result['text'] = result['text'][:32000]
            result['text_truncated'] = True
    return result


def status(backend: Backend | None = None):
    if backend is not None:
        return management.probe_backend(backend)
    return {'backends': {name: management.probe_backend(name) for name in management.BACKENDS}}


def resume_options(job_id):
    state = shared.get_task(job_id)
    if state['status'] == 'interrupted':
        raise ValueError('原任务状态不确定，请先在后端检查原会话。')
    if state['status'] not in shared.TERMINAL:
        raise ValueError('原任务仍在执行或等待授权，结束后再续接。')
    session_id = state.get('session_id')
    if not session_id:
        raise ValueError('原任务没有可续接的会话 ID。')
    try:
        original = shared.read_json(shared.job_dir(job_id) / 'request.json')
    except FileNotFoundError:
        raise ValueError('缺少原任务的请求记录，无法确认目录和权限。') from None
    if 'cwd' not in original:
        raise ValueError('缺少原任务的工作目录记录，无法安全续接。')
    return {
        'backend': state['backend'], 'session_id': session_id, 'cwd': original['cwd'],
        'title': original.get('title', '本地 Agent 委派任务'),
        'project': original.get('project', 'default'),
        'model': original.get('model') or state.get('model') or '',
        'allowed_tools': original.get('allowed_tools'), 'sandbox': original.get('sandbox', ''),
    }


def submit_task(backend: Backend, prompt: str, title='本地 Agent 委派任务', project='default', model='',
                cwd='', session_id='', timeout_seconds=10800, allowed_tools=None, sandbox=''):
    backend = management.canonical_backend(backend)
    if not prompt.strip():
        raise ValueError('prompt must not be empty')
    if not 1 <= timeout_seconds <= 86400:
        raise ValueError('execution timeout must be between 1 and 86400 seconds')
    if session_id:
        uuid.UUID(session_id)
    if cwd and (not Path(cwd).expanduser().is_absolute() or not Path(cwd).expanduser().is_dir()):
        raise ValueError('cwd must be an existing absolute directory')
    if allowed_tools and (not isinstance(allowed_tools,list) or any(not isinstance(x,str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*(?:\([^\r\n]*\))?',x) for x in allowed_tools)):
        raise ValueError('allowed_tools must contain explicit tool names or Tool(rule) patterns')
    if allowed_tools and backend != 'workbuddy':
        raise ValueError('allowed_tools applies only to WorkBuddy; use sandbox to authorize GPT/Antigravity file and command access')
    if sandbox and (backend not in {'gpt','agy'} or sandbox not in {'read-only','workspace-write','danger-full-access'}):
        raise ValueError('sandbox applies only to GPT and Antigravity: read-only, workspace-write or danger-full-access')
    effective_cwd = str(Path(cwd).expanduser()) if cwd else ('' if backend == 'bitto' else str(Path.home()))
    request = dict(backend=backend,prompt=prompt,title=title,project=project,model=model,
                   cwd=effective_cwd,session_id=session_id,
                   timeout_seconds=timeout_seconds,allowed_tools=allowed_tools or [],
                   sandbox=sandbox or ('read-only' if backend in {'gpt','agy'} else ''))
    if backend == 'bitto':
        request.update(ws_url=bitto.discover_ws(), model=model or bitto.settings_model())
        bitto.token()
    elif backend == 'workbuddy':
        request['model'] = model or 'deepseek-v4.1-flash'
        from . import workbuddy
        discovery = workbuddy.status()
        if not discovery['installed']:
            raise RuntimeError('WorkBuddy not installed')
        if not discovery['execution_ready']:
            raise RuntimeError(discovery['note'])
        workbuddy.validate_model(request['model'])
    elif backend == 'gpt':
        from . import gpt
        discovery = gpt.status()
        if not discovery['execution_ready']:
            raise RuntimeError('Codex CLI not installed; install codex and run codex login')
    else:
        from . import agy
        discovery = agy.status()
        if not discovery['execution_ready']:
            raise RuntimeError('Antigravity CLI not installed; install agy from https://antigravity.google/cli and sign in')
    job_id = uuid.uuid4().hex
    directory = shared.job_dir(job_id)
    shared.atomic_json(directory / 'request.json', request)
    state = dict(job_id=job_id,backend=backend,status='queued',session_id=session_id,model=request['model'],
                 created_at=time.time(),text='',tool_calls=[],message_usage=[],event_log=str(directory/'events.jsonl'))
    shared.atomic_json(directory/'state.json',state)
    with open(directory/'worker.log','a',opener=lambda p,flags:os.open(p,flags,0o600)) as log:
        process = subprocess.Popen([sys.executable,'-m','raincoat_buck','_worker',job_id],
                                   stdin=subprocess.DEVNULL,stdout=log,stderr=log,**shared.spawn_options(),
                                   env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])+os.pathsep+os.environ.get('PYTHONPATH','')})
    threading.Thread(target=process.wait, daemon=True, name='agent-worker-reaper').start()
    shared.atomic_json(directory/'worker.json',{'pid':process.pid})
    return state


async def submit_and_wait(backend, prompt, *, wait_seconds=25, resume_from_job_id='', legacy=False, **kwargs):
    if not 0 <= wait_seconds <= 50:
        raise ValueError('wait_seconds must be between 0 and 50')
    if resume_from_job_id:
        if backend is not None or any(kwargs.get(name) for name in (
            'title', 'project', 'model', 'cwd', 'session_id', 'allowed_tools', 'sandbox',
        )):
            raise ValueError('按任务 ID 续接时只传新指令和等待或执行超时，沿用原后端、目录和权限。')
        original = await asyncio.to_thread(resume_options, resume_from_job_id)
        backend = original.pop('backend')
        kwargs.update(original)
    if backend is None:
        raise ValueError('新任务须指定 backend；续接任务可使用 resume_from_job_id。')
    kwargs.setdefault('title', '本地 Agent 委派任务')
    kwargs.setdefault('project', 'default')
    state = await asyncio.to_thread(submit_task, backend, prompt, **kwargs)
    return compact(await shared.wait_task(state['job_id'], wait_seconds), legacy=legacy)


def cancel_task(job_id):
    state = shared.get_task(job_id)
    if state['status'] in shared.TERMINAL:
        return compact(state)
    shared.atomic_json(shared.job_dir(job_id)/'cancel.json',{'requested_at':time.time()})
    return {'job_id':job_id,'backend':state['backend'],'status':'cancellation_requested',
            'next':'调用 agent_wait_task 等待实际终止确认。'}


def respond_permission(job_id,request_id,allow):
    state = shared.get_task(job_id)
    if state['backend'] != 'bitto':
        raise ValueError('仅 Bitto 支持交互授权；WorkBuddy 使用 allowed_tools，GPT 与 Antigravity 使用 sandbox，均需提交时明确授权')
    pending = state.get('permission',{})
    if state['status'] != 'waiting_permission' or pending.get('requestId',pending.get('request_id')) != request_id:
        raise ValueError('No matching pending permission request')
    shared.atomic_json(shared.job_dir(job_id)/'permission-response.json',{'requestId':request_id,'allow':allow,'remember':False})
    return {'job_id':job_id,'status':'permission_response_queued'}


async def run_worker(job_id):
    ctx = shared.Worker(job_id)
    await ctx.start()
    try:
        if ctx.cancelled():
            ctx.state.update(status='cancelled',finished_at=time.time());ctx.save();return
        if ctx.request['backend'] == 'bitto':
            await bitto.run(ctx)
        elif ctx.request['backend'] == 'workbuddy':
            from . import workbuddy
            await workbuddy.run(ctx)
        elif ctx.request['backend'] == 'gpt':
            from . import gpt
            await gpt.run(ctx)
        else:
            from . import agy
            await agy.run(ctx)
    except Exception as e:
        if ctx.state['status'] not in shared.TERMINAL:
            ctx.state.update(status='interrupted' if ctx.state.get('status') in {'submitted','running','cancelling'} else 'failed',
                             error=str(e),finished_at=time.time());ctx.save()
    finally:
        await ctx.close()


def serve_mcp():
    from mcp.server.fastmcp import FastMCP
    legacy = os.environ.get('LOCAL_AGENT_MCP_LEGACY_TOOLS') == '1'
    mcp = FastMCP('buck', log_level='WARNING', instructions=(
        'Buck 是队首：调用方只需面对它一个，由它为每个任务挑选最合适的本机 agent。'
        '用 agent_status 发现可用后端（backend 可选 bitto、workbuddy、codex 即 gpt、agy 即 Antigravity）；'
        '不确定谁最合适时先 agent_status 看可用性和登录状态，再 agent_submit_task 派活。'
        'agent_submit_task 接受 bitto、workbuddy、codex（gpt）或 agy（Antigravity CLI）。'
        '提交默认等待 25 秒，wait_seconds=0 立即返回任务快照。'
        '需要取回结果时继续调用 agent_wait_task；等待超时不取消任务。'
        '按原 job_id 续接时只传 resume_from_job_id 和新指令，原目录和权限沿用。'
        'Codex 与 Antigravity 默认只读，写文件需显式授予 workspace-write 或 danger-full-access；WorkBuddy 工具通过 allowed_tools 授权。'
    ))
    @mcp.tool()
    async def agent_status(backend: Backend | None = None) -> dict:
        """只读检查本地后端。省略 backend 时返回所有后端及其可用性和登录状态。"""
        return await asyncio.to_thread(status, backend)
    @mcp.tool()
    async def agent_submit_task(
        prompt: str, backend: Backend | None = None, cwd: str = '', sandbox: str = '',
        allowed_tools: list[str] | None = None, resume_from_job_id: str = '',
        wait_seconds: float = 25, timeout_seconds: int = 10800,
        model: str = '', title: str | None = None, project: str | None = None, session_id: str = '',
    ) -> dict:
        """新任务指定 backend 和 cwd。续接传 resume_from_job_id 和新指令。wait_seconds=0 立即返回。"""
        bitto_options = {key: value for key, value in {'title': title, 'project': project}.items()
                         if value is not None}
        return await submit_and_wait(
            backend, prompt, cwd=cwd, sandbox=sandbox, allowed_tools=allowed_tools,
            resume_from_job_id=resume_from_job_id, wait_seconds=wait_seconds,
            timeout_seconds=timeout_seconds, model=model, session_id=session_id,
            legacy=legacy, **bitto_options,
        )
    @mcp.tool()
    async def agent_wait_task(job_id:str,timeout_seconds:float=25,include_details:bool=False) -> dict:
        """timeout_seconds=0 立即查询；正数等到完成、需授权或超时。完整结果见 result_path。"""
        return compact(await shared.wait_task(job_id,timeout_seconds),include_details,legacy=legacy)
    @mcp.tool()
    def agent_cancel_task(job_id:str) -> dict:
        """请求停止任务；之后 wait_task 等待实际终止确认。"""
        return cancel_task(job_id)
    @mcp.tool()
    def agent_respond_permission(job_id:str,request_id:str,allow:bool) -> dict:
        """回答 Bitto 当前工具授权；仅在已有用户授权时允许，不记住全局授权。"""
        return respond_permission(job_id,request_id,allow)
    if legacy:
        @mcp.tool()
        async def agent_get_task(job_id: str, include_details: bool = False) -> dict:
            """兼容旧查询入口。同 agent_wait_task(timeout_seconds=0)。"""
            return await agent_wait_task(job_id, 0, include_details)

        @mcp.tool()
        async def bitto_status() -> dict:
            """兼容旧 Bitto 检查。"""
            return await agent_status('bitto')

        @mcp.tool()
        async def bitto_submit_task(
            prompt: str, title: str = '本地 Agent 委派任务', project: str = 'default',
            model: str = '', cwd: str = '', session_id: str = '',
            timeout_seconds: int = 10800, wait_seconds: float = 25,
        ) -> dict:
            """兼容旧 Bitto 提交。"""
            return await agent_submit_task(
                prompt, 'bitto', title=title, project=project, model=model, cwd=cwd,
                session_id=session_id, timeout_seconds=timeout_seconds, wait_seconds=wait_seconds,
            )

        @mcp.tool()
        async def bitto_get_task(job_id: str, wait_seconds: float = 25) -> dict:
            """兼容旧 Bitto 等待。"""
            if shared.get_task(job_id)['backend'] != 'bitto':
                raise ValueError('This job does not belong to Bitto')
            return await agent_wait_task(job_id, wait_seconds)

        mcp.add_tool(agent_cancel_task, name='bitto_cancel_task')
        mcp.add_tool(agent_respond_permission, name='bitto_respond_permission')
    mcp.run(transport='stdio')


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('mcp')
    s=sub.add_parser('status');s.add_argument('backend',nargs='?',choices=BACKEND_NAMES)
    s=sub.add_parser('submit');s.add_argument('backend',choices=BACKEND_NAMES);s.add_argument('prompt',nargs='?',default='');s.add_argument('--prompt-file')
    for name,default in [('title','本地 Agent 委派任务'),('project','default'),('model',''),('cwd',''),('session-id','')]:s.add_argument('--'+name,default=default)
    s.add_argument('--timeout-seconds',type=int,default=10800);s.add_argument('--wait-seconds',type=float,default=25);s.add_argument('--allowed-tool',action='append',dest='allowed_tools')
    s.add_argument('--sandbox',choices=['read-only','workspace-write','danger-full-access'],default='')
    s = sub.add_parser('resume')
    s.add_argument('resume_from_job_id')
    s.add_argument('prompt', nargs='?', default='')
    s.add_argument('--prompt-file')
    s.add_argument('--timeout-seconds', type=int, default=10800)
    s.add_argument('--wait-seconds', type=float, default=25)
    for name in ['get','wait','cancel','_worker']:
        s=sub.add_parser(name);s.add_argument('job_id')
        if name=='wait':s.add_argument('--timeout-seconds',type=float,default=25)
    a=vars(p.parse_args());command=a.pop('command')
    try:
        if command=='mcp':serve_mcp();return
        if command=='_worker':asyncio.run(run_worker(a['job_id']));return
        if command=='status':result=status(**a)
        elif command in ('submit', 'resume'):
            file=a.pop('prompt_file')
            if file:a['prompt']=Path(file).read_text(encoding='utf-8')
            backend=a.pop('backend', None);prompt=a.pop('prompt');result=asyncio.run(submit_and_wait(backend,prompt,**a))
        elif command=='wait':result=compact(asyncio.run(shared.wait_task(**a)))
        elif command=='get':result=compact(shared.get_task(a['job_id']))
        else:result=cancel_task(a['job_id'])
        print(json.dumps(result,ensure_ascii=True,indent=2))
    except Exception as e:
        print(json.dumps({'error':str(e)},ensure_ascii=True),file=sys.stderr);sys.exit(1)

if __name__=='__main__':main()
