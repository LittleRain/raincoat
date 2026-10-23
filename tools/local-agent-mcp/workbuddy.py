"""WorkBuddy CLI adapter; authoritative result frames wake the shared waiters."""
from __future__ import annotations
import asyncio
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time
import uuid
import shared

APP = Path('/Applications/WorkBuddy.app')


def node_binary():
    candidate=os.environ.get('LOCAL_AGENT_NODE') or shutil.which('node')
    if not candidate:
        manifest=Path(__file__).with_name('install.json')
        if manifest.exists():candidate=shared.read_json(manifest).get('node')
    return candidate if candidate and Path(candidate).is_file() else None


def status():
    installed = (APP/'Contents/Resources/app.asar').is_file() and (APP/'Contents/MacOS/Electron').is_file()
    node = node_binary()
    return {'installed':installed,'runtime':'WorkBuddy bundled Agent CLI','execution_ready':bool(installed and node),
            'node':node,'desktop_task_visible':False,'default_model':'deepseek-v4.1-flash',
            'note':'本地安装检查；提交时只读获取现有登录凭证，过期则失败，不自动刷新。CLI 任务不进入桌面任务列表。'}


def validate_model(model):
    product = shared.read_json(Path.home()/'.workbuddy/cache/acc-product-config-v3.json')
    if product.get('endpoint') != 'https://www.workbuddy.cn':
        raise ValueError('Unexpected WorkBuddy endpoint')
    if model not in {x['id'] for x in product.get('models',[])}:
        raise ValueError('Use an official WorkBuddy model ID, e.g. deepseek-v4.1-flash')
    custom_path = Path.home()/'.workbuddy/models.json'
    if custom_path.exists():
        custom = shared.read_json(custom_path)
        entries = custom if isinstance(custom,list) else custom.get('models',[])
        if any(x.get('id') == model for x in entries):
            raise ValueError('Model is overridden by a custom route; choose an official WorkBuddy model')


def consume_event(state,event):
    kind = event.get('type')
    if kind == 'system' and event.get('subtype') == 'init':
        if event.get('apiKeySource') != 'www.workbuddy.cn':
            raise RuntimeError('CLI did not authenticate through www.workbuddy.cn')
        state.update(status='running',session_id=event['session_id'],provider='workbuddy',model=event.get('model',state['model']))
    elif kind == 'assistant':
        message=event.get('message',{})
        for content in message.get('content',[]):
            if content.get('type')=='text':state['text']=content.get('text','')
            if content.get('type')=='tool_use' and not any(x['id']==content['id'] for x in state['tool_calls']):
                state['tool_calls'].append({'id':content['id'],'name':content['name'],'status':'running'})
        if message.get('usage') and any(message['usage'].values()):
            state['message_usage'].append({'message_id':message.get('id'),**message['usage']})
    elif kind == 'user':
        for content in event.get('message',{}).get('content',[]):
            if content.get('type')=='tool_result':
                for call in state['tool_calls']:
                    if call['id']==content.get('tool_use_id'):
                        call.update(status='failed' if content.get('is_error') else 'succeeded',result=str(content.get('content',''))[:4000])
    elif kind=='result':
        denied=event.get('permission_denials',[])
        success=event.get('subtype')=='success' and not event.get('is_error') and not denied
        state.update(status='succeeded' if success else 'failed',text=event.get('result',state.get('text','')),
                     run_usage=event.get('usage',{}),model_usage=event.get('modelUsage',{}),permission_denials=denied,
                     backend_completed_at=time.time(),finished_at=time.time())
        if not success:
            state['error']='工具授权不足；按用户授权重新提交 allowed_tools。' if denied else str(event.get('errors') or event.get('result') or event.get('subtype'))
    elif kind=='bridge_error':
        raise RuntimeError(event.get('error','WorkBuddy runner failed'))
    elif kind=='bridge_exit' and state['status'] not in shared.TERMINAL:
        raise RuntimeError(f"CLI exited without a final result: {event.get('code')} {event.get('signal')}")


