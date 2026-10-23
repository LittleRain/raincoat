"""One local MCP delegates whole tasks to Bitto or WorkBuddy."""
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
from . import bitto, shared

Backend = Literal['bitto', 'workbuddy']


def compact(state, include_details=False):
    result = dict(state)
    result.setdefault('backend', 'bitto')
    result['result_path'] = str(shared.job_dir(result['job_id']) / 'state.json')
    if not include_details:
        calls = result.get('tool_calls', [])
        result['tool_call_count'] = len(calls)
        result['tool_calls'] = [{**x, 'result':str(x.get('result',''))[:1000]} for x in calls[-4:]]
        usage = result.get('message_usage', [])
        result['message_usage_count'] = len(usage)
        result['message_usage'] = usage[-3:]
        result.pop('streaming_text', None)
        if len(result.get('text','')) > 32000:
            result['text'] = result['text'][:32000]
            result['text_truncated'] = True
    return result


def status(backend: Backend):
    if backend == 'bitto':
        bitto.discover_ws(); bitto.token()
        return {'backend':'bitto','runtime':'existing Bitto local sidecar','ws_url':bitto.discover_ws(),
                'default_model':bitto.settings_model(),'desktop_task_visible':True,
                'note':'本地发现检查；认证在提交时验证。'}
    if backend == 'workbuddy':
        from . import workbuddy
        return {'backend':'workbuddy', **workbuddy.status()}
    raise ValueError('backend must be bitto or workbuddy')


def submit_task(backend: Backend, prompt: str, title='本地 Agent 委派任务', project='default', model='',
                cwd='', session_id='', timeout_seconds=10800, allowed_tools=None):
    if backend not in ('bitto','workbuddy'):
        raise ValueError('backend must be bitto or workbuddy')
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
        raise ValueError('allowed_tools applies only to WorkBuddy; Bitto uses its own permission requests')
    request = dict(backend=backend,prompt=prompt,title=title,project=project,model=model,
                   cwd=str(Path(cwd).expanduser()) if cwd else '',session_id=session_id,
                   timeout_seconds=timeout_seconds,allowed_tools=allowed_tools or [])
    if backend == 'bitto':
        request.update(ws_url=bitto.discover_ws(), model=model or bitto.settings_model())
        bitto.token()
    else:
        request['model'] = model or 'deepseek-v4.1-flash'
        from . import workbuddy
        discovery = workbuddy.status()
        if not discovery['installed']:
            raise RuntimeError('WorkBuddy not installed')
        if not discovery['execution_ready']:
            raise RuntimeError(discovery['note'])
        workbuddy.validate_model(request['model'])
    job_id = uuid.uuid4().hex
    directory = shared.job_dir(job_id)
    shared.atomic_json(directory / 'request.json', request)
    state = dict(job_id=job_id,backend=backend,status='queued',session_id=session_id,model=request['model'],
                 created_at=time.time(),text='',tool_calls=[],message_usage=[],event_log=str(directory/'events.jsonl'))
    shared.atomic_json(directory/'state.json',state)
    with open(directory/'worker.log','a',opener=lambda p,flags:os.open(p,flags,0o600)) as log:
        process = subprocess.Popen([sys.executable,'-m','raincoat_agent_mcp','_worker',job_id],
                                   stdin=subprocess.DEVNULL,stdout=log,stderr=log,start_new_session=True,
                                   env={**os.environ,'PYTHONPATH':str(Path(__file__).resolve().parents[1])+os.pathsep+os.environ.get('PYTHONPATH','')})
    threading.Thread(target=process.wait, daemon=True, name='agent-worker-reaper').start()
    shared.atomic_json(directory/'worker.json',{'pid':process.pid})
    return state


async def submit_and_wait(backend, prompt, *, wait_seconds=25, **kwargs):
    if not 0 <= wait_seconds <= 50:
        raise ValueError('wait_seconds must be between 0 and 50')
    state = await asyncio.to_thread(submit_task,backend,prompt,**kwargs)
    return compact(await shared.wait_task(state['job_id'],wait_seconds))


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
        raise ValueError('WorkBuddy 非交互授权需提交时明确 allowed_tools；不支持事后自动扩大权限')
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
        else:
            from . import workbuddy
            await workbuddy.run(ctx)
    except Exception as e:
        if ctx.state['status'] not in shared.TERMINAL:
            ctx.state.update(status='interrupted' if ctx.state.get('status') in {'submitted','running','cancelling'} else 'failed',
                             error=str(e),finished_at=time.time());ctx.save()
    finally:
        await ctx.close()


