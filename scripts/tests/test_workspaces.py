import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from office.store import Store
from office.workspaces import Workspace,files
from office.engine import run_codex,Worker
from office.actions import run_action

class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name)
        self.store=Store(self.base/'state');self.source=self.base/'project';self.source.mkdir()
        (self.source/'notes.txt').write_text('원래 자료',encoding='utf-8')
        self.project=self.store.register_project('테스트 프로젝트',self.source)
        self.store.clock_in()

    def tearDown(self):self.temp.cleanup()

    def task(self):
        identifier=self.store.submit('dev','加算機能を実装し테스트 프로젝트してください',project_id=self.project)
        return self.store.claim()

    def test_actual_file_edit_test_evidence_and_apply(self):
        task=self.task();actual_popen=subprocess.Popen
        def fake_codex(args,**kwargs):
            self.assertIn('workspace-write',args)
            cwd=Path(kwargs['cwd'])
            (cwd/'calc.py').write_text('def add(a,b):\n    return a+b\n')
            (cwd/'test_calc.py').write_text('import unittest\nfrom calc import add\nclass Calc(unittest.TestCase):\n    def test_add(self):self.assertEqual(add(2,3),5)\n')
            test=actual_popen([sys.executable,'-m','unittest','test_calc'],cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
            log,_=test.communicate(timeout=10)
            events=[{'type':'item.completed','item':{'type':'command_execution','command':'python -m unittest test_calc','exit_code':test.returncode,'status':'completed','aggregated_output':log}},{'type':'turn.completed','usage':{}}]
            kwargs['stdout'].write('\n'.join(json.dumps(e) for e in events));kwargs['stdout'].flush()
            Path(args[args.index('-o')+1]).write_text('実装と테스트 프로젝트を実行しました',encoding='utf-8')
            return SimpleNamespace(stdin=io.StringIO(),returncode=0,poll=lambda:0)
        with patch('office.engine.require_login'),patch('office.engine.codex_command',return_value=['codex']),patch('office.engine.subprocess.Popen',side_effect=fake_codex):
            result=run_codex(self.store,task,time.time()+20)
        self.assertEqual(result['status'],'review')
        self.assertEqual(result['evidence']['commands'][0]['exit_code'],0)
        self.assertFalse((self.source/'calc.py').exists())
        self.store.finish(task['id'],result);self.store.pause()
        self.assertEqual(Workspace(self.store,task).apply(),2)
        self.assertTrue((self.source/'calc.py').exists())
        self.assertEqual((self.source/'notes.txt').read_text(encoding='utf-8'),'원래 자료')

    def test_apply_refuses_new_user_edits_and_keeps_secrets_out(self):
        (self.source/'.env').write_text('secret')
        task=self.task();workspace=Workspace(self.store,task);workspace.prepare()
        self.assertFalse((workspace.work/'.env').exists())
        (workspace.work/'notes.txt').write_text('AI edit')
        self.store.finish(task['id'],{'status':'review','output':'done'});self.store.pause()
        (self.source/'notes.txt').write_text('new user edit')
        with self.assertRaises(ValueError):workspace.apply()
        self.assertEqual((self.source/'notes.txt').read_text(),'new user edit')

    def test_team_shares_workspace_and_project_id(self):
        root=self.store.submit('lead','개발하고 확인해 주세요',delegate=True,project_id=self.project)
        task=self.store.claim();workspace=Workspace(self.store,task);workspace.prepare()
        self.store.finish(root,{'status':'review','output':json.dumps({'tasks':[{'role':'dev','prompt':'기능을 작성해 주세요'},{'role':'data','prompt':'기능을 검증해 주세요'}]})})
        child=self.store.claim()
        self.assertEqual(child['project_id'],self.project)
        second=Workspace(self.store,child);second.prepare()
        self.assertEqual(second.work,workspace.work)

    def test_registered_action_requires_approval_then_runs_real_command(self):
        action=self.store.register_action(self.project,'preview receipt','local verification',[sys.executable,'-c',"from pathlib import Path;Path('receipt.txt').write_text('published fixture')"])
        root=self.store.submit('lead','연결한 작업을 실행해 주세요',delegate=True,project_id=self.project)
        task=self.store.claim();workspace=Workspace(self.store,task);workspace.prepare()
        self.store.finish(root,{'status':'review','output':json.dumps({'tasks':[{'role':'market','prompt':'등록된 작업을 실행해 주세요','action':action}]})})
        child=self.store.children(root)[0]
        self.assertEqual(child['status'],'awaiting_approval')
        self.assertIsNone(self.store.claim())
        self.store.approve(child['id'],workspace.fingerprint())
        child=self.store.claim();result=run_action(self.store,child,time.time()+15)
        self.assertEqual(result['status'],'review')
        self.assertEqual(result['evidence']['action']['exit_code'],0)
        self.assertTrue((workspace.work/'receipt.txt').exists())

    def test_unregistered_action_never_queued(self):
        root=self.store.submit('lead','홍보물을 게시해 주세요',delegate=True,project_id=self.project)
        self.store.claim()
        self.store.finish(root,{'status':'review','output':json.dumps({'tasks':[{'role':'market','prompt':'게시를 실행해 주세요','action':'not-connected'}]})})
        self.assertEqual(self.store.get(root)['status'],'failed')
        self.assertFalse(self.store.children(root))

    def test_approval_cannot_be_reused_after_file_changes(self):
        action={'name':'no execution','target':'local','argv':json.dumps([sys.executable,'-c','pass']),'automatic':0}
        task=self.task();workspace=Workspace(self.store,task);workspace.prepare()
        task.update(action_json=json.dumps(action),approval_hash=workspace.fingerprint())
        (workspace.work/'new.txt').write_text('changed')
        self.assertEqual(run_action(self.store,task,time.time()+10)['status'],'failed')

    def test_failed_test_receipt_is_not_reported_as_success(self):
        task=self.task()
        def fake(args,**kwargs):
            kwargs['stdout'].write(json.dumps({'type':'item.completed','item':{'type':'command_execution','command':'python -m unittest','exit_code':1,'status':'failed'}})+'\n'+json.dumps({'type':'turn.completed'}))
            kwargs['stdout'].flush()
            Path(args[args.index('-o')+1]).write_text('검증에 실패한 상태입니다',encoding='utf-8')
            return SimpleNamespace(stdin=io.StringIO(),returncode=0,poll=lambda:0)
        with patch('office.engine.require_login'),patch('office.engine.codex_command',return_value=['codex']),patch('office.engine.subprocess.Popen',side_effect=fake):
            result=run_codex(self.store,task,time.time()+10)
        self.assertEqual(result['status'],'failed')
        self.assertIn('테스트',result['error'])

    def test_pre_authorized_connection_is_queued_without_extra_approval(self):
        action=self.store.register_action(self.project,'local approved action','local fixture',[sys.executable,'-c','pass'],automatic=True)
        root=self.store.submit('lead','허용한 연결 작업을 실행해줘',delegate=True,project_id=self.project)
        self.store.claim()
        self.store.finish(root,{'status':'review','output':json.dumps({'tasks':[{'role':'dev','prompt':'허용한 작업을 실행해줘','action':action}]})})
        child=self.store.claim()
        self.assertEqual(child['status'],'queued')
        self.assertTrue(json.loads(child['action_json'])['automatic'])
