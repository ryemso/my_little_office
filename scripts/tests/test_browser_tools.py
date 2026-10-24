import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from office.browser_tools import prepare,catalog,requested
from office.store import Store
from office.app_server import AppServerRun,Transport

class BrowserToolsTests(unittest.TestCase):
    def test_registered_connector_preserves_environment_and_cwd(self):
        env={'PATH':'unchanged','PRIVATE':'do-not-log'}
        with patch('office.browser_tools.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout=json.dumps([{'name':'chrome-devtools','enabled':True}]))) as run:
            args,enabled=prepare(['codex'],'/work',env,{'prompt':'지피티를 검색해서 질문해'})
        self.assertTrue(enabled);self.assertIn('mcp_servers.chrome-devtools.startup_timeout_sec=60',args)
        self.assertEqual(run.call_args.kwargs['cwd'],'/work');self.assertEqual(run.call_args.kwargs['env'],env)
        self.assertNotIn('do-not-log',json.dumps(args))
    def test_missing_or_disabled_registration_is_not_installed_or_enabled(self):
        with patch('office.browser_tools.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='[]')):
            self.assertEqual(prepare(['codex'],'/work',{}, {'prompt':'Chrome 읽기'}),([],False))
        with patch('office.browser_tools.subprocess.run',return_value=SimpleNamespace(returncode=0,stdout='[{"name":"chrome-devtools","enabled":false}]')):
            with self.assertRaisesRegex(RuntimeError,'비활성화'):prepare(['codex'],'/work',{}, {'prompt':'Chrome 읽기'})
    def test_document_and_plan_do_not_change_tool_setup(self):
        with patch('office.browser_tools.subprocess.run') as run:
            self.assertEqual(prepare(['codex'],'/work',{}, {'prompt':'문서 작성'}),([],False))
            self.assertFalse(requested({'prompt':'Chrome 조회','kind':'plan'}));run.assert_not_called()
    def test_actual_thread_catalog_is_passed_before_turn_and_failure_blocks(self):
        fixture=Path(__file__).resolve().parents[1]/'fixtures/runtime_server.py'
        for mode in ['devtools-ready','devtools-missing']:
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as root:
                store=Store(root);store.clock_in();store.submit('dev','Chrome 탭 목록');task=store.claim()
                transport=Transport([sys.executable,'-u',str(fixture),mode],str(fixture.parent),dict(os.environ))
                runner=AppServerRun(store,task,transport,time.time()+10,browser_requested=True)
                if mode.endswith('missing'):
                    with self.assertRaisesRegex(RuntimeError,'실무 연결 실패'):runner.run('test',root,True,[])
                else:
                    result=runner.run('test',root,True,[])
                    self.assertEqual(result['browser_tools']['tool_count'],2)
                    self.assertFalse(result['browser_tools']['page_verified'])
                    self.assertIn('catalog passed',result['text'])
