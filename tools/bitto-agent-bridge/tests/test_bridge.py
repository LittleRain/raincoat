import importlib.util
import pathlib
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('bridge', pathlib.Path(__file__).parents[1] / 'bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)


class BridgeTests(unittest.TestCase):
    def state(self):
        return {'model': 'test-model', 'status': 'submitted', 'text': '', 'tool_calls': [], 'message_usage': []}

    def event(self, kind, **payload):
        return {'type': bridge.PREFIX + kind, 'payload': payload}

    def test_ignore_history_and_other_run(self):
        s = self.state()
        bridge.consume_event(s, self.event('SessionRunEnded', runId='old', stopReason='STOP_REASON_STOP'))
        self.assertEqual(s['status'], 'submitted')
        bridge.consume_event(s, self.event('SessionAccepted', runId='new'))
        bridge.consume_event(s, self.event('SessionRunEnded', runId='old', stopReason='STOP_REASON_STOP'))
        self.assertEqual(s['status'], 'running')

    def test_bitto_result_preserves_provider_and_each_message_usage(self):
        s = self.state()
        bridge.consume_event(s, self.event('SessionAccepted', runId='new'))
        for i in range(2):
            bridge.consume_event(s, self.event('SessionChatMessageEnded', runId='new', messageId=str(i),
                contents=[{'text': {'text': 'result'}}], role='MESSAGE_ROLE_ASSISTANT',
                meta={'provider': 'bitto', 'model': 'bitto-model', 'usage': {'inputTokens': '42'}}))
        bridge.consume_event(s, self.event('SessionRunEnded', runId='new', stopReason='STOP_REASON_STOP', usage={'inputTokens': '42'}))
        self.assertEqual(s['status'], 'succeeded')
        self.assertEqual(s['provider'], 'bitto')
        self.assertEqual(len(s['message_usage']), 2)
        self.assertEqual(s['run_usage']['inputTokens'], '42')

    def test_error_and_unknown_end_are_not_success(self):
        for reason in ['STOP_REASON_ERROR', 'STOP_REASON_MAX_TOKENS', '']:
            s = self.state()
            bridge.consume_event(s, self.event('SessionAccepted', runId='new'))
            bridge.consume_event(s, self.event('SessionRunEnded', runId='new', stopReason=reason))
            self.assertEqual(s['status'], 'failed')

    def test_cancellation_requires_terminal_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bridge, 'STATE', pathlib.Path(tmp)):
            job = 'a' * 32
            bridge.atomic_json(bridge.job_dir(job) / 'state.json', {'job_id': job, 'status': 'running'})
            self.assertEqual(bridge.cancel_task(job)['status'], 'cancellation_requested')
            self.assertEqual(bridge.get_task(job)['status'], 'running')
            self.assertTrue((bridge.job_dir(job) / 'cancel.json').exists())

    def test_permission_response_must_match_pending_request(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bridge, 'STATE', pathlib.Path(tmp)):
            job = 'b' * 32
            bridge.atomic_json(bridge.job_dir(job) / 'state.json', {'status': 'waiting_permission', 'permission': {'requestId': 'expected'}})
            with self.assertRaises(ValueError):
                bridge.respond_permission(job, 'wrong', True)
            bridge.respond_permission(job, 'expected', False)
            self.assertEqual(bridge.read_json(bridge.job_dir(job) / 'permission-response.json'), {'requestId': 'expected', 'allow': False, 'remember': False})

    def test_worker_died_before_state_update_is_interrupted(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bridge, 'STATE', pathlib.Path(tmp)), patch.object(bridge.os, 'kill', side_effect=ProcessLookupError):
            job = 'c' * 32
            bridge.atomic_json(bridge.job_dir(job) / 'state.json', {'status': 'queued'})
            bridge.atomic_json(bridge.job_dir(job) / 'worker.json', {'pid': 123})
            self.assertEqual(bridge.get_task(job)['status'], 'interrupted')

    def test_reject_job_path_traversal(self):
        with self.assertRaises(ValueError): bridge.job_dir('../credentials')

    def test_never_send_bearer_to_remote_websocket(self):
        with patch.dict('os.environ', {'BITTO_BRIDGE_WS_URL': 'ws://example.com:9000'}):
            with self.assertRaises(ValueError): bridge.discover_ws()

    def test_submit_rejects_invalid_input_before_spawning(self):
        with patch.object(bridge, 'discover_ws', return_value='ws://127.0.0.1:1'), patch.object(bridge, 'token', return_value='secret'):
            with self.assertRaises(ValueError): bridge.submit_task('')
            with self.assertRaises(ValueError): bridge.submit_task('test', timeout_seconds=0)


if __name__ == '__main__': unittest.main()
