import io
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from office.engine import Worker,run_codex,codex_command
from office.store import Store


class DiagnosticsTests(unittest.TestCase):
    def test_windows_native_binary_with_korean_path_without_node(self):
        with tempfile.TemporaryDirectory() as folder:
            npm=Path(folder)/'김렴소'/'npm'
            native=npm/'node_modules/@openai/codex/node_modules/@openai/codex-win32-x64/vendor/x86_64-pc-windows-msvc/bin/codex.exe'
            native.parent.mkdir(parents=True);native.write_bytes(b'fixture')
            with patch('office.engine.shutil.which',return_value=str(npm/'codex.cmd')),patch('office.engine.platform.machine',return_value='AMD64'):
                self.assertEqual(codex_command(),[str(native)])

    def test_windows_hoisted_arm64_and_wrapper_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            npm=Path(folder)
            native=npm/'node_modules/@openai/codex-win32-arm64/vendor/aarch64-pc-windows-msvc/bin/codex.exe'
            native.parent.mkdir(parents=True);native.write_bytes(b'fixture')
            def which(name):return str(npm/'codex.cmd') if name=='codex' else 'node'
            with patch('office.engine.shutil.which',side_effect=which),patch('office.engine.platform.machine',return_value='ARM64'):
                self.assertEqual(codex_command(),[str(native)])
                native.unlink()
                wrapper=npm/'node_modules/@openai/codex/bin/codex.js'
                wrapper.parent.mkdir(parents=True);wrapper.write_text('// fixture')
                self.assertEqual(codex_command(),['node',str(wrapper)])

    def test_worker_preserves_error_and_local_traceback_without_secret(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder)
            def fail(*args):raise OSError('프로젝트 접근 실패 token sk-abcdefghijklmnop1234567890')
            worker=Worker(store,fail,start=False)
            try:
                store.clock_in();identifier=store.submit('dev','간단한 업무를 진행해줘')
                worker.step()
                task=store.get(identifier)
                self.assertEqual(task['status'],'failed')
                self.assertIn('OSError',task['error'])
                self.assertIn('프로젝트 접근 실패',task['error'])
                log=next((Path(folder)/'logs').glob('worker-*.log')).read_text()
                self.assertIn('Traceback',log)
                self.assertNotIn('sk-abcdefghijklmnop1234567890',log+task['error'])
                self.assertFalse(store.status()[0]['on_duty'])
            finally:worker.close()

    def test_early_cli_exit_retains_stderr_instead_of_generic_pipe_error(self):
        class BrokenInput:
            def write(self,text):raise BrokenPipeError('early exit')
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.clock_in();store.submit('dev','간단한 업무를 진행해줘');task=store.claim()
            def fake(args,**kwargs):
                kwargs['stderr'].write('error: unexpected argument --unsupported');kwargs['stderr'].flush()
                return SimpleNamespace(stdin=BrokenInput(),returncode=2,poll=lambda:2)
            with patch('office.engine.require_login'),patch('office.engine.codex_command',return_value=['codex']),patch('office.engine.subprocess.Popen',side_effect=fake):
                result=run_codex(store,task,time.time()+10)
            self.assertEqual(result['status'],'failed')
            self.assertIn('unexpected argument',result['error'])
            self.assertIn('종료 코드 2',result['error'])
