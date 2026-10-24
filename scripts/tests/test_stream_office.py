import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from office.store import Store
from office.engine import Worker, run_codex, require_login

class OfficeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_clockin_and_idempotency(self):
        with self.assertRaises(ValueError):
            self.store.submit('dev', '새로운 기능을 설계해줘')
        self.store.clock_in()
        for _ in range(2):
            self.store.submit('dev', '새로운 기능을 설계해줘', 'same')
        self.assertEqual(len(self.store.tasks()), 1)
        with self.assertRaises(ValueError):
            self.store.submit('dev', '다른 기능을 설계해줘', 'same')

    def test_worker_review_followup_and_completion(self):
        seen = []
        def draft(store, task, end):
            seen.append(task['id'])
            return {'status':'review', 'output':'검토할 결과'}
        worker = Worker(self.store, draft, start=False)
        try:
            self.store.clock_in()
            one = self.store.submit('plan', '새로운 서비스를 기획해줘')
            worker.step(); worker.step()
            self.assertEqual(seen, [one])
            self.assertEqual(self.store.get(one)['status'], 'review')
            self.store.complete(one)
            self.assertEqual(self.store.get(one)['status'], 'completed')
            two = self.store.submit('dev', '기획 내용을 코드로 작성해줘', parent=one)
            self.assertEqual(self.store.get(two)['parent'], one)
        finally:
            worker.close()

    def test_recovery_never_replays_running_task(self):
        self.store.clock_in()
        identifier = self.store.submit('dev', '기능을 구현할 계획을 작성해줘')
        self.store.claim()
        restarted = Store(self.temp.name)
        restarted.recover()
        self.assertEqual(restarted.get(identifier)['status'], 'interrupted')
        self.assertFalse(restarted.status()[0]['on_duty'])

    def test_cancellation_wins_race_with_success(self):
        self.store.clock_in()
        identifier = self.store.submit('dev', '새로운 기능을 설계해줘')
        self.store.claim(); self.store.cancel(identifier)
        self.store.finish(identifier, {'status':'review', 'output':'late result'})
        self.assertEqual(self.store.get(identifier)['status'], 'interrupted')

    def test_quota_pauses_queue(self):
        worker = Worker(self.store, lambda *args: {'status':'quota_wait', 'error':'usage limit'}, start=False)
        try:
            self.store.clock_in()
            self.store.submit('dev', '새로운 기능을 설계해줘')
            second = self.store.submit('plan', '다음 기획을 작성해주세요')
            worker.step(); worker.step()
            self.assertFalse(self.store.status()[0]['on_duty'])
            self.assertEqual(self.store.get(second)['status'], 'queued')
        finally:
            worker.close()

    def test_background_job_survives_without_ui(self):
        started, finish = threading.Event(), threading.Event()
        def draft(*args):
            started.set(); finish.wait(3)
            return {'status':'review','output':'UI와 별개로 완료'}
        worker = Worker(self.store, draft)
        try:
            self.store.clock_in()
            identifier = self.store.submit('dev', '새로운 기능을 설계해줘')
            self.assertTrue(started.wait(3))
            self.assertEqual(self.store.get(identifier)['status'], 'running')
            finish.set()
            for _ in range(40):
                if self.store.get(identifier)['status'] == 'review':break
                time.sleep(.05)
            self.assertEqual(self.store.get(identifier)['status'], 'review')
        finally:
            finish.set(); worker.close()

    def test_legacy_and_new_worker_cannot_overlap(self):
        worker = Worker(self.store, start=False)
        try:
            with self.assertRaises(RuntimeError): Worker(self.store, start=False)
        finally:
            worker.close()

    def test_login_does_not_allow_api_key(self):
        with patch.dict('os.environ', {'OPENAI_API_KEY':'test-only'}), patch('office.engine.shutil.which', return_value='codex'):
            with self.assertRaises(RuntimeError): require_login()

