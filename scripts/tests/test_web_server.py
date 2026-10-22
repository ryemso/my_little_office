import json
import tempfile
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch
from office.store import Store
from office.engine import Worker
from office.web_server import WebOffice

class WebServerTests(unittest.TestCase):
    def test_real_http_auth_origin_idempotency_and_chat(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.company_project();worker=Worker(store,start=False);app=WebOffice(store,worker,port=0)
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            def call(path,body=None,token=None,origin=None,method=None):
                headers={'Authorization':'Bearer '+(token or app.token)}
                if origin:headers['Origin']=origin
                req=urllib.request.Request(app.url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers,method=method)
                with opener.open(req,timeout=5) as response:return response.status,response.headers,response.read()
            try:
                self.assertEqual(call('/')[0],200)
                self.assertIn(b'Office',call('/')[2])
                self.assertEqual(call('/data/tasks.json')[0],200)
                with self.assertRaises(urllib.error.HTTPError):call('/api/state',token='wrong')
                with self.assertRaises(urllib.error.HTTPError):call('/api/state',origin='https://untrusted.example')
                status,headers,data=call('/api/health',origin='https://ryemso.github.io')
                self.assertEqual(headers['Access-Control-Allow-Origin'],'https://ryemso.github.io')
                self.assertNotIn(app.token,data.decode())
                with patch('office.web_server.require_login'):
                    call('/api/clock',{'on':True})
                payload={'role':'dev','prompt':'새 화면으로 업무를 진행해줘','request_id':'web-once','project_id':'company'}
                result=json.loads(call('/api/submit',payload)[2]);call('/api/submit',payload)
                self.assertEqual(len(store.tasks()),1)
                self.assertEqual(result['thread'],result['id'])
                self.assertTrue(json.loads(call('/api/messages?task='+result['id'])[2])['messages'])
                self.assertEqual(call('/api/health',origin='https://ryemso.github.io',method='OPTIONS')[1]['Access-Control-Allow-Private-Network'],'true')
                self.assertEqual(store.get(result['id'])['status'],'queued')
            finally:app.close();worker.close()

    def test_stale_approval_is_rejected_and_zip_is_authenticated(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.company_project();worker=Worker(store,start=False);app=WebOffice(store,worker,0)
            try:
                store.clock_in();identifier=store.submit('dev','파일 생성 업무를 수행해줘',project_id='company')
                detail=app.route('GET','/api/detail',{}, {'task':[identifier]})
                with self.assertRaises(ValueError):app.route('POST','/api/decision',{'id':identifier,'action':'approve','version':detail['task']['updated'],'fingerprint':detail['fingerprint']},{})
                archive=app.route('GET','/api/archive',{}, {'task':[identifier]})
                self.assertEqual(archive[1],'application/zip')
            finally:app.close();worker.close()
