import json
from pathlib import Path
import sys
import tempfile
import unittest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
MAIN_TOOLS = {
    'agent_status', 'agent_submit_task', 'agent_wait_task', 'agent_cancel_task',
    'agent_respond_permission',
}
LEGACY_TOOLS = {
    'agent_get_task', 'bitto_status', 'bitto_submit_task', 'bitto_get_task',
    'bitto_cancel_task', 'bitto_respond_permission',
}


def server(state, **env):
    return StdioServerParameters(
        command=sys.executable,
        args=['-m', 'raincoat_buck', 'mcp'],
        env={
            'PYTHONPATH': str(ROOT / 'src'),
            'LOCAL_AGENT_MCP_STATE_DIR': str(state),
            'LOCAL_AGENT_MCP_LEGACY_TOOLS': '0',
            **env,
        },
    )

def tool_value(result):
    return result.structuredContent or json.loads(result.content[0].text)


class ContractTests(unittest.IsolatedAsyncioTestCase):
    async def test_default_tools_and_zero_second_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            job_id = 'a' * 32
            job = Path(tmp) / 'jobs' / job_id
            job.mkdir(parents=True)
            (job / 'state.json').write_text(json.dumps({
                'job_id': job_id, 'status': 'succeeded', 'text': 'historic result',
                'tool_calls': [{'id': 'large', 'result': 'x' * 1000}],
            }), encoding='utf-8')
            async with stdio_client(server(tmp)) as (reader, writer), ClientSession(reader, writer) as session:
                await session.initialize()
                tools = {tool.name: tool for tool in (await session.list_tools()).tools}
                self.assertEqual(set(tools), MAIN_TOOLS)
                properties = tools['agent_submit_task'].inputSchema['properties']
                self.assertTrue({'resume_from_job_id', 'wait_seconds', 'sandbox'} <= properties.keys())
                result = await session.call_tool('agent_wait_task', {'job_id': job_id, 'timeout_seconds': 0})
                self.assertFalse(result.isError, result.content)
                state = tool_value(result)
                self.assertEqual((state['backend'], state['text']), ('bitto', 'historic result'))
                self.assertEqual(state['wait_transport'], 'snapshot')
                self.assertNotIn('tool_calls', state)
                self.assertEqual(state['tool_call_count'], 1)
                self.assertEqual(Path(state['result_path']), job / 'state.json')
                detailed = tool_value(await session.call_tool('agent_wait_task', {
                    'job_id': job_id, 'timeout_seconds': 0, 'include_details': True,
                }))
                self.assertEqual(detailed['tool_calls'][0]['id'], 'large')

    async def test_compatibility_mode_exposes_existing_tools(self):
        with tempfile.TemporaryDirectory() as tmp:
            params = server(tmp, LOCAL_AGENT_MCP_LEGACY_TOOLS='1')
            async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
                await session.initialize()
                tools = {tool.name for tool in (await session.list_tools()).tools}
                self.assertEqual(tools, MAIN_TOOLS | LEGACY_TOOLS)

    async def test_status_lists_backends_without_requiring_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            async with stdio_client(server(tmp)) as (reader, writer), ClientSession(reader, writer) as session:
                await session.initialize()
                result = await session.call_tool('agent_status', {})
                self.assertFalse(result.isError, result.content)
                self.assertEqual(set(tool_value(result)['backends']), {'bitto', 'workbuddy', 'gpt', 'agy'})

    @unittest.skipUnless(sys.platform == 'darwin', 'Fixture uses a POSIX executable script')
    async def test_codex_job_resumes_with_the_same_session_and_permissions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            fake_codex = root / 'codex'
            fake_codex.write_text(f'#!{sys.executable}\n' + """
import json
import sys

args = sys.argv[1:]
thread_id = '12345678-1234-1234-1234-123456789abc'
assert args[0] == 'exec'
prompt = sys.stdin.read()
details = {
    'prompt': prompt,
    'cwd': args[args.index('--cd') + 1],
    'sandbox': args[args.index('--sandbox') + 1],
    'resume': args[args.index('resume') + 1] if 'resume' in args else None,
}
for event in [
    {'type': 'thread.started', 'thread_id': thread_id},
    {'type': 'item.completed', 'item': {'id': 'm1', 'type': 'agent_message', 'text': json.dumps(details)}},
    {'type': 'turn.completed', 'usage': {}},
]:
    print(json.dumps(event), flush=True)
""", encoding='utf-8')
            fake_codex.chmod(0o700)
            params = server(root, LOCAL_AGENT_CODEX=str(fake_codex))
            async with stdio_client(params) as (reader, writer), ClientSession(reader, writer) as session:
                await session.initialize()

                async def call(tool, **args):
                    result = await session.call_tool(tool, args)
                    self.assertFalse(result.isError, result.content)
                    return tool_value(result)

                started = await call('agent_submit_task', backend='codex', prompt='check',
                                     cwd=str(root), sandbox='read-only', wait_seconds=0)
                first = await call('agent_wait_task', job_id=started['job_id'], timeout_seconds=8)
                self.assertEqual(first['status'], 'succeeded', first)
                self.assertIsNone(json.loads(first['text'])['resume'])

                rejected = await session.call_tool('agent_submit_task', {
                    'resume_from_job_id': first['job_id'], 'prompt': 'expand permissions',
                    'sandbox': 'workspace-write',
                })
                self.assertTrue(rejected.isError, rejected)
                self.assertEqual(len(list((root / 'jobs').iterdir())), 1)

                resumed = await call('agent_submit_task', resume_from_job_id=first['job_id'],
                                     prompt='follow up', wait_seconds=0)
                self.assertNotEqual(resumed['job_id'], first['job_id'])
                result = await call('agent_wait_task', job_id=resumed['job_id'], timeout_seconds=8)
                self.assertEqual(result['status'], 'succeeded', result)
                self.assertEqual(json.loads(result['text']), {
                    'prompt': 'follow up', 'cwd': str(root),
                    'sandbox': 'read-only', 'resume': first['session_id'],
                })
