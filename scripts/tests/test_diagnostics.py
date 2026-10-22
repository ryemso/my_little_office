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
    def execute_fixture(self,store,task,events,output='',stderr='',check=None):
        def fake(args,**kwargs):
            if check:check(args,kwargs)
            if output:Path(args[args.index('-o')+1]).write_text(output,encoding='utf-8')
            kwargs['stdout'].write('\n'.join(__import__('json').dumps(e) for e in events)+'\n');kwargs['stdout'].flush()
            kwargs['stderr'].write(stderr);kwargs['stderr'].flush()
            return SimpleNamespace(stdin=io.StringIO(),returncode=0,poll=lambda:0)
        with patch('office.engine.require_login'),patch('office.engine.codex_command',return_value=['codex']),patch('office.engine.subprocess.Popen',side_effect=fake):
            return run_codex(store,task,time.time()+10)

    def test_plan_uses_inventory_without_shell_and_worker_keeps_shell(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            store=Store(Path(folder)/'state');store.clock_in();project=store.company_project()
            source=Path(store.project(project)['path']);(source/'README.md').write_text('project');(source/'.env').write_text('secret')
            identifier=store.submit('lead','서비스를 기획하고 개발해줘',delegate=True,project_id=project)
            task=store.claim()
            def check(args,kwargs):
                self.assertIn('features.shell_tool=false',args)
                self.assertIn('read-only',args)
            result=self.execute_fixture(store,task,[{'type':'turn.completed'}],json.dumps({'tasks':[{'role':'dev','prompt':'기능을 개발해 주세요'}]}),check=check)
            self.assertEqual(result['status'],'review')
            store.finish(identifier,result);child=store.claim()
            self.execute_fixture(store,child,[{'type':'turn.completed'}],'개발 결과',check=lambda args,kwargs:self.assertNotIn('features.shell_tool=false',args))

    def test_policy_denial_keeps_output_and_reports_real_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.clock_in();store.submit('dev','파일을 읽고 분석해줘');task=store.claim()
            result=self.execute_fixture(store,task,[{'type':'turn.completed'}],'명령 실행이 막혀 확인하지 못했습니다.',stderr='exec_command failed: rejected: blocked by policy')
            self.assertEqual(result['status'],'failed')
            self.assertIn('실행 정책',result['error']);self.assertIn('확인하지 못했습니다',result['output'])

    def test_internal_process_failure_is_not_success_when_cli_exits_zero(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.clock_in();store.submit('dev','파일을 분석해줘');task=store.claim()
            events=[{'type':'item.completed','item':{'type':'command_execution','status':'failed','exit_code':1,
                     'aggregated_output':'CreateProcessWithLogonW failed: 267'}},{'type':'turn.completed'}]
            result=self.execute_fixture(store,task,events,'보고서만 작성했습니다')
            self.assertEqual(result['status'],'failed')
            self.assertIn('내부 명령 실행',result['error'])

    def test_completed_turn_recovers_transient_error_and_final_file_fallback(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.clock_in();store.submit('dev','설명 문서를 작성해줘');task=store.claim()
            result=self.execute_fixture(store,task,[{'type':'error','message':'retrying transport'},
                    {'type':'item.completed','item':{'type':'agent_message','text':'blocked by policy라는 문구 설명입니다'}},
                    {'type':'turn.completed'}])
            self.assertEqual(result['status'],'review')
            self.assertIn('문구 설명',result['output'])

    def test_empty_result_has_specific_diagnostic(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.clock_in();store.submit('dev','설명 문서를 작성해줘');task=store.claim()
            result=self.execute_fixture(store,task,[{'type':'turn.completed'}])
            self.assertEqual(result['status'],'failed');self.assertIn('최종 결과가 없습니다',result['error'])

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
