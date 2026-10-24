import tempfile
import unittest
from office.store import Store

class BatchReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.store.clock_in()
    def reviewed_task(self):
        identifier=self.store.submit('dev','검토 결과 작성 테스트')
        self.store.claim();self.store.finish(identifier,{'status':'review','output':'결과'})
        row=self.store.get(identifier)
        return {'id':identifier,'version':row['updated']}
    def test_multiple_results_complete_without_external_action(self):
        rows=[self.reviewed_task(),self.reviewed_task()]
        self.assertEqual(self.store.complete_many(rows),2)
        self.assertTrue(all(self.store.get(r['id'])['status']=='completed' for r in rows))
    def test_stale_selection_rolls_back_all(self):
        rows=[self.reviewed_task(),self.reviewed_task()];rows[1]['version']-=1
        with self.assertRaises(ValueError):self.store.complete_many(rows)
        self.assertTrue(all(self.store.get(r['id'])['status']=='review' for r in rows))
    def test_running_and_duplicate_are_rejected(self):
        row=self.reviewed_task()
        with self.assertRaises(ValueError):self.store.complete_many([row,row])
        identifier=self.store.submit('dev','아직 실행하지 않은 업무')
        with self.assertRaises(ValueError):self.store.complete_many([{'id':identifier,'version':self.store.get(identifier)['updated']}])
