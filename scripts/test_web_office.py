"""Real browser-to-worker integration with a deterministic runner, no model account."""
from pathlib import Path
import tempfile
import time
from unittest.mock import patch
from playwright.sync_api import sync_playwright,expect
from office.store import Store
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
                page.locator('#runtime-command textarea').fill('웹 사무실에서 실제 업무를 지시합니다')
                page.get_by_role('button',name='업무 지시',exact=True).click()
                expect(page.locator('#runtime-chat')).to_contain_text('웹 사무실 실행 결과 확인',timeout=15000)
                assert len(store.tasks())==1
                page.locator('[data-role="ceo"]').click()
                expect(page.locator('#runtime-dialog')).to_be_visible()
                page.locator('#runtime-dialog').get_by_role('button',name='검토',exact=True).click()
                page.get_by_role('button',name='검토 완료',exact=True).click()
                deadline=time.time()+5
                while store.tasks()[0]['status']!='completed' and time.time()<deadline:time.sleep(.05)
                assert store.tasks()[0]['status']=='completed'
                page.get_by_role('button',name='퇴근',exact=True).click()
                expect(page.locator('#runtime-status')).to_contain_text('퇴근')
                print('Web office browser: pairing, clock-in, command, conversation, avatar inbox, review and clock-out passed')
        except Exception:
            print('Web office DOM:',page.locator('#work-panel').inner_text()[:6000]);raise
        finally:context.close();browser.close();app.close();worker.close()

if __name__=='__main__':main()
