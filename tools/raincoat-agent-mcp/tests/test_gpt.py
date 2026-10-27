import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from raincoat_agent_mcp import bridge, gpt, shared


class EventTests(unittest.TestCase):
    def setUp(self):
        self.state = {'status': 'submitted', 'model': '', 'tool_calls': [], 'message_usage': []}

    def test_intermediate_agent_message_is_not_completion(self):
        gpt.consume_event(self.state, {'type': 'thread.started', 'thread_id': '12345678-1234-1234-1234-123456789abc'})
        gpt.consume_event(self.state, {'type': 'item.completed', 'item': {'id': 'm1', 'type': 'agent_message', 'text': 'working'}})
        self.assertEqual(self.state['status'], 'running')
        self.assertEqual(self.state['text'], 'working')
        gpt.consume_event(self.state, {'type': 'turn.completed', 'usage': {'output_tokens': 3}})
        self.assertEqual(self.state['status'], 'succeeded')
        self.assertEqual(self.state['run_usage']['output_tokens'], 3)

    def test_tool_result_and_failure_are_preserved(self):
        gpt.consume_event(self.state, {'type': 'item.started', 'item': {'id': 'c1', 'type': 'command_execution', 'command': 'python3 bad.py'}})
        gpt.consume_event(self.state, {'type': 'item.completed', 'item': {'id': 'c1', 'type': 'command_execution', 'exit_code': 2, 'aggregated_output': 'failure'}})
        self.assertEqual(self.state['tool_calls'], [{'id': 'c1', 'name': 'Bash', 'status': 'failed', 'command': 'python3 bad.py', 'result': 'failure', 'exit_code': 2}])
        gpt.consume_event(self.state, {'type': 'turn.failed', 'error': {'message': 'turn failed'}})
        self.assertEqual(self.state['status'], 'failed')
        self.assertEqual(self.state['error'], 'turn failed')

    def test_error_event_is_not_silently_ignored(self):
        gpt.consume_event(self.state, {'type': 'error', 'message': 'authentication expired'})
        self.assertEqual(self.state['status'], 'failed')
        self.assertIn('authentication expired', self.state['error'])


