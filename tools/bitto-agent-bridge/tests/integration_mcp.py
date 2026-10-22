"""Opt-in live test: creates Bitto sessions and consumes Bitto model tokens."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

BRIDGE = Path(__file__).resolve().parents[1] / 'bridge.py'
ROOT = Path(tempfile.mkdtemp(prefix='bitto-bridge-integration-'))
PARAMS = StdioServerParameters(command=sys.executable, args=[str(BRIDGE), 'mcp'],
    env={**os.environ, 'BITTO_BRIDGE_STATE_DIR': str(ROOT/'jobs-state')})


def value(result):
    if result.isError:
        raise RuntimeError(result.content)
    return result.structuredContent or json.loads(result.content[0].text)


async def call(session, tool, args):
    return value(await session.call_tool(tool, args))


async def wait_task(session, job):
    for _ in range(240):
        state = await call(session, 'bitto_get_task', {'job_id': job})
        if state['status'] in {'succeeded', 'failed', 'interrupted', 'cancelled'}:
            return state
        if state['status'].startswith('waiting_'):
            raise RuntimeError(state)
        await asyncio.sleep(0.5)
    raise TimeoutError(job)


async def main():
    async with stdio_client(PARAMS) as (r,w), ClientSession(r,w) as session:
        await session.initialize()
        names = [x.name for x in (await session.list_tools()).tools]
        assert len(names) == 5, names
        print('MCP discovery PASS', names, flush=True)
        print('STATUS', await call(session, 'bitto_status', {}), flush=True)
        job = await call(session, 'bitto_submit_task', {'prompt': f'本地 agent MCP 验证任务。只做此事：用 bash/python 工具计算 [13,29,47] 的平方和，在 {ROOT}/result.json 写 JSON（字段 numbers 和 sum_of_squares），重新读文件校验后简短回复结果和路径。不做其他任务。', 'title':'MCP 封装真实调用验证', 'timeout_seconds':90})
        print('SUBMITTED', job, flush=True)
    # Deliberately disconnect the MCP caller: its worker must survive.
    await asyncio.sleep(2)
    async with stdio_client(PARAMS) as (r,w), ClientSession(r,w) as session:
        await session.initialize()
        first = await wait_task(session, job['job_id'])
        assert first['status'] == 'succeeded', first
        assert first['provider'] == 'bitto' and first['tool_calls'], first
        result = json.loads((ROOT/'result.json').read_text())
        assert result['sum_of_squares'] == 3219, result
        print('EXECUTION AND CALLER RESTART PASS', first['session_id'], flush=True)
        follow = await call(session, 'bitto_submit_task', {'prompt':'这是同一会话续接验证。请只回复上一轮任务计算出的平方和数字，不调用工具。', 'session_id':first['session_id'], 'title':'MCP 会话续接验证', 'timeout_seconds':90})
        second = await wait_task(session, follow['job_id'])
        assert second['status'] == 'succeeded', second
        assert '3219' in second['text'], second
        assert second['run_id'] != first['run_id'], second
        print('CONTINUATION PASS', second['text'], flush=True)
        slow = await call(session, 'bitto_submit_task', {'prompt':'这是取消能力验证。请只调用 bash 执行 sleep 45，不创建文件、不做其他任务。', 'title':'MCP 取消验证', 'timeout_seconds':90})
        for _ in range(60):
            state = await call(session, 'bitto_get_task', {'job_id':slow['job_id']})
            if state.get('tool_calls') or state['status'] in {'failed','succeeded'}:break
            await asyncio.sleep(0.5)
        await call(session, 'bitto_cancel_task', {'job_id':slow['job_id']})
        third = await wait_task(session, slow['job_id'])
        assert third['status'] == 'cancelled', third
        print('CANCELLATION PASS', third['stop_reason'], flush=True)
        summary = {'tools':names,'first':first,'continuation':second,'cancellation':third,'artifact':result}
        (ROOT/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
        print('EVIDENCE',ROOT,flush=True)


asyncio.run(main())
