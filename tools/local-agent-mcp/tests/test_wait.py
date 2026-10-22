import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import shared
import bridge

class CompletionWaitTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.patch=patch.object(shared,'STATE',Path(self.tmp.name));self.patch.start()
        self.job='d'*32;directory=shared.job_dir(self.job)
        shared.atomic_json(directory/'request.json',{'backend':'bitto'})
        shared.atomic_json(directory/'state.json',{'job_id':self.job,'backend':'bitto','status':'queued','tool_calls':[]})
        self.ctx=shared.Worker(self.job)
        await self.ctx.start()
    async def asyncTearDown(self):
        await self.ctx.close();self.patch.stop();self.tmp.cleanup()
    def complete(self,status='succeeded'):
        self.ctx.state.update(status=status,backend_completed_at=time.time(),text='done');self.ctx.save()
    async def test_multiple_callers_wake_promptly_on_persisted_completion(self):
        a=asyncio.create_task(shared.wait_task(self.job,2));b=asyncio.create_task(shared.wait_task(self.job,2))
        await asyncio.sleep(0.05);self.complete()
        results=await asyncio.gather(a,b)
        for r in results:
            self.assertEqual(r['status'],'succeeded');self.assertEqual(r['wait_transport'],'unix_socket')
            self.assertLess(r['completion_delivery_ms'],250)
            self.assertEqual(shared.read_json(self.ctx.directory/'state.json')['status'],'succeeded')
    async def test_finish_between_initial_read_and_subscription_is_not_lost(self):
        original=asyncio.open_unix_connection
        async def complete_before_subscribe(*args,**kwargs):
            self.complete()
            return await original(*args,**kwargs)
        start=time.monotonic()
        with patch.object(asyncio,'open_unix_connection',complete_before_subscribe):
            r=await shared.wait_task(self.job,2)
        self.assertLess(time.monotonic()-start,0.1);self.assertEqual(r['status'],'succeeded')
    async def test_wait_timeout_does_not_cancel_execution(self):
        r=await shared.wait_task(self.job,0.03)
        self.assertEqual(r['status'],'starting');self.assertFalse((self.ctx.directory/'cancel.json').exists())
    async def test_permission_request_returns_before_wait_timeout(self):
        wait=asyncio.create_task(shared.wait_task(self.job,2));await asyncio.sleep(0.03)
        self.ctx.state.update(status='waiting_permission',permission={'requestId':'p1'});self.ctx.save()
        r=await asyncio.wait_for(wait,0.25);self.assertEqual(r['status'],'waiting_permission')
    async def test_legacy_worker_without_socket_has_fast_bounded_fallback(self):
        await self.ctx.close()
        async def finish():
            await asyncio.sleep(0.07);self.complete()
        finish_task=asyncio.create_task(finish());r=await shared.wait_task(self.job,2);await finish_task
        self.assertEqual(r['status'],'succeeded');self.assertLess(r['completion_delivery_ms'],250)
    async def test_results_do_not_repeat_huge_tool_history_by_default(self):
        r=bridge.compact({'job_id':self.job,'status':'succeeded','tool_calls':[{'id':str(i),'result':'x'*4000} for i in range(100)],'text':'done'})
        self.assertEqual(r['tool_call_count'],100);self.assertEqual(len(r['tool_calls']),4)
        self.assertLess(len(json.dumps(r)),6000)
    async def test_large_result_does_not_overflow_notification_channel(self):
        waiter=asyncio.create_task(shared.wait_task(self.job,2))
        await asyncio.sleep(0.03)
        self.ctx.state.update(text='x'*(9*1024*1024),streaming_text='x'*(9*1024*1024),status='succeeded')
        self.ctx.save()
        result=bridge.compact(await waiter)
        self.assertTrue(result['text_truncated'])
        self.assertEqual(len(result['text']),32000)
    async def test_legacy_bitto_session_lock_is_preserved(self):
        session='12345678-1234-1234-1234-123456789abc'
        self.assertEqual(shared.lock_path('bitto',session),shared.STATE/'locks'/session)
        self.assertNotEqual(shared.lock_path('workbuddy',session),shared.lock_path('bitto',session))
    async def test_zombie_worker_is_interrupted(self):
        import subprocess
        process=subprocess.Popen([sys.executable,'-c','pass'])
        try:
            await asyncio.sleep(0.15)
            self.ctx.state['worker_pid']=process.pid;self.ctx.save()
            self.assertEqual(shared.get_task(self.job)['status'],'interrupted')
        finally:
            process.wait()
    async def test_pending_workbuddy_backend_fails_before_job_creation(self):
        with patch('workbuddy.status',return_value={'installed':True,'execution_ready':False,'note':'authorization pending'}):
            with self.assertRaisesRegex(RuntimeError,'authorization pending'):
                bridge.submit_task('workbuddy','test')
        self.assertEqual(len(list((shared.STATE/'jobs').iterdir())),1)
    async def test_invalid_backend_and_wait_timeout_have_no_side_effects(self):
        with self.assertRaises(ValueError):bridge.submit_task('other','test')
        with self.assertRaises(ValueError):await bridge.submit_and_wait('bitto','test',wait_seconds=51)
        with self.assertRaises(ValueError):await shared.wait_task(self.job,-1)

if __name__=='__main__':unittest.main()