async def group_alive(group_id):
    # A leader may exit before its tools, and zombies cannot execute work.
    result=await asyncio.to_thread(subprocess.run,['ps','-axo','pgid=,stat='],capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Cannot verify WorkBuddy process group termination')
    return any(parts[0]==str(group_id) and not parts[1].startswith('Z')
               for line in result.stdout.splitlines() if len(parts:=line.split())==2)


async def stop_process(process):
    try:os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:
        await process.wait();return
    deadline=time.monotonic()+3
    while await group_alive(process.pid) and time.monotonic()<deadline:
        await asyncio.sleep(0.05)
    if await group_alive(process.pid):
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
    await process.wait()
    deadline=time.monotonic()+1
    while await group_alive(process.pid):
        if time.monotonic()>=deadline:
            raise RuntimeError('WorkBuddy descendants are still alive; cancellation not confirmed')
        await asyncio.sleep(0.05)


async def acquire_session_lock(ctx,sid):
    lock=shared.lock_path('workbuddy',sid).open('a+')
    deadline=time.monotonic()+5
    try:
        while True:
            try:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                lock.seek(0);lock.truncate();lock.write(ctx.job_id);lock.flush()
                return lock
            except BlockingIOError:
                lock.seek(0);previous=lock.read().strip()
                try:previous_state=shared.get_task(previous)
                except (ValueError,FileNotFoundError):previous_state={}
                if previous_state.get('status') not in shared.TERMINAL:
                    raise RuntimeError('该 WorkBuddy 会话已有桥接任务在执行。') from None
                if time.monotonic()>=deadline:
                    raise RuntimeError('前序 WorkBuddy 已完成但仍未释放会话，请稍后续接。') from None
                if ctx.cancelled():raise RuntimeError('Cancelled while waiting for completed session cleanup')
                await asyncio.sleep(0.05)
    except BaseException:
        lock.close();raise


async def run(ctx):
    request,state=ctx.request,ctx.state
    validate_model(request['model'])
    sid=request['session_id'] or str(uuid.uuid4())
    state['session_id']=sid
    lock=await acquire_session_lock(ctx,sid)
    process=None
    reader_task=None
    try:
        launch={**request,'session_id':sid,'resume':bool(request['session_id'])}
        shared.atomic_json(ctx.directory/'launch.json',launch)
        if ctx.cancelled():
            state.update(status='cancelled',finished_at=time.time());ctx.save();return
        with open(ctx.directory/'runtime.stderr.log','a',opener=lambda p,flags:os.open(p,flags,0o600)) as log:
            process=await asyncio.create_subprocess_exec(node_binary() or 'node',str(Path(__file__).with_suffix('.mjs')),str(ctx.directory/'launch.json'),
                stdout=asyncio.subprocess.PIPE,stderr=log,start_new_session=True,limit=16*1024*1024)
        state.update(status='submitted',runtime_pid=process.pid);ctx.save()
        deadline=time.monotonic()+request['timeout_seconds']
        reader_task=asyncio.create_task(process.stdout.readline())
        while state['status'] not in shared.TERMINAL:
            if ctx.cancelled() or time.monotonic()>=deadline:
                expired=time.monotonic()>=deadline
                state['status']='cancelling';ctx.save()
                await stop_process(process)
                state.update(status='cancelled',timeout_expired=expired,finished_at=time.time());ctx.save();return
            done,_=await asyncio.wait({reader_task},timeout=0.05)
            if not done:continue
            line=reader_task.result()
            if not line:raise RuntimeError('WorkBuddy CLI exited before final result; inspect runtime.stderr.log')
            reader_task=asyncio.create_task(process.stdout.readline())
            try:event=json.loads(line)
            except json.JSONDecodeError:continue
            ctx.log_event(event)
            consume_event(state,event)
            ctx.save()
        # Publish final state before CLI housekeeping, which may take seconds.
    finally:
        if reader_task:
            reader_task.cancel()
            await asyncio.gather(reader_task,return_exceptions=True)
        try:
            if process:await stop_process(process)
        finally:
            lock.close()