class CommandTests(unittest.TestCase):
    def test_new_task_is_read_only_and_prompt_is_not_a_cli_argument(self):
        with patch.object(gpt.dependencies, 'codex_binary', return_value='/stable/codex'), patch.object(Path, 'home', return_value=Path('/home/test')):
            args = gpt.command({'prompt': 'secret prompt', 'sandbox': '', 'cwd': '', 'model': '', 'session_id': ''})
        self.assertEqual(args[0], '/stable/codex')
        self.assertIn('--ignore-user-config', args)
        self.assertEqual(args[args.index('--sandbox') + 1], 'read-only')
        self.assertEqual(args[-1], '-')
        self.assertNotIn('secret prompt', args)

    def test_resume_and_explicit_workspace_write(self):
        session = '12345678-1234-1234-1234-123456789abc'
        with patch.object(gpt.dependencies, 'codex_binary', return_value='/stable/codex'):
            args = gpt.command({'sandbox': 'workspace-write', 'cwd': '/tmp', 'model': 'gpt-test', 'session_id': session})
        self.assertEqual(args[args.index('--sandbox') + 1], 'workspace-write')
        self.assertEqual(args[args.index('--model') + 1], 'gpt-test')
        self.assertEqual(args[args.index('resume') + 1], session)

    def test_gpt_does_not_accept_workbuddy_tool_rules(self):
        with self.assertRaisesRegex(ValueError, 'use sandbox'):
            bridge.submit_task('gpt', 'test', allowed_tools=['Bash(python3:*)'])
        with self.assertRaisesRegex(ValueError, 'sandbox applies only to GPT'):
            bridge.submit_task('gpt', 'test', sandbox='unsafe')
        with self.assertRaisesRegex(ValueError, 'sandbox applies only to GPT'):
            bridge.submit_task('bitto', 'test', sandbox='workspace-write')


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.statepatch = patch.object(shared, 'STATE', Path(self.tmp.name))
        self.statepatch.start()
        self.job = 'e' * 32
        directory = shared.job_dir(self.job)
        shared.atomic_json(directory / 'request.json', {
            'backend': 'gpt', 'model': '', 'session_id': '', 'prompt': 'test',
            'timeout_seconds': 5, 'sandbox': 'read-only', 'cwd': self.tmp.name,
        })
        shared.atomic_json(directory / 'state.json', {
            'job_id': self.job, 'status': 'queued', 'backend': 'gpt', 'model': '',
            'tool_calls': [], 'message_usage': [],
        })
        self.ctx = shared.Worker(self.job)
        await self.ctx.start()
        self.original_spawn = asyncio.create_subprocess_exec

    async def asyncTearDown(self):
        await self.ctx.close()
        self.statepatch.stop()
        self.tmp.cleanup()

    def fake_spawn(self, script):
        async def spawn(*args, **kwargs):
            return await self.original_spawn(sys.executable, '-c', script, **kwargs)
        return spawn

    async def test_result_arrives_before_process_housekeeping(self):
        events = [
            {'type': 'thread.started', 'thread_id': '12345678-1234-1234-1234-123456789abc'},
            {'type': 'item.completed', 'item': {'id': 'm1', 'type': 'agent_message', 'text': 'done'}},
            {'type': 'turn.completed', 'usage': {'output_tokens': 1}},
        ]
        script = 'import json,time;events=' + repr(events) + ';[print(json.dumps(e),flush=True) for e in events];time.sleep(30)'
        with patch.object(gpt.dependencies, 'codex_binary', return_value='/stable/codex'), patch.object(asyncio, 'create_subprocess_exec', self.fake_spawn(script)):
            running = asyncio.create_task(gpt.run(self.ctx))
            result = await shared.wait_task(self.job, 2)
            self.assertEqual(result['status'], 'succeeded')
            self.assertEqual(result['text'], 'done')
            self.assertEqual(result['provider'], 'codex')
            self.assertEqual(shared.lock_path('gpt', result['session_id']).read_text(), self.job)
            self.assertLess(result['completion_delivery_ms'], 250)
            await asyncio.wait_for(running, 4)

    async def test_cancel_stops_process_before_confirming(self):
        with patch.object(gpt.dependencies, 'codex_binary', return_value='/stable/codex'), patch.object(asyncio, 'create_subprocess_exec', self.fake_spawn('import time;time.sleep(30)')):
            running = asyncio.create_task(gpt.run(self.ctx))
            for _ in range(100):
                if self.ctx.state.get('runtime_pid'):
                    break
                await asyncio.sleep(0.01)
            pid = self.ctx.state['runtime_pid']
            shared.atomic_json(self.ctx.directory / 'cancel.json', {})
            await asyncio.wait_for(running, 4)
            self.assertEqual(self.ctx.state['status'], 'cancelled')
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    async def test_api_key_environment_does_not_override_saved_chatgpt_login(self):
        script = 'import json;print(json.dumps({"type":"turn.completed","usage":{}}),flush=True)'
        captured = {}

        async def spawn(*args, **kwargs):
            captured.update(kwargs.get('env', {}))
            return await self.original_spawn(sys.executable, '-c', script, **kwargs)

        with patch.object(gpt.dependencies, 'codex_binary', return_value='/stable/codex'), patch.dict(os.environ, {'OPENAI_API_KEY': 'do-not-use', 'CODEX_API_KEY': 'do-not-use'}), patch.object(asyncio, 'create_subprocess_exec', spawn):
            await gpt.run(self.ctx)
        self.assertNotIn('OPENAI_API_KEY', captured)
        self.assertNotIn('CODEX_API_KEY', captured)

    async def test_crash_before_final_turn_is_reported(self):
        with patch.object(gpt.dependencies, 'codex_binary', return_value='/stable/codex'), patch.object(asyncio, 'create_subprocess_exec', self.fake_spawn('raise SystemExit(2)')):
            with self.assertRaisesRegex(RuntimeError, 'before final turn result'):
                await gpt.run(self.ctx)


if __name__ == '__main__':
    unittest.main()
