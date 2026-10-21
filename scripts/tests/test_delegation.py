import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from office.store import Store
from office.engine import Worker
from office.planning import parse_plan, instructions

class DelegationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = Store(self.temp.name)
        self.calls = []
        def run(store, task, end):
            self.calls.append(task)
            if task['kind'] == 'plan':
                output = json.dumps({'tasks':[{'role':'plan','prompt':'고객 문제와 기능을 기획해줘'},{'role':'dev','prompt':'앞 기획을 코드 초안으로 만들어줘'}]})
            else:
                output = '최종 보고입니다' if task['kind'] == 'report' else task['role']+' 제출물'
            return {'status':'review','output':output}
        self.worker = Worker(self.store, run, start=False)
        self.store.clock_in()

    def tearDown(self):
        self.worker.close()
        self.temp.cleanup()

    def root(self):
        return self.store.submit('lead','모바일 서비스를 기획하고 코드 초안까지 작성해줘',delegate=True)

    def test_plan_workers_report_and_idempotent_finishing(self):
        root = self.root()
        self.worker.step()
        self.assertEqual(self.store.get(root)['status'],'delegating')
        self.assertEqual(len(self.store.children(root)),2)
        # Replayed completion after the transaction cannot duplicate employees.
        self.store.finish(root,{'status':'review','output':'invalid replay'})
        self.assertEqual(len(self.store.children(root)),2)
        self.worker.step()
        second = self.store.children(root)[1]
        self.assertIn('plan 제출물',instructions(self.store,second))
        self.worker.step()
        self.assertEqual(self.store.children(root)[-1]['kind'],'report')
        self.worker.step();self.worker.step()
        self.assertEqual([t['kind'] for t in self.calls],['plan','employee','employee','report'])
        self.assertEqual(self.store.get(root)['status'],'review')
        self.assertEqual(self.store.get(root)['output'],'최종 보고입니다')
        self.store.complete(root)
        self.assertEqual(self.store.get(root)['status'],'completed')

    def test_invalid_plan_never_spawns_or_retries(self):
        self.worker.runner=lambda *args:{'status':'review','output':'잘못된 JSON'}
        root=self.root();self.worker.step();self.worker.step()
        self.assertEqual(self.store.get(root)['status'],'failed')
        self.assertFalse(self.store.children(root))
        self.assertFalse(self.store.status()[0]['on_duty'])

    def test_failure_stops_dependent_work_and_root(self):
        root=self.root();self.worker.step()
        self.worker.runner=lambda *args:{'status':'quota_wait','error':'usage limit'}
        self.worker.step()
        self.assertEqual(self.store.get(root)['status'],'blocked')
        self.assertEqual([t['status'] for t in self.store.children(root)],['quota_wait','cancelled'])
        self.assertFalse(self.store.status()[0]['on_duty'])

    def test_cancel_root_cancels_all_unstarted_children(self):
        root=self.root();self.worker.step();self.store.cancel(root);self.worker.step()
        self.assertEqual(self.store.get(root)['status'],'cancelled')
        self.assertTrue(all(t['status']=='cancelled' for t in self.store.children(root)))
        self.assertEqual(len(self.calls),1)

    def test_restart_between_steps_keeps_completed_work(self):
        root=self.root();self.worker.step();self.worker.step()
        first=self.store.children(root)[0]
        self.store.recover();self.store.clock_in()
        self.worker.step();self.worker.step()
        self.assertEqual(self.store.get(first['id'])['output'],'plan 제출물')
        self.assertEqual(self.store.get(root)['status'],'review')
        self.assertEqual(len(self.calls),4)

    def test_crash_during_child_blocks_team(self):
        root=self.root();self.worker.step();self.store.claim()
        self.store.recover()
        self.assertEqual(self.store.get(root)['status'],'blocked')
        self.assertEqual([t['status'] for t in self.store.children(root)],['interrupted','cancelled'])

    def test_plan_bound_and_no_recursive_lead(self):
        for steps in ([],[{'role':'dev','prompt':'업무를 수행해주세요'}]*7,[{'role':'lead','prompt':'재귀 배정해줘'}]):
            with self.assertRaises(ValueError):parse_plan(json.dumps({'tasks':steps}))
        self.assertEqual(len(parse_plan(json.dumps({'tasks':[{'role':'dev','prompt':'업무를 수행해주세요'}]*6}))),6)

    def test_schema_migration_preserves_old_task(self):
        with tempfile.TemporaryDirectory() as directory:
            db=sqlite3.connect(Path(directory)/'office.sqlite3')
            db.execute("CREATE TABLE tasks(id TEXT PRIMARY KEY,role TEXT,prompt TEXT,status TEXT,output TEXT DEFAULT '',error TEXT DEFAULT '',created REAL,updated REAL,parent TEXT,usage TEXT DEFAULT '{}')")
            db.execute("INSERT INTO tasks(id,role,prompt,status,created,updated) VALUES('old','dev','이전 업무 기록','review',1,1)");db.commit();db.close()
            migrated=Store(directory)
            self.assertEqual(migrated.get('old')['kind'],'single')
            self.assertEqual(migrated.get('old')['prompt'],'이전 업무 기록')
