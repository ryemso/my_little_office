import io
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from office.engine import Worker,run_codex
from office.store import Store


class DiagnosticsTests(unittest.TestCase):
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
