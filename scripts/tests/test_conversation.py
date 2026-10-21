import json
from pathlib import Path
import tempfile
import unittest
from office.store import Store
from office.conversation import LiveEvents


class ConversationTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.store=Store(self.temp.name);self.store.clock_in()

    def test_delegation_followup_and_restart_share_one_channel_without_duplicates(self):
        root=self.store.submit('lead','서비스를 개발하고 분석해줘','root',delegate=True)
        self.store.submit('lead','서비스를 개발하고 분석해줘','root',delegate=True)
        self.store.claim()
        plan={'status':'review','output':json.dumps({'tasks':[{'role':'dev','prompt':'서비스를 구현해 주세요'},{'role':'data','prompt':'데이터를 분석해 주세요'}]})}
        self.store.finish(root,plan);self.store.finish(root,plan)
        first=self.store.claim()
        self.store.message(first['id'],'command','dev','progress','명령 실행 시작\npython test.py')
        self.store.finish(first['id'],{'status':'review','output':'개발 결과입니다'})
        second=self.store.claim();self.store.finish(second['id'],{'status':'review','output':'분석 결과입니다'})
        report=self.store.claim();self.assertEqual(report['kind'],'report')
        self.store.finish(report['id'],{'status':'review','output':'총괄 최종 보고입니다'})
        follow=self.store.submit('dev','구현한 기능을 보완해줘',parent=first['id'])
        self.assertEqual(self.store.thread_id(follow),root)
        messages=self.store.transcript(root)
        self.assertEqual(sum(m['kind']=='assignment' for m in messages),2)
        self.assertEqual(sum(m['body']=='서비스를 개발하고 분석해줘' for m in messages),1)
        self.assertIn('owner',{m['actor'] for m in messages})
        self.assertTrue({'lead','dev','data'}.issubset({m['actor'] for m in messages}))
        self.assertFalse(any(m['body']==plan['output'] for m in messages))
        restarted=Store(self.temp.name)
        self.assertEqual(restarted.transcript(root),messages)
        self.assertEqual(len(restarted.channels()),1)

    def test_live_partial_json_dedup_sanitizes_and_ignores_reasoning(self):
        identifier=self.store.submit('dev','코드를 점검해 주세요')
        task=self.store.claim();path=Path(self.temp.name)/'live.jsonl';path.write_bytes(b'')
        tail=LiveEvents(self.store,task,path)
        event={'type':'item.started','item':{'id':'command1','type':'command_execution','command':'echo sk-abcdefghijklmnop123456789'}}
        encoded=(json.dumps(event)+'\n').encode()
        path.write_bytes(encoded[:25]);tail.poll()
        self.assertFalse(any(m['kind']=='progress' for m in self.store.transcript(identifier)))
        with path.open('ab') as file:file.write(encoded[25:])
        tail.poll();tail.poll()
        with path.open('a') as file:
            file.write(json.dumps({'type':'item.completed','item':{'type':'reasoning','text':'private reasoning'}})+'\n')
            file.write(json.dumps({'type':'item.completed','item':{'id':'a1','type':'agent_message','text':'공개 진행 메시지'}})+'\n')
        tail.poll()
        messages=self.store.transcript(identifier)
        self.assertEqual(sum(m['event_key'].startswith('live:item.started') for m in messages),1)
        self.assertNotIn('sk-abcdefgh',str(messages));self.assertNotIn('private reasoning',str(messages))
        with path.open('a') as file:file.write(json.dumps({'type':'item.completed','item':{'id':'last','type':'command_execution','command':'pytest','exit_code':0}}))
        tail.poll(final=True)
        self.assertTrue(any('종료 코드 0' in m['body'] for m in self.store.transcript(identifier)))
        self.store.finish(identifier,{'status':'review','output':'공개 진행 메시지'})
        self.assertEqual(sum(m['body']=='공개 진행 메시지' for m in self.store.transcript(identifier)),1)

    def test_history_pagination_and_recovery(self):
        identifier=self.store.submit('dev','작업을 진행해 주세요');self.store.claim()
        for number in range(210):self.store.message(identifier,str(number),'dev','progress',str(number))
        page=self.store.messages(identifier,200)
        older=self.store.messages(identifier,200,before=page[0]['id'])
        self.assertEqual(len(page),200)
        self.assertTrue(set(m['id'] for m in page).isdisjoint(m['id'] for m in older))
        self.store.recover();self.store.recover()
        self.assertEqual(sum(m['event_key']=='recovered' for m in self.store.transcript(identifier)),1)

    def test_old_database_backfill_is_marked_and_chronological(self):
        first=self.store.submit('dev','이전 작업을 작성해줘');self.store.claim()
        self.store.finish(first,{'status':'review','output':'이전 결과'})
        self.store.submit('data','이전 결과를 분석해줘',parent=first)
        with self.store.connect() as con:
            con.execute('DELETE FROM messages');con.execute("DELETE FROM meta WHERE key='chat_backfill_v1'")
        restarted=Store(self.temp.name);messages=restarted.transcript(first)
        self.assertEqual(len(messages),3)
        self.assertTrue(all(m['historical'] for m in messages))
        self.assertEqual([m['created'] for m in messages],sorted(m['created'] for m in messages))
        self.assertEqual(Store(self.temp.name).transcript(first),messages)

    def test_followup_preserves_attached_sources(self):
        from office.knowledge import upload
        source=upload(self.store,'reference.txt',b'reference context')
        parent=self.store.submit('dev','첨부 자료를 읽어주세요',source_ids=[source])
        child=self.store.submit('dev','그 자료로 수정해주세요',parent=parent)
        context=json.loads(self.store.get(child)['context_json'])
        self.assertEqual(context['selected_ids'],[source])

    def test_chat_ui_renders_roles_and_accepts_followup(self):
        import streamlit as st
        from streamlit.testing.v1 import AppTest
        from unittest.mock import patch
        from office.engine import Worker
        st.cache_resource.clear()
        workers=[]
        def create_worker(store):
            worker=Worker(store,runner=lambda *args:{'status':'review','output':'개발 결과를 제출합니다'},start=False)
            workers.append(worker);return worker
        try:
            with patch('scripts.local_office.STATE',Path(self.temp.name)/'ui'),patch('office.engine.Worker',side_effect=create_worker),patch('office.engine.require_login'):
                app=AppTest.from_file(str(Path(__file__).resolve().parents[2]/'streamlit_app.py')).run(timeout=15)
                next(button for button in app.button if button.label=='출근 / 근무 재개').click().run()
                next(select for select in app.selectbox if select.label=='담당 직원').select('dev')
                next(text for text in app.text_area if text.label=='업무 지시').input('대화형 업무 기록을 작성해줘')
                next(button for button in app.button if button.label=='업무 지시').click().run()
                workers[0].step();app.run()
                self.assertFalse(app.exception)
                self.assertGreaterEqual(len(app.chat_message),4)
                self.assertTrue(any('대표 ·' in caption.value for caption in app.caption))
                self.assertTrue(any('개발 ·' in caption.value for caption in app.caption))
                app.chat_input[0].set_value('그 결과를 보완해 주세요').run()
                self.assertFalse(app.exception)
                self.assertEqual(len(workers[0].store.tasks()),2)
                self.assertEqual(len(workers[0].store.channels()),1)
                app.run()
                self.assertEqual(len(workers[0].store.tasks()),2)
        finally:
            for worker in workers:worker.close()
            st.cache_resource.clear()
