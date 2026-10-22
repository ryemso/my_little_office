from datetime import datetime,date
import json
import tempfile
import unittest
from office.store import Store
from office.activity import normalize_state
from scripts.local_office import KST

class ActivityTests(unittest.TestCase):
    def test_live_activity_stale_signal_is_not_completion(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.clock_in();identifier=store.submit('dev','프로그램을 작성해줘')
            store.claim();store.activity(identifier,'search','검색 이벤트',now=100)
            row=next(x for x in store.activity_board(now=101) if x['role']=='dev')
            self.assertEqual(row['state'],'researching');self.assertFalse(row['stale'])
            self.assertTrue(next(x for x in store.activity_board(now=146) if x['role']=='dev')['stale'])
            self.assertEqual(store.get(identifier)['status'],'running')
            store.heartbeat(identifier,now=150)
            self.assertFalse(next(x for x in store.activity_board(now=151) if x['role']=='dev')['stale'])
            store.finish(identifier,{'status':'failed','error':'fixture'})
            self.assertEqual(next(x for x in store.activity_board() if x['role']=='dev')['state'],'error')

    def test_running_work_wins_over_newer_queued_and_stored_state(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.clock_in();first=store.submit('data','실제 분석을 진행해줘');store.claim()
            store.submit('data','두 번째 분석을 진행해줘');store.activity(first,'run','명령 시작')
            self.assertEqual(next(x for x in store.activity_board() if x['role']=='data')['task_id'],first)
        self.assertEqual(normalize_state('working'),'writing')
        with self.assertRaises(ValueError):normalize_state('invented')

    def test_korean_day_boundaries(self):
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.clock_in();identifier=store.submit('dev','일지에 남길 업무')
            day=date(2026,10,22);stamp=datetime(2026,10,22,0,1,tzinfo=KST).timestamp()
            with store.connect() as con:con.execute('UPDATE tasks SET updated=? WHERE id=?',(stamp,identifier))
            self.assertEqual(len(store.daily_memo(day)['tasks']),1)
            self.assertEqual(store.daily_memo(date(2026,10,21))['tasks'],[])

    def test_codex_events_drive_activity_without_changing_task_outcome(self):
        from pathlib import Path
        from office.conversation import LiveEvents
        with tempfile.TemporaryDirectory() as folder:
            store=Store(folder);store.clock_in();identifier=store.submit('dev','작업을 진행해줘');task=store.claim()
            path=Path(folder)/'events.jsonl'
            path.write_text(json.dumps({'type':'item.started','item':{'id':'web','type':'web_search'}})+'\n')
            live=LiveEvents(store,task,path);live.poll()
            self.assertEqual(next(x for x in store.activity_board() if x['role']=='dev')['state'],'researching')
            with path.open('a') as stream:stream.write(json.dumps({'type':'item.completed','item':{'id':'cmd','type':'command_execution','exit_code':1}})+'\n')
            live.poll()
            self.assertEqual(next(x for x in store.activity_board() if x['role']=='dev')['state'],'error')
            self.assertEqual(store.get(identifier)['status'],'running')
