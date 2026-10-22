import base64
import json
from pathlib import Path
import tempfile
import time
import unittest
from office.github_publish import publish_workspace, repository
from office.store import Store
from office.workspaces import Workspace

class GitHubPublishTests(unittest.TestCase):
    def workspace(self,folder):
        store=Store(folder);store.clock_in();project=store.company_project()
        identifier=store.submit('dev','실제 파일 생성',project_id=project)
        work=Workspace(store,store.get(identifier));work.prepare()
        (work.work/'result.txt').write_text('result')
        return work

    def test_branch_commit_is_read_back_and_main_is_not_updated(self):
        with tempfile.TemporaryDirectory() as folder:
            work=self.workspace(folder);calls=[]
            def api(method,path,body):
                calls.append((method,path,body))
                if path=='':return {'default_branch':'main'}
                if path.startswith('git/matching-refs/'):return []
                if path=='git/ref/heads/main':return {'object':{'sha':'head'}}
                if path=='git/commits/head':return {'tree':{'sha':'base'}}
                if path=='git/trees/base':return {'tree':[]}
                if path=='git/blobs':return {'sha':'blob'}
                if path=='git/trees':return {'sha':'tree'}
                if path=='git/commits':return {'sha':'commit'}
                if path=='git/refs':return {}
                if path.startswith('git/ref/heads/office/'):return {'object':{'sha':'commit'}}
                self.fail(path)
            receipt=publish_workspace(work,'owner/repo','task',time.time()+30,api=api)
            self.assertTrue(receipt['verified'])
            ref=next(body for method,path,body in calls if path=='git/refs')
            self.assertTrue(ref['ref'].startswith('refs/heads/office/'))
            self.assertFalse(any(method=='PATCH' for method,path,body in calls))

    def test_remote_conflict_blocks_all_writes(self):
        with tempfile.TemporaryDirectory() as folder:
            work=self.workspace(folder);writes=[]
            def api(method,path,body):
                if method!='GET':writes.append(path);self.fail('must not write')
                if path=='':return {'default_branch':'main'}
                if path.startswith('git/matching-refs/'):return []
                if path=='git/ref/heads/main':return {'object':{'sha':'head'}}
                if path=='git/commits/head':return {'tree':{'sha':'base'}}
                if path=='git/trees/base':return {'tree':[{'path':'result.txt','type':'blob','mode':'100644','sha':'existing'}]}
                if path=='git/blobs/existing':return {'content':base64.b64encode(b'other').decode()}
                self.fail(path)
            with self.assertRaisesRegex(ValueError,'충돌'):
                publish_workspace(work,'owner/repo','task',time.time()+30,api=api)
            self.assertEqual(writes,[])

    def test_invalid_repository_and_cancellation(self):
        for value in ['https://github.com/a/b','a/b/c','../b','-x']:
            with self.assertRaises(ValueError):repository(value)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaisesRegex(RuntimeError,'중단'):
                publish_workspace(self.workspace(folder),'owner/repo','task',time.time()+30,cancelled=lambda:True,api=lambda *a:self.fail('cancelled'))
