import asyncio
import os
from pathlib import Path
import sys
import unittest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / 'bridge.py'

class ContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_caller_can_wait_for_immediate_completion_instead_of_slow_polling(self):
        params = StdioServerParameters(command=sys.executable, args=[str(ENTRY), 'mcp'])
        async with stdio_client(params) as (r, w), ClientSession(r, w) as session:
            await session.initialize()
            tools = {x.name:x for x in (await session.list_tools()).tools}
            self.assertIn('agent_wait_task', tools, '旧接口只返回 job_id，无完成等待工具，调用方只能轮询')
            self.assertIn('wait_seconds', tools['agent_submit_task'].inputSchema['properties'])
            self.assertIn('backend', tools['agent_submit_task'].inputSchema['required'])

if __name__ == '__main__': unittest.main()
