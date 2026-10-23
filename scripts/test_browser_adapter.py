"""Real Chromium integration against an intercepted editor fixture, never Naver production."""
import json
from pathlib import Path
import tempfile
from playwright.sync_api import sync_playwright
from office.naver import run_editor

EDITOR='''<!doctype html><html lang="ko"><meta charset="utf-8"><body>
<button id="save">저장</button><button id="drafts" aria-label="임시저장된 글 보기, 0개">0</button>
<button id="publish">발행</button><section id="settings" hidden>
<label><input type="radio" name="access" checked>전체공개</label>
<label><input type="radio" name="when" checked>현재</label><button id="final">발행</button></section>
<article><div class="se-title-text"><p contenteditable="true" id="title"></p></div>
<div class="se-section-text"><p contenteditable="true" id="body"></p></div></article>
<section id="list" role="region" aria-label="임시저장 글 보기" hidden></section>
<script>
const saved=()=>JSON.parse(localStorage.getItem('drafts')||'[]');
const counter=()=>{const n=saved().length;document.querySelector('#drafts').textContent=n;document.querySelector('#drafts').setAttribute('aria-label','임시저장된 글 보기, '+n+'개');};counter();
document.querySelector('#save').onclick=()=>{let items=saved();items.push({title:document.querySelector('#title').innerText,body:document.querySelector('#body').innerText});localStorage.setItem('drafts',JSON.stringify(items));counter();};
document.querySelector('#drafts').onclick=()=>{const region=document.querySelector('#list');region.replaceChildren();region.hidden=false;for(const item of saved()){let b=document.createElement('button');let strong=document.createElement('strong');strong.textContent=item.title;b.append(strong);b.onclick=()=>{document.querySelector('#title').innerText=item.title;document.querySelector('#body').innerText=item.body;region.hidden=true;};region.append(b);}};
document.querySelector('#publish').onclick=()=>document.querySelector('#settings').hidden=false;
document.querySelector('#final').onclick=()=>{localStorage.setItem('published',JSON.stringify({title:document.querySelector('#title').innerText,body:document.querySelector('#body').innerText}));localStorage.setItem('publishCount',Number(localStorage.getItem('publishCount')||0)+1);location.href='/qt0177/123';};
</script></body></html>'''
ARTICLE='''<!doctype html><html lang="ko"><meta charset="utf-8"><body><h1 id="title"></h1><article id="body"></article><script>const post=JSON.parse(localStorage.getItem('published'));document.querySelector('#title').textContent=post.title;document.querySelector('#body').textContent=post.body;</script></body></html>'''


def login_fixture(playwright, root):
    from office.store import Store
    from office.browser_accounts import BrowserAccounts
    from office.browser_session import ensure_authenticated
    accounts=BrowserAccounts(Store(root/'auth'))
    account=accounts.register('qt0177')
    with accounts.store.connect() as con:
        con.execute('UPDATE browser_accounts SET auto_login=1 WHERE id=?',(account['id'],))
    browser=playwright.chromium.launch(headless=True)
    context=browser.new_context()
    def handle(route):
        if 'nid.naver.com' in route.request.url:
            body='''<input id="id"><input id="pw" type="password"><button id="log.login" onclick="location.href='https://blog.naver.com/qt0177/postwrite?authenticated=1'">login</button>'''
            route.fulfill(content_type='text/html',body=body)
        elif 'authenticated=1' in route.request.url:
            route.fulfill(content_type='text/html',body=EDITOR)
        else:route.fulfill(status=302,headers={'Location':'https://nid.naver.com/nidlogin.login'},body='')
    context.route('https://**/*',handle)
    class FixtureVault:
        def get(self, identifier):return 'fixture-user','fixture-password'
    page=context.new_page()
    try:
        ensure_authenticated(page,accounts,account,'qt0177',vault_factory=FixtureVault)
        assert accounts.get(account['id'])['state']=='READY'
        assert accounts.verify_audit()
        print('Real Chromium fixture: expired session, allowed login origin, automatic relogin and audit passed')
    except Exception:
        print('Login fixture diagnostics:',page.url,page.locator('input').evaluate_all('(nodes)=>nodes.map(node=>node.id)'),page.locator('button').evaluate_all('(nodes)=>nodes.map(node=>node.id)'))
        raise
    finally:context.close();browser.close()


def main():
    with tempfile.TemporaryDirectory() as folder,sync_playwright() as playwright:
        root=Path(folder);login_fixture(playwright,root)
        work=root/'work';work.mkdir()
        (work/'post.json').write_text(json.dumps({'post_id':'fixture-1','title':'연결 검증 제목','body':'실제 브라우저 입력 검증\n두 번째 문단'},ensure_ascii=False),encoding='utf-8')
        browser=playwright.chromium.launch(headless=True)
        context=browser.new_context()
        context.route('https://blog.naver.com/**',lambda route:route.fulfill(content_type='text/html; charset=utf-8',body=EDITOR if '/postwrite' in route.request.url else ARTICLE))
        page=context.new_page()
        try:
            draft=run_editor(page,root,work,'qt0177','post.json','draft','draft-task')
            assert draft['state']=='draft' and draft['verified']
            published=run_editor(page,root,work,'qt0177','post.json','publish','publish-task')
            assert published['state']=='published' and published['url']=='https://blog.naver.com/qt0177/123'
            reused=run_editor(page,root,work,'qt0177','post.json','publish','retry-task')
            assert reused['state']=='published'
            assert page.evaluate("localStorage.getItem('publishCount')")=='1','duplicate publication'
            print('Real Chromium fixture: input, save/reopen, publication, article verification, duplicate prevention passed')
        except Exception:
            print('Fixture title:',repr(page.locator('.se-title-text p').all_inner_texts()))
            print('Fixture body:',repr(page.locator('.se-section-text p').all_inner_texts()))
            raise
        finally:context.close();browser.close()

if __name__=='__main__':main()
