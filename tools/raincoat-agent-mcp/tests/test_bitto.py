import asyncio
import json
from pathlib import Path
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch
import websockets
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from raincoat_agent_mcp import bitto, shared
class BittoEventsTests(unittest.TestCase):
    def event(self,kind,**payload):return {'type':bitto.PREFIX+kind,'payload':payload}
    def test_intermediate_message_is_not_task_completion(self):
        s={'status':'submitted','model':'test','tool_calls':[],'message_usage':[]}
        bitto.consume_event(s,self.event('SessionAccepted',runId='current'))
        bitto.consume_event(s,self.event('SessionChatMessageEnded',runId='current',contents=[{'text':{'text':'still working'}}],meta={'stopReason':'STOP_REASON_TOOL_USE'}))
        self.assertEqual(s['status'],'running')
        bitto.consume_event(s,self.event('SessionRunEnded',runId='other',stopReason='STOP_REASON_STOP'))
        self.assertEqual(s['status'],'running')
        bitto.consume_event(s,self.event('SessionRunEnded',runId='current',stopReason='STOP_REASON_STOP'))
        self.assertEqual(s['status'],'succeeded')
    def test_normal_end_turn_wins_cancel_race(self):
        state={'status':'running','model':'test','cancel_sent':True,'run_id':'current'}
        bitto.consume_event(state,self.event('SessionRunEnded',stopReason='STOP_REASON_END_TURN'))
        self.assertEqual(state['status'],'succeeded')


class BittoLoopbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_session_over_local_websocket(self):
        sid = str(uuid.uuid4())
        job = 'b' * 32
        async def sidecar(ws):
            opened = json.loads(await ws.recv())
            self.assertEqual(opened['type'], bitto.PREFIX + 'OpenSession')
            await ws.send(json.dumps({'type': bitto.PREFIX + 'SessionOpened', 'sessionId': sid, 'payload': {'agentRunning': False}}))
            chat = json.loads(await ws.recv())
            self.assertEqual(chat['type'], bitto.PREFIX + 'SessionChat')
            self.assertEqual(chat['payload']['contents'][0]['text']['text'], 'hello')
            for kind, payload in [
                ('SessionAccepted', {'runId': 'run-1'}),
                ('SessionChatMessageEnded', {'runId': 'run-1', 'contents': [{'text': {'text': 'done'}}]}),
                ('SessionRunEnded', {'runId': 'run-1', 'stopReason': 'STOP_REASON_END_TURN'}),
            ]:
                await ws.send(json.dumps({'type': bitto.PREFIX + kind, 'sessionId': sid, 'payload': payload}))
        with tempfile.TemporaryDirectory() as tmp, patch.object(shared, 'STATE', Path(tmp)), patch.object(bitto, 'BITTO', Path(tmp)), patch.object(bitto, 'token', return_value='test-token'):
            (Path(tmp) / 'device.id').write_text('test-device', encoding='utf-8')
            async with websockets.serve(sidecar, '127.0.0.1', 0) as server:
                port = server.sockets[0].getsockname()[1]
                directory = shared.job_dir(job)
                with patch.dict('os.environ', {'BITTO_BRIDGE_WS_URL': f'ws://127.0.0.1:{port}'}):
                    ws_url = bitto.discover_ws()
                shared.atomic_json(directory / 'request.json', {'backend': 'bitto', 'session_id': sid, 'prompt': 'hello', 'model': 'test', 'timeout_seconds': 5, 'cwd': tmp, 'ws_url': ws_url})
                shared.atomic_json(directory / 'state.json', {'job_id': job, 'status': 'queued', 'backend': 'bitto', 'model': 'test', 'tool_calls': [], 'message_usage': []})
                worker = shared.Worker(job)
                await worker.start()
                try:
                    await asyncio.wait_for(bitto.run(worker), 5)
                    self.assertEqual(worker.state['status'], 'succeeded')
                    self.assertEqual(worker.state['text'], 'done')
                    self.assertTrue((directory / 'events.jsonl').is_file())
                finally:
                    await worker.close()
if __name__=='__main__':unittest.main()
