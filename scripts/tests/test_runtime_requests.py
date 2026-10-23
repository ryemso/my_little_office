import json
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from office.store import Store
from office.runtime_requests import public_request, rpc_reply


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name);self.store.clock_in()
        self.task=self.store.submit('dev','실행 중 승인 왕복을 검증하세요')
        self.store.claim();self.b=self.store.runtime
        self.session=self.b.session(self.task);self.b.bind(self.session,'thread','turn')
        self.params={'threadId':'thread','turnId':'turn','itemId':'item','command':'python hello.py','cwd':'/workspace'}

    def add(self, rpc_id=12, params=None, ttl=900):
        return self.b.add(self.session,rpc_id,'item/commandExecution/requestApproval',params or self.params,ttl)

    def decision(self, identifier, choice='accept', content=None):
        row=next(r for r in self.b.list() if r['id']==identifier)
        self.b.decide(identifier,row['version'],row['digest'],choice,content)

    def test_roundtrip_waits_until_runtime_resolution(self):
        identifier=self.add();self.decision(identifier)
        self.assertEqual(self.b.list()[0]['state'],'responding')
        self.assertIsNone(self.store.claim())
        self.b.resolve(self.session,12)
        self.assertEqual(self.b.list(),[])
        self.assertEqual(self.b.list(False)[0]['state'],'accepted')
        self.assertEqual(self.store.get(self.task)['status'],'running')

    def test_double_click_only_one_decision(self):
        identifier=self.add();row=self.b.list()[0]
        def decide():
            try:self.b.decide(identifier,row['version'],row['digest'],'accept');return True
            except ValueError:return False
        with ThreadPoolExecutor(2) as pool:self.assertEqual(sum(pool.map(lambda _:decide(),range(2))),1)

    def test_old_version_digest_and_foreign_thread(self):
        identifier=self.add();row=self.b.list()[0]
        for version,digest in [(0,row['digest']),(row['version'],'changed')]:
            with self.assertRaises(ValueError):self.b.decide(identifier,version,digest,'accept')
        with self.assertRaises(ValueError):self.add(13,dict(self.params,threadId='another'))

    def test_timeout_restart_and_duplicate_ids_are_not_approval(self):
        identifier=self.add(ttl=-1)
        with self.assertRaises(ValueError):self.decision(identifier)
        self.b.recover()
        self.assertEqual(self.b.list(),[])
        with self.assertRaises(ValueError):self.b.decide(identifier,1,'old','accept')
        fresh=self.b.session(self.task);self.b.bind(fresh,'thread','turn')
        self.b.add(fresh,12,'item/commandExecution/requestApproval',self.params)
        self.assertEqual(len(self.b.list()),1)

    def test_rpc_id_type_preserved(self):
        self.add(12);self.add('12')
        self.b.resolve(self.session,12)
        self.assertEqual(len(self.b.list()),1)

    def test_no_secret_or_oauth_url_persisted(self):
        params={'threadId':'thread','turnId':'turn','serverName':'browser','mode':'url','message':'접근을 확인하세요','url':'https://example.test/auth?code=private-code'}
        self.b.add(self.session,'url','mcpServer/elicitation/request',params)
        with self.store.connect() as con:stored=str([tuple(row) for row in con.execute('SELECT * FROM runtime_requests')])
        self.assertNotIn('private-code',stored)
        self.assertIn('https://example.test',stored)
        for name in ['password','otp','token']:
            with self.assertRaises(ValueError):public_request('mcpServer/elicitation/request',dict(params,mode='form',requestedSchema={'type':'object','properties':{name:{'type':'string'}}}))

    def test_enum_boolean_forms_and_memory_only_answers(self):
        params={'threadId':'thread','serverName':'browser','mode':'form','message':'사이트 접근 허용','requestedSchema':{'type':'object','properties':{'allow':{'type':'boolean'}},'required':['allow']}}
        identifier=self.b.add(self.session,2,'mcpServer/elicitation/request',params)
        with self.assertRaises(ValueError):self.decision(identifier,content={'allow':'yes'})
        self.decision(identifier,content={'allow':True})
        self.assertEqual(self.b.take_content(identifier),{'allow':True})
        self.assertIsNone(self.b.take_content(identifier))
        self.assertEqual(rpc_reply('mcpServer/elicitation/request',params,'accept',{'allow':True}),{'action':'accept','content':{'allow':True}})

    def test_secret_question_unknown_method_and_free_text_rejected(self):
        for method,params in [('unknown/request',{}),('item/tool/requestUserInput',{'questions':[{'id':'q','question':'password','isSecret':True}]})]:
            with self.assertRaises(ValueError):public_request(method,params)
        with self.assertRaises(ValueError):public_request('item/commandExecution/requestApproval',dict(self.params,command='echo password=hidden'))

    def test_pending_input_stops_schedule_without_losing_task(self):
        project=self.store.company_project()
        schedule=self.store.add_schedule(project,'dev','예약 작업 검증입니다',time.time(),300)
        with self.store.connect() as con:con.execute('UPDATE schedules SET last_task=? WHERE id=?',(self.task,schedule))
        self.add()
        self.assertEqual(self.store.schedules()[0]['enabled'],0)
        self.assertEqual(self.store.get(self.task)['status'],'running')

    def test_late_resolution_does_not_revive_dead_session(self):
        self.add();self.b.end(self.session);self.b.resolve(self.session,12)
        with self.store.connect() as con:state=con.execute('SELECT state FROM runtime_sessions WHERE id=?',(self.session,)).fetchone()[0]
        self.assertEqual(state,'disconnected')

    def test_quoted_denial_in_successful_document_read_is_not_policy_failure(self):
        from office.runtime_requests import browser_access_denied
        message={'text':'과거 기록: The origin approval gate did not grant access'}
        self.assertFalse(browser_access_denied({'status':'completed','result':message}))
        self.assertTrue(browser_access_denied({'status':'failed','error':message}))

    def test_approval_history_is_scoped_to_current_task(self):
        identifier=self.add();self.decision(identifier);self.b.resolve(self.session,12)
        self.assertEqual(len(self.b.list(False,task_id=self.task)),1)
        self.assertEqual(self.b.list(False,task_id='another-task'),[])

    def test_rejected_form_keeps_shape_without_values(self):
        params={'mode':'openai/form','requestedSchema':{'type':'object','properties':{'password':{'type':'string','default':'never-record-this'}}}}
        diagnostic=self.b.reject(self.session,'mcpServer/elicitation/request',params,ValueError('자유 입력·비밀 입력 양식은 공식 화면에서 직접 처리하세요.'))
        self.assertEqual(diagnostic['shape']['field_shapes'][0]['type'],'string')
        text=json.dumps(self.b.rejections(self.task))
        self.assertNotIn('never-record-this',text);self.assertNotIn('password',text)

    def test_titled_const_enum_uses_same_strict_selection_validation(self):
        params={'threadId':'thread','serverName':'browser','mode':'openai/form','message':'사이트 접근 확인',
                'requestedSchema':{'type':'object','properties':{'decision':{'type':'string','oneOf':[{'const':'allow','title':'이번에 허용'},{'const':'deny','title':'거절'}]}}}}
        identifier=self.b.add(self.session,22,'mcpServer/elicitation/request',params)
        with self.assertRaises(ValueError):self.decision(identifier,content={'decision':'anything'})
        self.decision(identifier,content={'decision':'allow'})
        self.assertEqual(self.b.take_content(identifier),{'decision':'allow'})
