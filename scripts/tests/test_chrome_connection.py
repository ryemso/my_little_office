import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from office.store import Store
from office.app_server import AppServerRun,Transport
from office.chrome_connection import launch_overrides,inspect_catalog,required,skill_snapshot,browser_count

FIXTURE=Path(__file__).resolve().parents[1]/'fixtures/runtime_server.py'


class ChromeConnectionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.store.clock_in()
        identifier=self.store.submit('dev','Chrome 연결 상태 확인')
        self.task=self.store.claim()

    def runner(self,mode='chrome-ready'):
        transport=Transport([sys.executable,'-u',str(FIXTURE),mode],str(FIXTURE.parent),dict(os.environ))
        return AppServerRun(self.store,self.task,transport,time.time()+10,browser_policy={'required':True})

    def test_existing_cua_probe_uses_actual_tool_and_drops_private_response(self):
        result=self.runner().run_probe(str(FIXTURE.parent),True)
        data=result['browser_tools']
        self.assertEqual(data['status'],'CHROME_CONNECTED')
        self.assertTrue(data['tool_call_verified'])
        self.assertNotIn('fixture-secret',json.dumps(result))
        self.assertNotIn(b'fixture-secret',(Path(self.tmp.name)/'office.sqlite3').read_bytes())

    def test_missing_runtime_blocks_before_model_turn_and_no_report_file(self):
        with self.assertRaisesRegex(RuntimeError,'BRIDGE_NOT_PROVIDED'):
            self.runner('chrome-missing').run('Chrome을 읽어라',str(FIXTURE.parent),True,[])
        self.assertFalse(list(Path(self.tmp.name).rglob('source-review.md')))
        with self.store.connect() as con:
            self.assertEqual(self.store._get(con,'chrome_diagnostic',{})['status'],'BRIDGE_NOT_PROVIDED')

    def test_new_node_bridge_is_not_reported_as_restored_legacy_cua(self):
        result=self.runner('chrome-node-only').run_probe(str(FIXTURE.parent),True)
        self.assertEqual(result['browser_tools']['status'],'LEGACY_CUA_MISSING')
        self.assertFalse(result['browser_tools']['tool_call_verified'])

    def test_declined_probe_is_not_retried_via_different_server(self):
        result={};runner=self.runner('chrome-approval')
        def run():
            try:result['value']=runner.run_probe(str(FIXTURE.parent),True)
            except RuntimeError as error:result['error']=str(error)
        thread=threading.Thread(target=run);thread.start()
        until=time.time()+5
        while time.time()<until and not self.store.runtime.list():time.sleep(.02)
        requests=self.store.runtime.list();self.assertEqual(len(requests),1)
        row=requests[0];self.store.runtime.decide(row['id'],row['version'],row['digest'],'decline')
        thread.join(timeout=5);self.assertFalse(thread.is_alive())
        self.assertIn('거절',result['error']);self.assertNotIn('value',result)
        self.assertEqual(len(self.store.runtime.list(False)),1)

    def test_repair_is_scoped_and_does_not_reenable_disabled_servers(self):
        root=Path(self.tmp.name)
        config={'mcp_servers':{'cua_repl':{'command':sys.executable,'args':[str(FIXTURE)],'cwd':str(root/'gone')},'node_repl':{'enabled':False,'command':'missing'}}}
        original=json.dumps(config)
        args,disabled,policy=launch_overrides(config,[],root)
        self.assertIn('mcp_servers.cua_repl.required=true',args)
        self.assertTrue(any('mcp_servers.cua_repl.cwd=' in value for value in args))
        self.assertFalse(any('node_repl' in value for value in args))
        self.assertEqual(json.dumps(config),original)
        self.assertEqual(policy['repairs'],[{'provider':'cua_repl','change':'stable_cwd'}])

    def test_relative_launcher_keeps_its_original_working_directory(self):
        args,_,policy=launch_overrides({'mcp_servers':{'cua_repl':{'command':'node','args':['launch.mjs'],'cwd':'/missing'}}},[],Path(self.tmp.name))
        self.assertFalse(any('.cwd=' in value for value in args));self.assertEqual(policy['repairs'],[])

    def test_skill_runtime_mismatch_has_hashes_without_raw_document_or_paths(self):
        root=Path(self.tmp.name);skill=root/'26.1021.31345'/'SKILL.md';skill.parent.mkdir()
        skill.write_text('mcp__node_repl__js is required; fixture-secret')
        args,disabled,policy=launch_overrides({'mcp_servers':{'cua_repl':{'command':sys.executable}}},[{'name':'control-in-app-browser','path':str(skill),'enabled':True}],root)
        self.assertEqual(disabled,[str(skill)])
        self.assertEqual(policy['skills'][0]['bridge'],'node_repl')
        self.assertEqual(policy['skills'][0]['version'],'26.1021.31345')
        self.assertNotIn('fixture-secret',json.dumps(policy));self.assertNotIn(str(root),json.dumps(policy))

    def test_denied_existing_cua_cannot_fall_back_to_node(self):
        def rpc(*args):return {'data':[{'name':'cua_repl','toolsError':'policy denied secret-token','tools':{}},{'name':'node_repl','runtimeStatus':'connected','tools':{'js':{'name':'js'}}}]}
        result,_=inspect_catalog(rpc,'thread')
        self.assertEqual(result['status'],'POLICY_BLOCKED');self.assertIsNone(result['selected'])
        self.assertNotIn('secret-token',json.dumps(result))

    def test_browser_declaration_is_validated_and_handed_to_children(self):
        from office.planning import parse_plan
        with self.assertRaises(ValueError):parse_plan(json.dumps({'tasks':[{'role':'dev','prompt':'Chrome 연결 확인','browser_required':'yes'}]}))
        self.store.finish(self.task['id'],{'status':'review','output':'진단 대기'})
        root=self.store.submit('lead','원고 확인 후 브라우저로 게시하세요',delegate=True)
        self.store.claim();self.store.finish(root,{'status':'review','output':json.dumps({'tasks':[{'role':'dev','prompt':'먼저 원문을 확보하세요','browser_required':True},{'role':'data','prompt':'원고 파일을 검토하세요','browser_required':False}]})})
        first,second=self.store.children(root)
        self.assertTrue(required(first));self.assertFalse(required(second))
        self.store.claim();self.store.finish(first['id'],{'status':'blocked','error':'BRIDGE_NOT_PROVIDED'})
        self.assertEqual(self.store.get(second['id'])['status'],'cancelled')
        self.assertEqual(self.store.get(root)['status'],'blocked')

    def test_snapshot_from_another_task_is_not_current_evidence(self):
        from office.chrome_connection import latest,record_snapshot
        record_snapshot(self.store,{'task_id':'older','status':'CHROME_CONNECTED','chrome_connection_verified':True})
        self.assertEqual(latest(self.store,self.task['id'])['status'],'NOT_CHECKED')

    def test_host_diagnostic_and_model_task_cannot_share_request_id(self):
        self.store.submit('dev','既存 Chrome 接続確認',identifier='probe',host_operation='chrome_probe')
        with self.assertRaises(ValueError):self.store.submit('dev','既存 Chrome 接続確認',identifier='probe')

    def test_browser_count_does_not_treat_documentation_as_connection(self):
        self.assertEqual(browser_count({'content':[{'text':'The Chrome browser supports browsers=[]'}]}),0)
        self.assertEqual(browser_count({'browsers':[{'name':'Chrome','id':'1','connected':False}]}),0)
        self.assertEqual(browser_count({'structuredContent':{'browsers':[{'name':'Chrome','id':'1','url':'private'}]}}),1)
