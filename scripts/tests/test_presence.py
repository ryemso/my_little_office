import json
import tempfile
import unittest
import urllib.request
import urllib.error
from office.store import Store
from office.presence import PresenceServer,issue_key,visitors,revoke

class PresenceTests(unittest.TestCase):
    def test_real_http_auth_scope_revocation_and_expiry(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);identifier,key=issue_key(store,'외부 분석가');server=PresenceServer(store,0)
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            def call(path,body=None,token=key,origin=None):
                headers={'Authorization':'Bearer '+token}
                if origin:headers['Origin']=origin
                req=urllib.request.Request(server.url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
                with opener.open(req,timeout=5) as response:return json.load(response)
            try:
                self.assertEqual(call('/agent-push',{'state':'search','detail':'자료 조사'})['scope'],'presence-only')
                self.assertEqual(visitors(store)[0]['state'],'researching')
                self.assertTrue(visitors(store)[0]['online'])
                seen=visitors(store)[0]['seen']
                self.assertFalse(visitors(store,seen+61)[0]['online'])
                self.assertNotIn(key,json.dumps(call('/agents')))
                for path,body,kwargs in [('/agent-push',{'state':'run'},{'token':'wrong'}),('/agent-push',{'state':'run','prompt':'do work'},{}),('/agent-push',{'state':'run'},{'origin':'https://example.com'}),('/execute',{'state':'run'}, {})]:
                    with self.assertRaises(urllib.error.HTTPError):call(path,body,**kwargs)
                self.assertEqual(store.tasks(),[])
                revoke(store,identifier)
                with self.assertRaises(urllib.error.HTTPError):call('/agent-push',{'state':'run'})
                self.assertFalse(visitors(store)[0]['online'])
                with store.connect() as con:
                    raw=str(dict(con.execute('SELECT * FROM visitors').fetchone()))
                self.assertNotIn(key,raw)
            finally:server.close()
