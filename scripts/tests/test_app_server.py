import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from office.store import Store
from office.app_server import AppServerRun, Transport

FIXTURE=Path(__file__).resolve().parents[1]/'fixtures/runtime_server.py'


def fixture_run(store,task,end,mode='accept'):
    transport=Transport([sys.executable,'-u',str(FIXTURE),mode],str(FIXTURE.parent),dict(os.environ))
    return AppServerRun(store,task,transport,end).run('모형 승인 검증',str(FIXTURE.parent),True,[])


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.store.clock_in()
        identifier=self.store.submit('dev','실행 중 승인 요청을 확인하세요')
        self.task=self.store.claim();self.assertEqual(self.task['id'],identifier)

    def background(self,mode='accept'):
        result={}
        def run():
            try:result['value']=fixture_run(self.store,self.task,time.time()+10,mode)
            except Exception as error:result['error']=str(error)
        thread=threading.Thread(target=run);thread.start()
        self.addCleanup(lambda:thread.join(timeout=5))
        return thread,result

    def wait_requests(self):
        until=time.time()+5
        while time.time()<until:
            requests=self.store.runtime.list()
            if len(requests)==2:return requests
            time.sleep(.02)
        self.fail('모형 실행기가 요청을 보내지 않았습니다.')

    def test_subprocess_two_requests_resolve_independently(self):
        thread,result=self.background();requests=self.wait_requests()
        self.assertIsNone(self.store.claim())
        for row in reversed(requests):self.store.runtime.decide(row['id'],row['version'],row['digest'],'accept')
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive());self.assertNotIn('error',result)
        self.assertIn('승인 왕복 모형 완료',result['value']['text'])
        self.assertEqual([r['state'] for r in self.store.runtime.list(False)],['accepted','accepted'])

    def test_decline_cannot_become_successful_report(self):
        thread,result=self.background();requests=self.wait_requests()
        for row in requests:self.store.runtime.decide(row['id'],row['version'],row['digest'],'decline')
        thread.join(timeout=5)
        self.assertIn('거절',result['error']);self.assertNotIn('value',result)

    def test_cancel_while_waiting_invalidates_all_requests(self):
        thread,result=self.background();self.wait_requests();self.store.cancel(self.task['id']);thread.join(timeout=5)
        self.assertIn('중단',result['error']);self.assertEqual(self.store.runtime.list(),[])
        self.assertTrue(all(r['state']=='disconnected' for r in self.store.runtime.list(False)))

    def test_disconnect_is_not_approval(self):
        thread,result=self.background('disconnect');thread.join(timeout=5)
        self.assertIn('연결이 끊겼',result['error']);self.assertNotIn('value',result)

    def test_thread_start_error_preserves_reason_without_credentials(self):
        with self.assertRaises(RuntimeError) as caught:
            fixture_run(self.store,self.task,time.time()+10,'thread-error')
        message=str(caught.exception)
        self.assertIn('thread/start',message)
        self.assertIn('-32602',message)
        self.assertIn('on-request is not allowed',message)
        self.assertNotIn('fixture-private',message)
        self.assertNotIn('not-for-log',message)

    def test_rpc_error_omits_sensitive_data_and_urls(self):
        from office.app_server import rpc_error
        message=rpc_error('thread/start',{'code':-1,'message':'token=private https://example.com/?code=private','data':{'secret':'private'}})
        self.assertNotIn('private',message)
        self.assertIn('[REDACTED]',message)

    def test_probe_failure_updates_last_status(self):
        from office.chrome_connection import latest
        transport=Transport([sys.executable,'-u',str(FIXTURE),'thread-error'],str(FIXTURE.parent),dict(os.environ))
        run=AppServerRun(self.store,self.task,transport,time.time()+10,browser_policy={'required':True,'office_version':'test-new'})
        with self.assertRaises(RuntimeError):run.run_probe(str(FIXTURE.parent),True)
        result=latest(self.store)
        self.assertEqual(result['status'],'EXECUTION_FAILED')
        self.assertEqual(result['office_version'],'test-new')
        self.assertIn('-32602',result['error'])
        self.assertNotIn('fixture-private',result['error'])
