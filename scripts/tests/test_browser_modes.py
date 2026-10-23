import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from office.store import Store
from office.browser_modes import mode,overrides,prepare
from office.browser_timing import BrowserTiming
from office.ego_diagnostics import inspect_local,diagnose


class BrowserModeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.store.clock_in()

    def test_default_idempotency_and_immutable_team_snapshot(self):
        identifier=self.store.submit('lead','공개 사이트에서 업무를 수행하세요',identifier='request',delegate=True,browser_mode='ego')
        self.assertEqual(self.store.submit('lead','공개 사이트에서 업무를 수행하세요',identifier='request',delegate=True,browser_mode='ego'),identifier)
        with self.assertRaises(ValueError):self.store.submit('lead','공개 사이트에서 업무를 수행하세요',identifier='request',delegate=True)
        root=self.store.claim()
        self.store.finish(identifier,{'status':'review','output':json.dumps({'tasks':[{'role':'dev','prompt':'공개 사이트를 읽어 보고하세요'}]})})
        child=self.store.claim();self.assertEqual(mode(child),'ego')
        self.store.finish(child['id'],{'status':'review','output':'검토 준비'})
        report=self.store.claim();self.assertEqual(mode(report),'ego')
        fresh=self.store.submit('dev','새 업무는 기본으로 수행하세요')
        self.assertEqual(mode(self.store.get(fresh)),'standard')
        self.assertEqual(mode(Store(self.tmp.name).get(identifier)),'ego')
        self.assertEqual(mode({'context_json':'{}'}),'standard')

    def test_invalid_mode_rejected_before_execution(self):
        for value in ('chrome','EGO',None,[],{}):
            with self.assertRaises(ValueError):self.store.submit('dev','잘못된 설정을 검사하세요',browser_mode=value)
        for context in ('[]','{"browser_mode":"oops"}'):
            with self.assertRaises(ValueError):mode({'context_json':context})

    def test_explicit_retry_preserves_blocked_task_mode(self):
        identifier=self.store.submit('dev','연결 오류 후 재개를 확인하세요',browser_mode='ego')
        self.store.claim();self.store.finish(identifier,{'status':'blocked','error':'연결 실패'})
        self.store.retry_task(identifier)
        self.assertEqual(mode(self.store.get(identifier)),'ego')
        self.assertEqual(self.store.get(identifier)['status'],'queued')

    def test_cli_overrides_preserve_other_servers_and_skill_settings(self):
        config={'skills':{'config':[{'path':'/other/SKILL.md','enabled':False}]},'mcp_servers':{
            'my_browser':{'command':'node','args':['ego-browser']},'gmail':{'url':'https://safe.example/mcp'},'ego_disabled':{'enabled':False}}}
        skills=[{'name':'ego-browser','path':'/ego/SKILL.md','dependencies':{'tools':[{'type':'mcp','value':'my_browser'}]}}]
        args,_,servers=overrides(config,skills,'standard')
        self.assertEqual(set(servers),{'my_browser','ego_disabled'})
        self.assertIn('mcp_servers.my_browser.enabled=false',args)
        self.assertFalse(any('gmail' in a for a in args))
        self.assertIn('enabled=false',args[1])
        args,_,_=overrides(config,skills,'ego')
        self.assertFalse(any('mcp_servers.' in a for a in args))
        self.assertIn('enabled=true',args[1])

    def test_ego_uninstalled_no_fallback(self):
        skills=[{'name':'ego-browser','enabled':True,'path':'/ego/SKILL.md'}]
        with patch('office.browser_modes.Inventory') as cls,patch('office.ego_diagnostics.inspect_local',return_value={'status':'NOT_INSTALLED'}) as check:
            cls.return_value.read.return_value=({},skills)
            with self.assertRaisesRegex(RuntimeError,'NOT_INSTALLED'):prepare({'context_json':'{"browser_mode":"ego"}'},['codex'],'/work',{})
            self.assertEqual(cls.call_count,1);check.assert_called_once()

    def test_effective_catalog_mismatch_blocks_before_inference(self):
        with patch('office.browser_modes.Inventory') as cls:
            cls.return_value.read.return_value=({},[{'name':'ego-browser','enabled':True,'path':'/ego/SKILL.md'}])
            with self.assertRaisesRegex(RuntimeError,'POLICY_BLOCKED'):prepare({},['codex'],'/work',{})

    def test_ego_registered_playwright_action_cannot_silently_switch(self):
        from office.actions import run_action
        result=run_action(self.store,{'context_json':'{"browser_mode":"ego"}'},time.time()+1)
        self.assertEqual(result['status'],'blocked')
        self.assertIn('자동 전환',result['error'])

    def test_schedule_mode_is_saved_and_reused(self):
        project=self.store.company_project()
        schedule=self.store.add_schedule(project,'dev','사이트 내용을 확인하세요',time.time()-1,browser_mode='ego')
        ids=self.store.tick_schedules();self.assertEqual(mode(self.store.get(ids[0])),'ego')
        self.assertEqual(self.store.schedules()[0]['browser_mode'],'ego')

    def test_ego_diagnostics_do_not_persist_cli_output(self):
        with patch('office.ego_diagnostics.shutil.which',return_value=None):
            self.assertEqual(inspect_local()['status'],'NOT_INSTALLED')
        guide='nodejs listTabs useOrCreateTaskSpace openOrReuseTab snapshotText [ego-browser:skill] end of guide'
        def cli(args,**kwargs):
            return SimpleNamespace(returncode=0,stdout=guide if args[-1]=='skill' else 'OFFICE_CONNECTED secret-cookie-value',stderr='')
        with patch('office.ego_diagnostics.shutil.which',return_value='/ego'),patch('office.ego_diagnostics.subprocess.run',side_effect=cli),patch('office.browser_modes.Inventory') as cls:
            cls.return_value.read.return_value=({},[{'name':'ego-browser'}])
            result=diagnose(self.store)
            self.assertEqual(result['status'],'CONNECTED');self.assertFalse(result['page_verified'])
        self.assertNotIn('secret-cookie-value',json.dumps(result))
        self.assertNotIn(b'secret-cookie-value',(Path(self.tmp.name)/'office.sqlite3').read_bytes())

    def test_timing_never_invents_ai_or_inner_browser_durations(self):
        now=[0.0];timing=BrowserTiming(clock=lambda:now[0])
        item={'id':'call','type':'commandExecution','command':'ego-browser nodejs'}
        timing.observe('item/started',item);now[0]=2;timing.observe('item/completed',item);now[0]=3
        timing.approval_wait(True);now[0]=4;timing.approval_wait(False)
        result=timing.summary();self.assertEqual(result['browser_tool_calls'],1)
        self.assertEqual(result['approval_wait_ms'],1000)
        self.assertEqual(result['observed_ms']['browser_tool'],2000)
        self.assertEqual(result['total_ms'],4000);self.assertIsNone(result['ai_inference_ms']);self.assertIsNone(result['snapshot_ms'])
