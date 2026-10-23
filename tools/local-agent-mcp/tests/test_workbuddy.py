import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import shared
import workbuddy
import bridge

class EventTests(unittest.TestCase):
    def setUp(self):self.state={'status':'submitted','model':'test','tool_calls':[],'message_usage':[]}
    def test_installed_node_path_survives_minimal_desktop_path(self):
        with patch.dict(os.environ,{'PATH':'','LOCAL_AGENT_NODE':''}),patch.object(Path,'exists',return_value=True),patch.object(Path,'is_file',return_value=True),patch.object(shared,'read_json',return_value={'node':'/stable/node'}):
            self.assertEqual(workbuddy.node_binary(),'/stable/node')
    def test_allowed_tools_cannot_inject_cli_options(self):
        with self.assertRaisesRegex(ValueError,'explicit tool names'):
            bridge.submit_task('workbuddy','test',allowed_tools=['--dangerously-skip-permissions'])
    def test_intermediate_assistant_is_not_completion(self):
        workbuddy.consume_event(self.state,{'type':'assistant','message':{'content':[{'type':'text','text':'working'}]}})
        self.assertEqual(self.state['status'],'submitted')
        workbuddy.consume_event(self.state,{'type':'result','subtype':'success','result':'done','usage':{'output_tokens':3}})
        self.assertEqual(self.state['status'],'succeeded');self.assertEqual(self.state['run_usage']['output_tokens'],3)
    def test_permission_denial_cannot_be_success(self):
        workbuddy.consume_event(self.state,{'type':'result','subtype':'success','permission_denials':[{'tool':'Bash'}]})
        self.assertEqual(self.state['status'],'failed')
    def test_non_workbuddy_authentication_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError,'authenticate'):
            workbuddy.consume_event(self.state,{'type':'system','subtype':'init','apiKeySource':'api.deepseek.com'})
    def test_exit_without_final_result_is_not_success(self):
        with self.assertRaisesRegex(RuntimeError,'without a final result'):
            workbuddy.consume_event(self.state,{'type':'bridge_exit','code':0})

class RunnerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.statepatch=patch.object(shared,'STATE',Path(self.tmp.name));self.statepatch.start()
        self.job='c'*32;directory=shared.job_dir(self.job)
        shared.atomic_json(directory/'request.json',{'backend':'workbuddy','model':'test','session_id':'','prompt':'test','timeout_seconds':5})
        shared.atomic_json(directory/'state.json',{'job_id':self.job,'status':'queued','backend':'workbuddy','model':'test','tool_calls':[],'message_usage':[]})
        self.ctx=shared.Worker(self.job);await self.ctx.start()
        self.original_spawn=asyncio.create_subprocess_exec
    async def asyncTearDown(self):
        await self.ctx.close();self.statepatch.stop();self.tmp.cleanup()
    def fake_spawn(self,script):
        async def spawn(*args,**kwargs):return await self.original_spawn(sys.executable,'-c',script,**kwargs)
        return spawn
    async def test_result_arrives_before_process_housekeeping(self):
        script='import json,time;print(json.dumps({"type":"result","subtype":"success","result":"done"}),flush=True);time.sleep(30)'
        with patch.object(workbuddy,'validate_model'),patch.object(asyncio,'create_subprocess_exec',self.fake_spawn(script)):
            running=asyncio.create_task(workbuddy.run(self.ctx))
            result=await shared.wait_task(self.job,2)
            self.assertEqual(result['status'],'succeeded');self.assertLess(result['completion_delivery_ms'],250)
            await asyncio.wait_for(running,4)
    async def test_cancel_stops_process_before_confirming(self):
        with patch.object(workbuddy,'validate_model'),patch.object(asyncio,'create_subprocess_exec',self.fake_spawn('import time;time.sleep(30)')):
            running=asyncio.create_task(workbuddy.run(self.ctx))
            for _ in range(100):
                if self.ctx.state.get('runtime_pid'):break
                await asyncio.sleep(0.01)
            pid=self.ctx.state['runtime_pid']
            shared.atomic_json(self.ctx.directory/'cancel.json',{})
            await asyncio.wait_for(running,4)
            self.assertEqual(self.ctx.state['status'],'cancelled')
            with self.assertRaises(ProcessLookupError):os.kill(pid,0)
    async def test_term_ignoring_descendant_is_killed_after_leader_exits(self):
        marker=Path(self.tmp.name)/'child.pid'
        child="import signal,time,os;signal.signal(signal.SIGTERM,signal.SIG_IGN);open("+repr(str(marker))+",'w').write(str(os.getpid()));time.sleep(30)"
        parent="import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',"+repr(child)+"]);time.sleep(30)"
        process=await self.original_spawn(sys.executable,'-c',parent,start_new_session=True)
        try:
            for _ in range(100):
                if marker.exists():break
                await asyncio.sleep(.01)
            self.assertTrue(marker.exists())
            await asyncio.wait_for(workbuddy.stop_process(process),5)
            self.assertFalse(await workbuddy.group_alive(process.pid))
        finally:
            await workbuddy.stop_process(process)
    async def test_immediate_resume_waits_for_completed_predecessor_cleanup(self):
        import fcntl
        sid='12345678-1234-1234-1234-123456789abc'
        lock=shared.lock_path('workbuddy',sid).open('a+')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        lock.write(self.job);lock.flush()
        self.ctx.state['status']='succeeded';self.ctx.save()
        async def release():
            await asyncio.sleep(.1);lock.close()
        release_task=asyncio.create_task(release())
        acquired=await workbuddy.acquire_session_lock(self.ctx,sid)
        acquired.close();await release_task
    async def test_running_session_is_not_queued_as_resume(self):
        import fcntl
        sid='12345678-1234-1234-1234-123456789abc'
        lock=shared.lock_path('workbuddy',sid).open('a+')
        try:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);lock.write(self.job);lock.flush()
            with self.assertRaisesRegex(RuntimeError,'已有桥接任务'):
                await workbuddy.acquire_session_lock(self.ctx,sid)
        finally:lock.close()
    async def test_crash_before_result_is_reported(self):
        with patch.object(workbuddy,'validate_model'),patch.object(asyncio,'create_subprocess_exec',self.fake_spawn('raise SystemExit(2)')):
            with self.assertRaisesRegex(RuntimeError,'before final result'):
                await workbuddy.run(self.ctx)

if __name__=='__main__':unittest.main()
