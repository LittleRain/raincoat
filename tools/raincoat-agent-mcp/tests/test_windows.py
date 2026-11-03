"""Windows startup paths without requiring product credentials or model calls."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from raincoat_agent_mcp import dependencies, shared, workbuddy


class WindowsDiscoveryTests(unittest.TestCase):
    def test_npm_codex_shim_resolves_to_native_executable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shim = root / 'codex.cmd'
            shim.write_text('')
            binary = root / 'node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe'
            binary.parent.mkdir(parents=True)
            binary.write_text('')
            with patch.object(dependencies.sys, 'platform', 'win32'), \
                    patch.object(dependencies, 'settings', return_value={}), \
                    patch.object(dependencies.shutil, 'which', side_effect=lambda name: str(shim) if name == 'codex' else None), \
                    patch.dict(os.environ, {'LOCAL_AGENT_CODEX': ''}):
                self.assertEqual(dependencies.codex_binary(), str(binary))

    def test_workbuddy_default_windows_install_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp)
            app = local / 'Programs/WorkBuddy'
            (app / 'resources').mkdir(parents=True)
            (app / 'resources/app.asar').write_text('')
            (app / 'WorkBuddy.exe').write_text('')
            with patch.object(workbuddy.sys, 'platform', 'win32'), \
                    patch.dict(os.environ, {'LOCALAPPDATA': str(local), 'WORKBUDDY_APP': ''}):
                self.assertEqual(workbuddy.app_root(), app)
                self.assertEqual(workbuddy.app_files()[1:], (app / 'resources/app.asar', app / 'WorkBuddy.exe'))


class WindowsRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_windows_wait_uses_bounded_state_polling(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(shared, 'STATE', Path(tmp)), \
                patch.object(shared, 'IS_WINDOWS', True):
            job = 'a' * 32
            directory = shared.job_dir(job)
            shared.atomic_json(directory / 'request.json', {'backend': 'gpt'})
            shared.atomic_json(directory / 'state.json', {'job_id': job, 'status': 'queued'})
            worker = shared.Worker(job)
            await worker.start()
            try:
                waiting = asyncio.create_task(shared.wait_task(job, 2))
                await asyncio.sleep(0.06)
                worker.state['status'] = 'succeeded'
                worker.save()
                result = await waiting
                self.assertEqual(result['status'], 'succeeded')
                self.assertEqual(result['wait_transport'], 'snapshot')
            finally:
                await worker.close()

    @unittest.skipUnless(os.name == 'nt', 'Requires native Windows process APIs')
    async def test_windows_process_tree_can_be_stopped(self):
        process = await asyncio.create_subprocess_exec(
            sys.executable, '-c', 'import time;time.sleep(30)', **shared.spawn_options(),
        )
        await shared.stop_process(process)
        self.assertIsNotNone(process.returncode)

    @unittest.skipUnless(os.name == 'nt', 'Requires msvcrt')
    async def test_windows_session_lock_rejects_second_handle(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(shared, 'STATE', Path(tmp)):
            path = shared.lock_path('gpt', 'session')
            with path.open('a+') as first, path.open('a+') as second:
                shared.try_lock_file(first)
                with self.assertRaises(BlockingIOError):
                    shared.try_lock_file(second)


if __name__ == '__main__':
    unittest.main()
