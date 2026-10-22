import io
import json
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from office.engine import run_codex
from office.store import Store
from office.connections import connection_status


class AccessTests(unittest.TestCase):
    def test_review_can_write_and_uses_connected_tools_with_chatgpt_auth(self):
        with tempfile.TemporaryDirectory() as directory:
            store=Store(directory);store.clock_in();project=store.company_project()
            store.submit('lead','결과를 검토하고 보완 문서를 작성해줘',project_id=project)
            task=store.claim();task['kind']='report'
            def fake(args,**kwargs):
                self.assertEqual(args[args.index('--cd')+1],kwargs['cwd'])
                self.assertTrue(Path(kwargs['cwd']).is_absolute())
                self.assertNotIn('--ignore-user-config',args)
                self.assertIn('workspace-write',args)
                self.assertIn('features.shell_tool=true',args)
                self.assertIn('web_search="live"',args)
                self.assertIn('forced_login_method="chatgpt"',args)
                self.assertNotIn('danger-full-access',args)
                self.assertEqual(kwargs['env']['GH_TOKEN'],'fixture-github-token')
                (Path(kwargs['cwd'])/'review.md').write_text('실제 파일 검토 결과',encoding='utf-8')
                Path(args[args.index('-o')+1]).write_text('review.md 작성',encoding='utf-8')
                events=[{'type':'item.completed','item':{'id':'web','type':'web_search','action':{'query':'public GitHub source'}}},
                        {'type':'item.completed','item':{'id':'mcp','type':'mcp_tool_call','server':'github','tool':'read_file','status':'completed','arguments':{'token':'private-secret'}}},
                        {'type':'turn.completed'}]
                kwargs['stdout'].write('\n'.join(json.dumps(event) for event in events)+'\n');kwargs['stdout'].flush()
                return SimpleNamespace(stdin=io.StringIO(),returncode=0,poll=lambda:0)
            with patch.dict('os.environ',{'GH_TOKEN':'fixture-github-token'}),patch('office.engine.require_login'),patch('office.engine.codex_command',return_value=['codex']),patch('office.engine.subprocess.Popen',side_effect=fake):
                result=run_codex(store,task,time.time()+10)
            self.assertEqual(result['status'],'review')
            self.assertTrue(any(change['path']=='review.md' for change in result['evidence']['changes']))
            self.assertNotIn('fixture-github-token',json.dumps(result))
            self.assertEqual(result['evidence']['environment']['connected_tools'],'local Codex user config')
            context=result['evidence']['environment']['project']
            self.assertTrue(context['registered'])
            self.assertEqual(context['file_count'],0)
            self.assertFalse(context['git_metadata_copied'])
            self.assertEqual(len(result['evidence']['external_tools']),2)
            self.assertNotIn('private-secret',str(result['evidence']))
            messages=store.transcript(task['id'])
            self.assertTrue(any('웹 조사' in message['body'] for message in messages))
            self.assertTrue(any('github / read_file' in message['body'] for message in messages))

    def test_existing_project_network_migration_and_later_optout(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'project';source.mkdir()
            store=Store(root/'state');project=store.register_project('기존 프로젝트',source,network=False)
            with store.connect() as con:con.execute("DELETE FROM meta WHERE key='employee_access_v1'")
            upgraded=Store(root/'state');self.assertEqual(upgraded.project(project)['network'],1)
            upgraded.set_project_network(project,False)
            self.assertEqual(Store(root/'state').project(project)['network'],0)

    def test_connection_health_does_not_expose_server_config_or_tokens(self):
        def fake(args,**kwargs):
            if 'auth' in args:return SimpleNamespace(returncode=0)
            return SimpleNamespace(returncode=0,stdout=json.dumps([{'name':'github','enabled':True,'env':{'TOKEN':'private-secret'}},{'name':'disabled-server','enabled':False}]))
        with patch('office.connections.shutil.which',return_value='gh'),patch('office.engine.codex_command',return_value=['codex']),patch('office.connections.subprocess.run',side_effect=fake):
            result=connection_status()
        self.assertEqual(result['mcp'],['github'])
        self.assertNotIn('private-secret',str(result))

    def test_new_project_network_is_enabled_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);project=root/'source';project.mkdir()
            store=Store(root/'state');identifier=store.register_project('새 프로젝트',project)
            self.assertEqual(store.project(identifier)['network'],1)
