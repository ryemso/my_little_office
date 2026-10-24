import json
from pathlib import Path
import tempfile
import unittest
from office.store import Store
from office.inbox import approve_decision
from office.workspaces import Workspace


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name);self.store.clock_in()

    def review(self):
        identifier=self.store.submit('dev','실제 결과를 검토해 주세요');self.store.claim()
        self.store.finish(identifier,{'status':'review','output':'검토할 결과물입니다'})
        return identifier

    def approval(self):
        project=self.store.company_project()
        action=self.store.register_action(project,'미리보기','preview destination',['echo','fixture'])
        root=self.store.submit('lead','미리보기를 배포해 주세요',delegate=True,project_id=project);self.store.claim()
        self.store.finish(root,{'status':'review','output':json.dumps({'tasks':[{'role':'market','prompt':'미리보기 배포를 진행해 주세요','action':action}]})})
        return self.store.children(root)[0]

    def test_reviews_clear_after_completion_and_survive_restart(self):
        identifier=self.review()
        self.assertEqual(self.store.pending_decisions()[0]['decision_type'],'review')
        restarted=Store(self.temp.name)
        self.assertEqual(restarted.pending_decisions()[0]['id'],identifier)
        restarted.complete(identifier)
        self.assertEqual(restarted.pending_decisions(),[])

    def test_employee_submissions_do_not_duplicate_owner_review(self):
        root=self.store.submit('lead','기획하고 개발해 주세요',delegate=True);self.store.claim()
        self.store.finish(root,{'status':'review','output':json.dumps({'tasks':[{'role':'dev','prompt':'실제 파일을 작성해 주세요'}]})})
        child=self.store.claim();self.store.finish(child['id'],{'status':'review','output':'개발 제출'})
        self.assertEqual(self.store.pending_decisions(),[])
        report=self.store.claim();self.store.finish(report['id'],{'status':'review','output':'총괄 보고'})
        self.assertEqual([entry['id'] for entry in self.store.pending_decisions()],[root])

    def test_approval_rejects_unreviewed_changes_then_accepts_current_snapshot(self):
        task=self.approval();workspace=Workspace(self.store,task);workspace.prepare()
        fingerprint=workspace.fingerprint()
        (workspace.work/'new.txt').write_text('changed after dialog opened')
        with self.assertRaises(ValueError):approve_decision(self.store,task['id'],task['updated'],fingerprint)
        self.assertEqual(self.store.get(task['id'])['status'],'awaiting_approval')
        approve_decision(self.store,task['id'],task['updated'],workspace.fingerprint())
        self.assertEqual(self.store.get(task['id'])['status'],'queued')
        self.assertEqual(self.store.pending_decisions(),[])

    def test_error_acknowledgement_is_versioned_and_does_not_complete_task(self):
        identifier=self.store.submit('dev','문제를 점검해 주세요');self.store.claim()
        self.store.finish(identifier,{'status':'failed','error':'fixture failure'})
        task=self.store.get(identifier)
        self.store.acknowledge_decision(identifier,task['updated'])
        self.assertEqual(Store(self.temp.name).pending_decisions(),[])
        self.assertEqual(self.store.get(identifier)['status'],'failed')
        with self.store.connect() as con:con.execute('UPDATE tasks SET updated=updated+1 WHERE id=?',(identifier,))
        self.assertEqual(len(self.store.pending_decisions()),1)
        with self.assertRaises(ValueError):self.store.acknowledge_decision(identifier,task['updated'])

    def test_dialog_review_and_close(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        from unittest.mock import patch
        from office.engine import Worker
        instances=[]
        def factory(store):
            worker=Worker(store,start=False);instances.append(worker)
            source=Path(self.temp.name)/'source-ui';source.mkdir()
            project=store.register_project('검토 프로젝트',source)
            store.clock_in();identifier=store.submit('dev','완료 결과를 검토해주세요',project_id=project);store.claim()
            store.finish(identifier,{'status':'review','output':'실제 결과 미리보기'})
            return worker
        st.cache_resource.clear()
        try:
            with patch('scripts.local_office.STATE',Path(self.temp.name)/'ui'),patch('office.engine.Worker',side_effect=factory):
                app=AppTest.from_file(str(Path(__file__).resolve().parents[2]/'streamlit_app.py')).run(timeout=15)
                next(button for button in app.button if button.key=='open-owner-inbox').click().run()
                self.assertFalse(app.exception)
                self.assertTrue(any('실제 결과 미리보기' in item.value for item in app.markdown))
                next(button for button in app.button if str(button.key).startswith('inbox-follow-')).click().run()
                self.assertFalse(app.exception)
                self.assertFalse(app.session_state.inbox_open)
                task=instances[0].store.tasks()[0]
                self.assertEqual(app.session_state.parent_task,task['id'])
                self.assertEqual(app.session_state.project_choice,task['project_id'])
                self.assertEqual(app.session_state.selected_role,'dev')
                next(button for button in app.button if button.key=='open-owner-inbox').click().run()
                next(button for button in app.button if str(button.key).startswith('inbox-complete-')).click().run()
                self.assertFalse(app.exception)
                self.assertEqual(instances[0].store.pending_decisions(),[])
                next(button for button in app.button if button.label=='검토함 닫기').click().run()
                self.assertFalse(app.session_state.inbox_open)
        finally:
            for worker in instances:worker.close()
            st.cache_resource.clear()

    def test_dialog_approval_queues_exact_action(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        from unittest.mock import patch
        from office.engine import Worker
        instances=[];tasks=[]
        def factory(store):
            worker=Worker(store,start=False);instances.append(worker)
            project=store.company_project();store.clock_in()
            action=store.register_action(project,'프리뷰 배포','preview destination',['echo','preview'])
            root=store.submit('lead','프리뷰 배포를 검토해주세요',delegate=True,project_id=project);store.claim()
            store.finish(root,{'status':'review','output':json.dumps({'tasks':[{'role':'market','prompt':'등록된 프리뷰 배포를 수행해주세요','action':action}]})})
            tasks.append(store.children(root)[0]['id'])
            return worker
        st.cache_resource.clear()
        try:
            with patch('scripts.local_office.STATE',Path(self.temp.name)/'approval-ui'),patch('office.engine.Worker',side_effect=factory):
                app=AppTest.from_file(str(Path(__file__).resolve().parents[2]/'streamlit_app.py')).run(timeout=15)
                next(button for button in app.button if button.key=='open-owner-inbox').click().run()
                self.assertFalse(app.exception)
                self.assertTrue(any('preview destination' in item.value for item in app.markdown))
                next(button for button in app.button if str(button.key).startswith('inbox-approve-')).click().run()
                self.assertFalse(app.exception)
                self.assertEqual(instances[0].store.get(tasks[0])['status'],'queued')
                self.assertEqual(instances[0].store.pending_decisions(),[])
        finally:
            for worker in instances:worker.close()
            st.cache_resource.clear()
