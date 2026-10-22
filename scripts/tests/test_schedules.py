import json
import tempfile
import unittest
from office.store import Store

class ScheduleTests(unittest.TestCase):
    def test_off_duty_overdue_coalesces_and_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);project=store.company_project()
            sid=store.add_schedule(project,'dev','예약 분석 수행',100,300)
            self.assertEqual(store.tick_schedules(1000),[])
            store.clock_in();queued=store.tick_schedules(1000)
            self.assertEqual(len(queued),1)
            self.assertEqual(store.tick_schedules(1000),[])
            row=store.schedules()[0]
            self.assertEqual(row['next_due'],1300)
            # An in-flight run prevents overlap even at the next due time.
            self.assertEqual(store.tick_schedules(1300),[])
            task=store.claim();store.finish(task['id'],{'status':'failed','error':'fixture'})
            self.assertEqual(store.tick_schedules(1300),[])
            self.assertFalse(store.schedules()[0]['enabled'])

    def test_enqueue_crash_reuses_deterministic_task(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);store.clock_in();p=store.company_project()
            sid=store.add_schedule(p,'dev','한 번 실행 업무',100)
            first=store.tick_schedules(100)[0]
            with store.connect() as con:con.execute('UPDATE schedules SET enabled=1,last_task=NULL WHERE id=?',(sid,))
            self.assertEqual(store.tick_schedules(100),[first])
            self.assertEqual(len(store.tasks()),1)

    def test_retry_preserves_finished_predecessors_and_requires_action_approval(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root);store.clock_in();p=store.company_project()
            action=store.register_action(p,'게시','destination',['fixture'])
            identifier=store.submit('lead','순서대로 처리해줘',delegate=True,project_id=p)
            store.claim();store.finish(identifier,{'status':'review','output':json.dumps({'tasks':[
                {'role':'dev','prompt':'파일 생성 수행'}, {'role':'data','prompt':'분석을 실행해줘'},
                {'role':'market','prompt':'게시를 실행해줘','action':action}]})})
            first=store.claim();store.finish(first['id'],{'status':'review','output':'first'})
            failed=store.claim();store.finish(failed['id'],{'status':'failed','error':'fixture'})
            self.assertEqual(store.get(identifier)['status'],'blocked')
            store.retry_task(identifier)
            children=store.children(identifier)
            self.assertEqual([x['status'] for x in children],['review','queued','awaiting_approval'])
            self.assertEqual(store.get(identifier)['status'],'delegating')
