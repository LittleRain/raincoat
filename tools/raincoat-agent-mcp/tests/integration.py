"""Opt-in real backend integration. Creates test sessions and consumes model tokens."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[1]

def value(r):
    if r.isError:raise RuntimeError(r.content)
    return r.structuredContent or json.loads(r.content[0].text)

async def main(backend):
    output=Path(tempfile.mkdtemp(prefix='local-agent-integration-',dir='/private/tmp'))
    params=StdioServerParameters(command=sys.executable,args=[os.environ.get('LOCAL_AGENT_TEST_ENTRY',str(ROOT/'bridge.py')),'mcp'],env={**os.environ,'LOCAL_AGENT_MCP_STATE_DIR':str(output/'state')})
    async with stdio_client(params) as (r,w),ClientSession(r,w) as session:
        await session.initialize()
        prompt=f'仅做本验证任务：直接调用以 python3 开头的命令，计算 [7,11,13] 的平方和，在 {output}/result.json 写入 JSON（numbers、sum_of_squares字段），重新读文件校验后回复结果与路径。仅运行 python3；不要先执行ls/pwd/mkdir或任何其他工作流。'
        args={'backend':backend,'prompt':prompt,'cwd':str(output),'title':'Unified MCP result delivery verification','wait_seconds':25,'timeout_seconds':90}
        if backend=='workbuddy':args['allowed_tools']=['Bash(python3:*)']
        start=time.monotonic()
        result=value(await session.call_tool('agent_submit_task',args))
        while result['status'] not in {'succeeded','failed','interrupted','cancelled','waiting_permission','waiting_desktop_tool'}:
            result=value(await session.call_tool('agent_wait_task',{'job_id':result['job_id'],'timeout_seconds':25}))
        elapsed=time.monotonic()-start
        assert result['status']=='succeeded',result
        artifact=json.loads((output/'result.json').read_text());assert artifact['sum_of_squares']==339,artifact
        assert result['backend']==backend
        assert result['completion_delivery_ms']<250,result
        summary={'backend':backend,'execution_seconds':elapsed,'completion_delivery_ms':result['completion_delivery_ms'],'wait_transport':result['wait_transport'],'result':result,'artifact':artifact}
        (output/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
        print(json.dumps({'backend':backend,'status':result['status'],'completion_delivery_ms':result['completion_delivery_ms'],'wait_transport':result['wait_transport'],'model':result.get('model'),'provider':result.get('provider'),'evidence':str(output)},ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('backend',choices=['bitto','workbuddy']);asyncio.run(main(p.parse_args().backend))