if __name__ == '__main__':unittest.main()

class CodexAdapterTests(unittest.TestCase):
    def test_adapter_uses_stdin_readonly_and_requires_completed_event(self):
        import io
        import json
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            store.clock_in()
            identifier = store.submit('dev','모바일 기능 설계를 작성해줘')
            task = store.claim()
            def fake(args, **kwargs):
                self.assertEqual(args[-1], '-')
                self.assertIn('read-only', args)
                self.assertNotIn(task['prompt'], args)
                Path(args[args.index('-o')+1]).write_text('실행 증거를 갖춘 모의 초안',encoding='utf-8')
                kwargs['stdout'].write(json.dumps({'type':'turn.completed','usage':{'input_tokens':10}})+'\n')
                kwargs['stdout'].flush()
                return SimpleNamespace(stdin=io.StringIO(), returncode=0, poll=lambda:0)
            with patch('office.browser_modes.prepare',return_value=([],{'catalog_verified':True,'fixture':True})),patch('office.engine.require_login'), patch('office.engine.codex_command',return_value=['codex']), patch('office.engine.subprocess.Popen',side_effect=fake):
                result=run_codex(store,task,time.time()+10)
            self.assertEqual(result['status'],'review')
            self.assertEqual(result['usage']['input_tokens'],10)
            def failure(args, **kwargs):
                kwargs['stderr'].write('usage limit reached')
                kwargs['stderr'].flush()
                return SimpleNamespace(stdin=io.StringIO(), returncode=1, poll=lambda:1)
            with patch('office.browser_modes.prepare',return_value=([],{'catalog_verified':True,'fixture':True})),patch('office.engine.require_login'), patch('office.engine.codex_command',return_value=['codex']), patch('office.engine.subprocess.Popen',side_effect=failure):
                self.assertEqual(run_codex(store,task,time.time()+10)['status'],'quota_wait')

    def test_publish_keeps_remote_tasks_and_excludes_pending(self):
        from office.sync import publish
        existing={'version':1,'tasks':[{'id':'other','status':'review'}]}
        def remote(change):change(existing)
        records=[dict(id='one',status='review',role='dev',prompt='공개용 명령',output='초안',error='',created=time.time()),dict(id='two',status='queued')]
        with patch('office.sync.update_remote',side_effect=remote):
            self.assertEqual(publish(records),1)
        self.assertEqual(existing['tasks'][0]['id'],'streamlit-one')
        self.assertEqual(existing['tasks'][1]['id'],'other')

class UnlimitedAttendanceTests(unittest.TestCase):
    def test_clock_in_has_no_count_day_or_midnight_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            with store.connect() as con:
                store._put(con, 'attendance', {'day':'2026-10-21','shifts':[{'end':1},{'end':2}]})
            for number in range(8):
                store.clock_in(now=1792544400+number*86400)
                status, _ = store.status()
                self.assertTrue(status['on_duty'])
                self.assertNotIn('end',status)
                store.pause()
            store.clock_in(now=1)
            # An old start date never expires submission or task claiming.
            identifier = store.submit('dev','제한 없이 이어서 설계해줘')
            self.assertEqual(store.claim()['id'],identifier)

    def test_worker_ignores_expired_legacy_deadline(self):
        with tempfile.TemporaryDirectory() as directory:
            store = Store(directory)
            worker = Worker(store, lambda *args: {'status':'review','output':'계속 근무'}, start=False)
            try:
                with store.connect() as con:
                    store._put(con,'office',{'on_duty':True,'end':1,'message':'근무 중'})
                identifier=store.submit('dev','다음 기능을 설계해줘')
                worker.step()
                self.assertEqual(store.get(identifier)['status'],'review')
                self.assertTrue(store.status()[0]['on_duty'])
                store.pause()
                with self.assertRaises(ValueError):store.submit('dev','퇴근 후 지시 접수 금지')
            finally:worker.close()
