import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from raincoat_buck import agy, bridge, shared

SESSION = '12345678-1234-1234-1234-123456789abc'


class EventTests(unittest.TestCase):
    def setUp(self):
        self.state = {'status': 'submitted', 'model': '', 'tool_calls': [], 'message_usage': []}

    def test_init_publishes_conversation_and_permission_mode(self):
        agy.consume_event(self.state, {'event': 'init', 'conversation_id': SESSION,
                                       'init': {'cwd': '/tmp', 'tools': ['read_file'], 'permission_mode': 'request-review'}})
        self.assertEqual(self.state['status'], 'running')
        self.assertEqual(self.state['session_id'], SESSION)
        self.assertEqual(self.state['provider'], 'agy')
        self.assertEqual(self.state['permission_mode'], 'request-review')
        self.assertEqual(self.state['tool_count'], 1)

    def test_streamed_agent_text_is_not_completion(self):
        agy.consume_event(self.state, {'event': 'init', 'conversation_id': SESSION, 'init': {}})
        for delta in ('wor', 'king'):
            agy.consume_event(self.state, {'event': 'step_update', 'step_update': {
                'step_index': 1, 'state': 'ACTIVE', 'step_type': 'agent_response', 'text_delta': delta}})
        self.assertEqual(self.state['status'], 'running')
        agy.consume_event(self.state, {'event': 'result', 'result': {
            'conversation_id': SESSION, 'status': 'SUCCESS', 'response': 'working',
            'usage': {'output_tokens': 3}}})
        self.assertEqual(self.state['status'], 'succeeded')
        self.assertEqual(self.state['text'], 'working')
        self.assertEqual(self.state['run_usage']['output_tokens'], 3)

    def test_tool_step_is_recorded(self):
        agy.consume_event(self.state, {'event': 'init', 'conversation_id': SESSION, 'init': {}})
        agy.consume_event(self.state, {'event': 'step_update', 'step_update': {
            'step_index': 5, 'state': 'ACTIVE', 'step_type': 'tool',
            'tool_info': {'tool_name': 'run_command'}, 'text_delta': 'ls -la'}})
        agy.consume_event(self.state, {'event': 'step_update', 'step_update': {
            'step_index': 5, 'state': 'DONE', 'step_type': 'tool',
            'tool_info': {'tool_name': 'run_command', 'status': 'FAILED'}}})
        self.assertEqual(self.state['tool_calls'], [{
            'id': 5, 'name': 'run_command', 'status': 'failed', 'result': 'ls -la'}])

    def test_soft_denied_write_is_reported_as_failure(self):
        agy.consume_event(self.state, {'event': 'result', 'result': {
            'conversation_id': SESSION, 'status': 'SUCCESS', 'response': '',
            'denied_actions': [{'action': 'write_file', 'display_name': 'Edit'}]}})
        self.assertEqual(self.state['status'], 'failed')
        self.assertIn('write_file', self.state['error'])
        self.assertIn('workspace-write', self.state['error'])
        self.assertEqual(self.state['denied_actions'][0]['action'], 'write_file')

    def test_non_success_result_is_failure(self):
        agy.consume_event(self.state, {'event': 'result', 'result': {
            'status': 'ERROR', 'response': '', 'error': 'quota exhausted'}})
        self.assertEqual(self.state['status'], 'failed')
        self.assertIn('quota exhausted', self.state['error'])


class CommandTests(unittest.TestCase):
    def test_prompt_goes_through_stdin_and_default_is_read_only(self):
        with patch.object(agy.dependencies, 'agy_binary', return_value='/stable/agy'), \
             patch.object(Path, 'home', return_value=Path('/home/test')):
            args = agy.command({'prompt': 'secret prompt', 'sandbox': '', 'cwd': '', 'model': '', 'session_id': ''})
        self.assertEqual(args[0], '/stable/agy')
        self.assertEqual(args[args.index('--output-format') + 1], 'stream-json')
        self.assertEqual(args[args.index('--input-format') + 1], 'text')
        self.assertNotIn('--dangerously-skip-permissions', args)
        self.assertNotIn('secret prompt', args)

    def test_workspace_write_and_resume(self):
        with patch.object(agy.dependencies, 'agy_binary', return_value='/stable/agy'):
            args = agy.command({'sandbox': 'workspace-write', 'cwd': '/tmp',
                                'model': 'gemini-4-neon-high', 'session_id': SESSION})
        self.assertIn('--dangerously-skip-permissions', args)
        self.assertEqual(args[args.index('--model') + 1], 'gemini-4-neon-high')
        self.assertEqual(args[args.index('--conversation') + 1], SESSION)

    def test_agy_accepts_sandbox_but_rejects_workbuddy_tool_rules(self):
        from raincoat_buck import agy as agy_module
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(agy_module, 'status', return_value={'execution_ready': True}), \
             patch.object(shared, 'STATE', Path(tmp)), \
             patch('subprocess.Popen') as popen, \
             patch('threading.Thread'):
            popen.return_value.pid = 4242
            state = bridge.submit_task('agy', 'test', sandbox='workspace-write', cwd='/tmp')
        self.assertEqual(state['backend'], 'agy')
        with self.assertRaisesRegex(ValueError, 'use sandbox'):
            bridge.submit_task('agy', 'test', allowed_tools=['Bash(python3:*)'])
        with self.assertRaisesRegex(ValueError, 'sandbox applies only to GPT and Antigravity'):
            bridge.submit_task('agy', 'test', sandbox='unsafe')
        with self.assertRaisesRegex(ValueError, 'sandbox applies only to GPT and Antigravity'):
            bridge.submit_task('bitto', 'test', sandbox='workspace-write')

    def test_missing_binary_blocks_submission(self):
        from raincoat_buck import agy as agy_module
        with patch.object(agy_module, 'status', return_value={'execution_ready': False}):
            with self.assertRaisesRegex(RuntimeError, 'Antigravity CLI not installed'):
                bridge.submit_task('agy', 'test')