def serve_mcp():
    from mcp.server.fastmcp import FastMCP
    mcp=FastMCP('local_agents',log_level='WARNING',instructions='将完整任务交给所选 backend 的原生运行时。agent_submit_task 默认等待25秒，未完成时立即继续调用 agent_wait_task；不要 sleep、指数退避或稀疏轮询。单次等待超时不取消任务。MCP 不会在调用结束后主动唤醒闲置模型，需保持有界等待。WorkBuddy 工具权限通过 allowed_tools 按用户授权显式给出，不会自动放宽权限。历史 Bitto job_id 仍可查询。')
    @mcp.tool()
    def agent_status(backend: Backend) -> dict:
        """检查所选本地运行时；不进行模型调用。WorkBuddy CLI 任务不会显示在桌面任务列表。"""
        return status(backend)
    @mcp.tool()
    async def agent_submit_task(backend: Backend,prompt:str,title:str='本地 Agent 委派任务',project:str='default',model:str='',cwd:str='',session_id:str='',timeout_seconds:int=10800,wait_seconds:float=25,allowed_tools:list[str]|None=None) -> dict:
        """交给 bitto 或 workbuddy 原生 Agent 执行。默认等待25秒，完成即返回结果；未完成则保存job_id，立即调用 agent_wait_task，勿 sleep。执行超时与本次等待超时独立。WorkBuddy 的 allowed_tools 例 ['Bash(python3:*)']，仅按用户授权设置。"""
        return await submit_and_wait(backend,prompt,title=title,project=project,model=model,cwd=cwd,session_id=session_id,timeout_seconds=timeout_seconds,wait_seconds=wait_seconds,allowed_tools=allowed_tools)
    @mcp.tool()
    async def agent_wait_task(job_id:str,timeout_seconds:float=25,include_details:bool=False) -> dict:
        """保持等待，后端一完成或需要授权就立即返回。等待超时不取消任务；未完成时立即再次调用本工具，勿 sleep。"""
        return compact(await shared.wait_task(job_id,timeout_seconds),include_details)
    @mcp.tool()
    def agent_get_task(job_id:str,include_details:bool=False) -> dict:
        """立即读取状态快照。持续等待结果请用 agent_wait_task。默认省略大量工具历史，完整结果见 result_path。"""
        return compact(shared.returned(shared.get_task(job_id),'snapshot'),include_details)
    @mcp.tool()
    def agent_cancel_task(job_id:str) -> dict:
        """请求停止任务；之后 wait_task 等待实际终止确认。"""
        return cancel_task(job_id)
    @mcp.tool()
    def agent_respond_permission(job_id:str,request_id:str,allow:bool) -> dict:
        """回答 Bitto 当前工具授权；仅在已有用户授权时允许，不记住全局授权。"""
        return respond_permission(job_id,request_id,allow)
    # The old tools stay in this one server so existing prompts and job IDs keep working.
    @mcp.tool()
    def bitto_status() -> dict:
        """兼容旧 Bitto 工具名；同 agent_status(backend='bitto')。"""
        return status('bitto')
    @mcp.tool()
    async def bitto_submit_task(prompt:str,title:str='本地 Agent 委派任务',project:str='default',model:str='',cwd:str='',session_id:str='',timeout_seconds:int=10800,wait_seconds:float=25) -> dict:
        """兼容旧入口；现在默认等待25秒，完成立即返回，未完成请调用 agent_wait_task。"""
        return await submit_and_wait('bitto',prompt,title=title,project=project,model=model,cwd=cwd,session_id=session_id,timeout_seconds=timeout_seconds,wait_seconds=wait_seconds)
    @mcp.tool()
    async def bitto_get_task(job_id:str,wait_seconds:float=25) -> dict:
        """兼容旧入口并改为有界等待；完成立即返回，未完成时立即继续调用。"""
        state=shared.get_task(job_id)
        if state['backend']!='bitto':raise ValueError('This job belongs to WorkBuddy')
        return compact(await shared.wait_task(job_id,wait_seconds))
    mcp.add_tool(agent_cancel_task,name='bitto_cancel_task')
    mcp.add_tool(agent_respond_permission,name='bitto_respond_permission')
    mcp.run(transport='stdio')


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('mcp')
    s=sub.add_parser('status');s.add_argument('backend',choices=['bitto','workbuddy'])
    s=sub.add_parser('submit');s.add_argument('backend',choices=['bitto','workbuddy']);s.add_argument('prompt',nargs='?',default='');s.add_argument('--prompt-file')
    for name,default in [('title','本地 Agent 委派任务'),('project','default'),('model',''),('cwd',''),('session-id','')]:s.add_argument('--'+name,default=default)
    s.add_argument('--timeout-seconds',type=int,default=10800);s.add_argument('--wait-seconds',type=float,default=25);s.add_argument('--allowed-tool',action='append',dest='allowed_tools')
    for name in ['get','wait','cancel','_worker']:
        s=sub.add_parser(name);s.add_argument('job_id')
        if name=='wait':s.add_argument('--timeout-seconds',type=float,default=25)
    a=vars(p.parse_args());command=a.pop('command')
    try:
        if command=='mcp':serve_mcp();return
        if command=='_worker':asyncio.run(run_worker(a['job_id']));return
        if command=='status':result=status(**a)
        elif command=='submit':
            file=a.pop('prompt_file')
            if file:a['prompt']=Path(file).read_text()
            backend=a.pop('backend');prompt=a.pop('prompt');result=asyncio.run(submit_and_wait(backend,prompt,**a))
        elif command=='wait':result=compact(asyncio.run(shared.wait_task(**a)))
        elif command=='get':result=compact(shared.get_task(a['job_id']))
        else:result=cancel_task(a['job_id'])
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except Exception as e:
        print(json.dumps({'error':str(e)},ensure_ascii=False),file=sys.stderr);sys.exit(1)

if __name__=='__main__':main()
