import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

class StreamlitUITests(unittest.TestCase):
    def test_direct_command_review_and_followup(self):
        try:
            import streamlit as st
            from streamlit.testing.v1 import AppTest
        except ImportError:
            self.skipTest('Install requirements.txt to run Streamlit UI tests')
        from office.engine import Worker
        instances = []
        def create_worker(store):
            worker = Worker(store, runner=lambda *args: {'status':'review', 'output':'모의 실행 결과: 기능 명세 초안'})
            instances.append(worker)
            return worker
        st.cache_resource.clear()
        with tempfile.TemporaryDirectory() as directory, patch('scripts.local_office.STATE',Path(directory)), patch('office.engine.Worker',side_effect=create_worker), patch('office.engine.require_login'):
            try:
                app = AppTest.from_file(str(Path(__file__).resolve().parents[2] / 'streamlit_app.py')).run(timeout=15)
                self.assertFalse(app.exception)
                self.assertNotIn('오늘 근무 구간', [m.label for m in app.metric])
                self.assertNotIn('남은 시간', [m.label for m in app.metric])
                next(b for b in app.button if b.label=='출근 / 근무 재개').click().run()
                app.selectbox[0].select('dev')
                app.text_area[0].input('모바일 첫 화면 개선안을 작성해줘')
                next(b for b in app.button if b.label=='업무 지시').click().run()
                for _ in range(30):
                    if instances[0].store.tasks() and instances[0].store.tasks()[0]['status']=='review':break
                    time.sleep(.1)
                app.run()
                self.assertFalse(app.exception)
                self.assertEqual(instances[0].store.tasks()[0]['role'],'dev')
                self.assertEqual(instances[0].store.tasks()[0]['status'],'review')
                # Submitting the untouched form is idempotent.
                next(b for b in app.button if b.label=='업무 지시').click().run()
                self.assertEqual(len(instances[0].store.tasks()),1)
                next(b for b in app.button if b.label=='추가 지시 / 다시 진행').click().run()
                app.text_area[0].input('그 개선안에 대한 코드 초안을 작성해줘')
                next(b for b in app.button if b.label=='업무 지시').click().run()
                self.assertEqual(len(instances[0].store.tasks()),2)
                self.assertTrue(instances[0].store.tasks()[0]['parent'])
                next(b for b in app.button if b.label=='업무 지시').click().run()
                self.assertEqual(len(instances[0].store.tasks()),2)
                next(b for b in app.button if b.label=='퇴근 · 현재 작업 중단').click().run()
                self.assertFalse(instances[0].store.status()[0]['on_duty'])
                self.assertFalse(app.exception)
            finally:
                for worker in instances:worker.close()
                st.cache_resource.clear()
