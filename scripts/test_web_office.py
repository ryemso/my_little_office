"""Real browser-to-worker integration with a deterministic runner, no model account."""
from pathlib import Path
import tempfile
import time
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
from office.store import Store
from office.browser_modes import mode
from office.engine import Worker
from office.web_server import WebOffice


def main():
    with tempfile.TemporaryDirectory() as directory,sync_playwright() as playwright:
        store=Store(directory);store.company_project()
        worker=Worker(store,runner=lambda *args:{'status':'review','output':'웹 사무실 실행 결과 확인'})
        app=WebOffice(store,worker,port=0)
        browser=playwright.chromium.launch(headless=True)
        context=browser.new_context()
        context.route('**/*',lambda route:route.continue_() if route.request.url.startswith(app.url+'/') else route.abort())
        page=context.new_page()
        try:
            with patch('office.web_server.require_login'):
                page.goto(app.url+'/#bridge='+app.token)
                expect(page.locator('#runtime-status')).to_contain_text('퇴근',timeout=15000)
                assert 'bridge' not in page.url,'secret must be removed from address bar'
                page.get_by_role('button',name='출근 / 근무 재개',exact=True).click()
                expect(page.locator('#runtime-status')).to_contain_text('근무 중')
                page.locator('#runtime-role').select_option('dev')
                expect(page.locator('#runtime-browser-mode')).to_have_value('standard')
                page.locator('#runtime-browser-mode').select_option('ego')
                expect(page.locator('#runtime-browser-selection')).to_contain_text('현재 선택: ego')
                page.locator('#runtime-command textarea').fill('웹 사무실에서 실제 업무를 지시합니다')
                page.get_by_role('button',name='업무 지시',exact=True).click()
                expect(page.locator('#runtime-chat')).to_contain_text('웹 사무실 실행 결과 확인',timeout=15000)
                assert len(store.tasks())==1
                assert mode(store.tasks()[0])=='ego'
                expect(page.locator('#runtime-browser-mode')).to_have_value('standard')
                page.locator('[data-role="ceo"]').click()
                expect(page.locator('#runtime-dialog')).to_be_visible()
                page.locator('#runtime-dialog').get_by_role('button',name='검토',exact=True).click()
                expect(page.locator('#runtime-decisions')).to_contain_text('적용 브라우저: ego')
                page.get_by_role('button',name='검토 완료',exact=True).click()
                deadline=time.time()+5
                while store.tasks()[0]['status']!='completed' and time.time()<deadline:time.sleep(.05)
                assert store.tasks()[0]['status']=='completed'
                from office.app_server import AppServerRun,Transport
                import os,sys
                fixture=Path(__file__).resolve().parent/'fixtures/runtime_server.py'
                def approval_runner(store,task,end):
                    transport=Transport([sys.executable,'-u',str(fixture)],str(fixture.parent),dict(os.environ))
                    result=AppServerRun(store,task,transport,end).run('오프라인 승인 검증',str(fixture.parent),True,[])
                    return {'status':'review','output':result['text']}
                worker.runner=approval_runner
                page.locator('#runtime-command textarea').fill('두 요청에 대해 대표 승인을 전달하세요')
                page.get_by_role('button',name='업무 지시',exact=True).click()
                expect(page.locator('#runtime-status')).to_contain_text('승인/검토 2건',timeout=15000)
                page.locator('[data-role="ceo"]').click()
                expect(page.locator('[data-runtime-card]')).to_have_count(2)
                page.get_by_role('button',name='이번 요청 허용',exact=True).first.click()
                page.get_by_role('button',name='이번 요청 허용',exact=True).last.click()
                page.get_by_role('button',name='닫기',exact=True).click()
                expect(page.locator('#runtime-chat')).to_contain_text('승인 왕복 모형 완료',timeout=15000)
                assert not store.runtime.list(),'resolved request must leave inbox'
                print('Web office runtime approval: avatar badge, two cards, decisions, resolution and continuation passed')
                page.get_by_role('button',name='퇴근',exact=True).click()
                expect(page.locator('#runtime-status')).to_contain_text('퇴근')
                print('Web office browser: pairing, clock-in, command, conversation, avatar inbox, review and clock-out passed')
        except Exception:
            print('Web office DOM:',page.locator('#work-panel').inner_text()[:6000]);raise
        finally:context.close();browser.close();app.close();worker.close()

if __name__=='__main__':main()