class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.statepatch = patch.object(shared, 'STATE', Path(self.tmp.name))
        self.statepatch.start()
        self.job = 'f' * 32
        directory = shared.job_dir(self.job)
        shared.atomic_json(directory / 'request.json', {
            'backend': 'agy', 'model': '', 'session_id': '', 'prompt': 'test',
            'timeout_seconds': 5, 'sandbox': 'read-only', 'cwd': self.tmp.name,
        })
        shared.atomic_json(directory / 'state.json', {
            'job_id': self.job, 'status': 'queued', 'backend': 'agy', 'model': '',
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
            {'event': 'init', 'conversation_id': SESSION, 'init': {'permission_mode': 'request-review'}},
            {'event': 'step_update', 'step_update': {'step_index': 1, 'state': 'ACTIVE',
                                                     'step_type': 'agent_response', 'text_delta': 'done'}},
            {'event': 'result', 'result': {'conversation_id': SESSION, 'status': 'SUCCESS',
                                           'response': 'done', 'usage': {'output_tokens': 1}}},
        ]
        script = 'import json,time;events=' + repr(events) + ';[print(json.dumps(e),flush=True) for e in events];time.sleep(30)'
        with patch.object(agy.dependencies, 'agy_binary', return_value='/stable/agy'), \
             patch.object(asyncio, 'create_subprocess_exec', self.fake_spawn(script)):
            running = asyncio.create_task(agy.run(self.ctx))
            result = await shared.wait_task(self.job, 2)
            self.assertEqual(result['status'], 'succeeded')
            self.assertEqual(result['text'], 'done')
            self.assertEqual(result['provider'], 'agy')
            lock_file = shared.lock_path('agy', result['session_id'])
            self.assertTrue(lock_file.exists())
            await asyncio.wait_for(running, 4)
            self.assertEqual(lock_file.read_text(), self.job)

    async def test_prompt_is_written_to_stdin(self):
        captured = {}

        async def spawn(*args, **kwargs):
            process = await self.original_spawn(sys.executable, '-c',
                                                'import sys,json;print(json.dumps({"event":"result","result":{"status":"SUCCESS","response":sys.stdin.read()}}),flush=True)',
                                                **kwargs)
            return process

        with patch.object(agy.dependencies, 'agy_binary', return_value='/stable/agy'), \
             patch.object(asyncio, 'create_subprocess_exec', spawn):
            await agy.run(self.ctx)
        self.assertEqual(self.ctx.state['status'], 'succeeded')
        self.assertEqual(self.ctx.state['text'], 'test')

    async def test_cancel_stops_process_before_confirming(self):
        with patch.object(agy.dependencies, 'agy_binary', return_value='/stable/agy'), \
             patch.object(asyncio, 'create_subprocess_exec', self.fake_spawn('import time;time.sleep(30)')):
            running = asyncio.create_task(agy.run(self.ctx))
            for _ in range(100):
                if self.ctx.state.get('runtime_pid'):
                    break
                await asyncio.sleep(0.01)
            pid = self.ctx.state['runtime_pid']
            shared.atomic_json(self.ctx.directory / 'cancel.json', {})
            await asyncio.wait_for(running, 4)
            self.assertEqual(self.ctx.state['status'], 'cancelled')
            self.assertFalse(shared.pid_alive(pid))

    async def test_crash_before_result_is_reported(self):
        with patch.object(agy.dependencies, 'agy_binary', return_value='/stable/agy'), \
             patch.object(asyncio, 'create_subprocess_exec', self.fake_spawn('raise SystemExit(2)')):
            with self.assertRaisesRegex(RuntimeError, 'before final result'):
                await agy.run(self.ctx)


if __name__ == '__main__':
    unittest.main()
