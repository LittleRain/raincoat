"""Opt-in WorkBuddy resume and real command cancellation, after integration.py."""
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from integration import value
ROOT=Path(__file__).resolve().parents[1]

async def main(output):
    previous=json.loads((output/'verification.json').read_text())['result']
    params=StdioServerParameters(command=sys.executable,args=[os.environ.get('LOCAL_AGENT_TEST_ENTRY',str(ROOT/'bridge.py')),'mcp'],env={**os.environ,'LOCAL_AGENT_MCP_STATE_DIR':str(output/'state')})
    async with stdio_client(params) as (r,w),ClientSession(r,w) as session:
        await session.initialize()
        async def finish(result):
            while result['status'] not in {'succeeded','failed','interrupted','cancelled'}:
                result=value(await session.call_tool('agent_wait_task',{'job_id':result['job_id'],'timeout_seconds':25}))
            return result
        resume=value(await session.call_tool('agent_submit_task',{'backend':'workbuddy','session_id':previous['session_id'],'cwd':str(output),
            'prompt':f'继续上一轮验证。根据会话历史，把上一轮的 numbers 和 sum_of_squares 用一条 python3 命令写入 {output}/resume.json，重读校验。不要从旧文件读取来代替回忆，不执行其他命令。',
            'allowed_tools':['Bash(python3:*)'],'wait_seconds':25,'timeout_seconds':90}))
        resume=await finish(resume)
        assert resume['status']=='succeeded',resume
        assert json.loads((output/'resume.json').read_text())=={'numbers':[7,11,13],'sum_of_squares':339}
        assert resume['session_id']==previous['session_id']
        print(json.dumps({'resume':'passed','session_id':resume['session_id']}),flush=True)
        for name in ['cancel-child.pid','should-not-exist.txt']:(output/name).unlink(missing_ok=True)
        cancel=value(await session.call_tool('agent_submit_task',{'backend':'workbuddy','cwd':str(output),
            'prompt':f'这是取消功能验证，仅运行一条 python3 命令：先把 os.getpid() 写入 {output}/cancel-child.pid，再 time.sleep(30)，最后写入 {output}/should-not-exist.txt。不执行其他命令。',
            'allowed_tools':['Bash(python3:*)'],'wait_seconds':0,'timeout_seconds':90}))
        start=time.monotonic()
        pidfile=output/'cancel-child.pid'
        while not pidfile.exists():
            assert time.monotonic()-start<60,'Python cancellation command did not start'
            await asyncio.sleep(.1)
        pid=int(pidfile.read_text())
        value(await session.call_tool('agent_cancel_task',{'job_id':cancel['job_id']}))
        cancelled=await finish(cancel)
        assert cancelled['status']=='cancelled',cancelled
        alive=False
        try:os.kill(pid,0);alive=True
        except ProcessLookupError:pass
        assert not alive,f'Child {pid} survived cancellation'
        assert not (output/'should-not-exist.txt').exists()
        summary={'resume':resume,'cancel':cancelled,'cancelled_child_pid':pid,'child_alive':alive}
        (output/'lifecycle.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
        print(json.dumps({'cancellation':'passed','child_alive':alive,'evidence':str(output)}),flush=True)

if __name__=='__main__':asyncio.run(main(Path(sys.argv[1])))
