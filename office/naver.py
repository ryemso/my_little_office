"""Local, visible Naver editor adapter. No passwords or cookies leave the PC."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import time
import unicodedata
from urllib.parse import urlparse, parse_qs
from office.workspaces import target

TITLE='.se-title-text p'
BODY='.se-section-text p'


def blog_id(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]{3,50}',value):raise ValueError('네이버 블로그 ID를 확인하세요.')
    return value


def normalize(value):
    return re.sub(r'\s+',' ',unicodedata.normalize('NFKC',value)).strip()


def read_post(work,name):
    path=target(work,name)
    if not path.is_file() or path.stat().st_size>1_000_000:raise ValueError('게시 JSON 파일이 없거나 너무 큽니다.')
    post=json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(post,dict) or set(post)-{'post_id','title','body','images'}:raise ValueError('게시 JSON 필드를 확인하세요.')
    for key,limit in [('post_id',100),('title',150),('body',100000)]:
        if not isinstance(post.get(key),str) or not 1<=len(post[key].strip())<=limit:raise ValueError('게시 '+key+' 필드를 확인하세요.')
    images=post.get('images',[])
    if not isinstance(images,list) or len(images)>20 or not all(isinstance(x,str) for x in images):raise ValueError('이미지는 프로젝트 상대 경로 배열이어야 합니다 (최대 20개).')
    image_paths=[];hashes=[]
    for name in images:
        image=target(work,name)
        if not image.is_file() or image.suffix.lower() not in ('.jpg','.jpeg','.png','.webp','.gif') or image.stat().st_size>20_000_000:raise ValueError('이미지 경로·형식·크기를 확인하세요: '+name)
        image_paths.append(str(image));hashes.append(hashlib.sha256(image.read_bytes()).hexdigest())
    post=dict(post,images=images)
    digest=hashlib.sha256(json.dumps({'post':post,'images':hashes},sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return post,image_paths,digest


@contextmanager
def profile_lock(root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    stream=(root/'naver-profile.lock').open('a+b')
    try:
        try:
            if os.name=='nt':
                import msvcrt
                stream.seek(0);stream.write(b'0');stream.flush();stream.seek(0)
                msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:raise ValueError('네이버 로그인 창 또는 다른 게시 작업이 사용 중입니다. 먼저 해당 창을 닫으세요.') from None
        yield
    finally:stream.close()


def write_receipt(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


def post_url(value,blog):
    parsed=urlparse(value)
    if parsed.scheme!='https' or parsed.hostname!='blog.naver.com':return False
    if re.fullmatch('/'+re.escape(blog)+r'/\d+',parsed.path):return True
    query=parse_qs(parsed.query)
    return parsed.path=='/PostView.naver' and query.get('blogId')==[blog] and bool(re.fullmatch(r'\d+',query.get('logNo',[''])[0]))


def open_editor(page,blog):
    page.goto('https://blog.naver.com/'+blog+'/postwrite',wait_until='domcontentloaded')
    try:page.locator(TITLE).wait_for(state='visible',timeout=20000)
    except Exception:
        raise RuntimeError('네이버 글쓰기 화면을 열지 못했습니다. 로그인 만료·인증 요청 또는 화면 변경을 확인하세요. 사무실의 네이버 로그인 버튼을 사용하세요.') from None


def editor_matches(page,post):
    title=page.locator(TITLE).inner_text()
    body='\n'.join(page.locator(BODY).all_inner_texts())
    return normalize(title)==normalize(post['title']) and normalize(body)==normalize(post['body'])


def load_draft(page,post):
    page.get_by_role('button',name=re.compile(r'임시저장된 글 보기')).click()
    region=page.get_by_role('region',name='임시저장 글 보기',exact=True)
    candidates=region.get_by_role('button').filter(has=page.locator('strong',has_text=post['title']))
    # Exact title, not a substring or a date, identifies the selected draft.
    matches=[]
    for candidate in candidates.all():
        strong=candidate.locator('strong')
        if strong.count()==1 and strong.inner_text()==post['title']:matches.append(candidate)
    if len(matches)!=1:raise RuntimeError('임시저장 글을 하나로 식별하지 못했습니다. 같은 제목의 글 또는 저장 결과를 확인하세요.')
    matches[0].click()
    page.locator(TITLE).filter(has_text=post['title']).wait_for(timeout=15000)
    if not editor_matches(page,post):raise RuntimeError('임시저장 원문이 승인한 제목·본문과 다릅니다. 발행하지 않습니다.')


def fill_editor(page,post,images):
    if normalize(page.locator(TITLE).inner_text()) not in ('','제목'):
        raise RuntimeError('새 글쓰기 화면에 기존 내용이 있습니다. 자동으로 덮어쓰지 않습니다.')
    page.locator(TITLE).click();page.keyboard.insert_text(post['title'])
    page.locator(BODY).first.click();page.keyboard.insert_text(post['body'])
    for image in images:
        with page.expect_file_chooser(timeout=10000) as chooser:
            page.get_by_role('button',name='사진 추가',exact=True).click()
        chooser.value.set_files(image)
    if not editor_matches(page,post):raise RuntimeError('글쓰기 입력 결과가 원문과 다릅니다. 저장·발행하지 않습니다.')


def verify_article(page,url,blog,post):
    if not post_url(url,blog):raise ValueError('해당 블로그의 HTTPS 게시물 URL이어야 합니다.')
    response=page.goto(url,wait_until='domcontentloaded')
    if response and response.status>=400:raise RuntimeError('게시물 응답 오류')
    surface=page.frame_locator('#mainFrame') if page.locator('#mainFrame').count() else page
    surface.get_by_text(post['title'],exact=True).first.wait_for(timeout=15000)
    if normalize(post['body']) not in normalize(surface.locator('body').inner_text()):
        raise RuntimeError('게시된 본문 검증 실패')
    if len(post.get('images',[]))>surface.locator('.se-section-image').count():
        raise RuntimeError('게시된 이미지 수 검증 실패')


def run_editor(page,root,work,blog,name,mode,task_id,checkpoint=lambda:None):
    blog=blog_id(blog)
    if mode not in ('draft','publish','recover-draft'):raise ValueError('네이버 작업은 draft 또는 publish입니다.')
    post,images,digest=read_post(work,name)
    key=hashlib.sha256((blog+'\0'+post['post_id']).encode()).hexdigest()
    receipt_path=Path(root)/'publishing'/(key+'.json')
    previous=json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else {}
    if previous and previous.get('digest')!=digest:raise ValueError('같은 post_id의 내용이 바뀌었습니다. 새 post_id를 지정하고 다시 검토하세요.')
    if previous.get('state') in ('publishing','uncertain','draft_saving') and mode!='recover-draft':
        raise RuntimeError('이 글은 이전 저장·발행 결과가 불확실합니다. 연결 관리에서 원격 결과 확인 후 재개하세요. 자동 재시도하지 않습니다.')
    checkpoint()
    if previous.get('state')=='published':
        verify_article(page,previous['url'],blog,post)
        return previous
    open_editor(page,blog);checkpoint()
    receipt={'post_id':post['post_id'],'title':post['title'],'digest':digest,'blog':blog,'task_id':task_id,'source':name}
    if mode in ('draft','recover-draft'):
        if mode=='recover-draft' and not previous:raise ValueError('복구할 이전 기록이 없습니다.')
        if mode=='recover-draft' or previous.get('state')=='draft':load_draft(page,post)
        else:
            fill_editor(page,post,images);checkpoint()
            write_receipt(receipt_path,dict(receipt,state='draft_saving'))
            counter=page.get_by_role('button',name=re.compile(r'임시저장된 글 보기'))
            old_count=int(counter.inner_text()) if counter.count() else 0
            page.get_by_role('button',name='저장',exact=True).click()
            until=time.time()+15
            while time.time()<until:
                checkpoint()
                counter=page.get_by_role('button',name=re.compile(r'임시저장된 글 보기'))
                if counter.count() and int(counter.inner_text())>old_count:break
                page.wait_for_timeout(200)
            else:raise RuntimeError('임시 저장 완료를 확인하지 못했습니다. 네이버에서 확인 후 재개하세요.')
            # Reopen on a fresh page and read the stored draft, rather than trusting a click.
            open_editor(page,blog);load_draft(page,post)
        if len(images)>page.locator('article .se-section-image').count():raise RuntimeError('임시 저장된 이미지 수가 다릅니다.')
        receipt.update(state='draft',verified=True)
    else:
        if previous.get('state')!='draft':raise RuntimeError('같은 원문의 임시 저장 검증을 먼저 완료해야 발행할 수 있습니다.')
        load_draft(page,post);checkpoint()
        page.get_by_role('button',name='발행',exact=True).click()
        page.get_by_role('radio',name='전체공개',exact=True).check()
        page.get_by_role('radio',name='현재',exact=True).check()
        buttons=page.get_by_role('button',name='발행',exact=True)
        if buttons.count()!=2:raise RuntimeError('최종 발행 화면을 식별하지 못했습니다. 발행하지 않습니다.')
        checkpoint()
        write_receipt(receipt_path,dict(receipt,state='publishing'))
        try:
            buttons.last.click()
            page.wait_for_url(lambda url:post_url(str(url),blog),timeout=30000)
            # Read the resulting article in a new page, including legacy mainFrame pages.
            url=page.url
            verification=page.context.new_page()
            try:
                verify_article(verification,url,blog,post)
            finally:verification.close()
        except Exception:
            write_receipt(receipt_path,dict(receipt,state='uncertain'))
            raise RuntimeError('발행을 요청했으나 결과를 확인하지 못했습니다. 중복 방지를 위해 재발행을 멈췄습니다. 네이버에서 확인하세요.') from None
        receipt.update(state='published',url=url,verified=True)
    receipt['updated']=time.time()
    write_receipt(receipt_path,receipt)
    evidence=Path(root)/'publishing'/(key+'-'+receipt['state']+'.png')
    try:
        if not post_url(page.url,blog):return receipt
        page.screenshot(path=str(evidence),full_page=False)
        receipt['screenshot']=str(evidence)
    except Exception:receipt['screenshot_error']='화면 저장 실패. 원격 검증 결과는 유지됩니다.'
    return receipt


def _execute_browser(store,task,workspace,argv,end):
    if len(argv) not in (4,5):raise ValueError('네이버 연결 인자 오류')
    _,blog,name,mode=argv[:4]
    approved_fingerprint=workspace.fingerprint()
    action=json.loads(task['action_json'])
    if (mode=='publish' or not action['automatic']) and approved_fingerprint!=task.get('approval_hash'):
        raise ValueError('승인 이후 파일이 바뀌었습니다. 다시 검토하세요.')
    def checkpoint():
        if time.time()>=end or store.get(task['id'])['status']=='cancel_requested':raise RuntimeError('네이버 작업 중단 요청')
        if workspace.fingerprint()!=approved_fingerprint:raise RuntimeError('네이버 실행 중 승인 원문이 변경됐습니다. 다시 검토하세요.')
    try:from playwright.sync_api import sync_playwright
    except ImportError:raise RuntimeError('업데이트로 Playwright를 설치한 뒤 브라우저 실행 준비 버튼을 누르세요.') from None
    from office.browser_accounts import BrowserAccounts
    from office.browser_session import ensure_authenticated
    accounts=BrowserAccounts(store);account=accounts.register(blog_id(blog))
    with profile_lock(store.root/'browser-locks'/account['id']),sync_playwright() as playwright:
        context=playwright.chromium.launch_persistent_context(str(accounts.profile(account)),headless=False)
        try:
            page=context.new_page();page.set_default_timeout(15000)
            ensure_authenticated(page,accounts,account,blog)
            accounts.state(account['id'],'TASK_RUNNING')
            if mode=='verify' and len(argv)==5:
                post,images,digest=read_post(workspace.work,name)
                verify_article(page,argv[4],blog_id(blog),post)
                key=hashlib.sha256((blog+'\0'+post['post_id']).encode()).hexdigest()
                receipt_path=store.root/'publishing'/(key+'.json')
                previous=json.loads(receipt_path.read_text(encoding='utf-8')) if receipt_path.exists() else {}
                if previous and previous.get('digest')!=digest:raise ValueError('원문 지문이 다릅니다.')
                result={'state':'published','post_id':post['post_id'],'title':post['title'],'digest':digest,'blog':blog,'url':argv[4],'verified':True,'updated':time.time(),'task_id':task['id']}
                write_receipt(receipt_path,result)
            else:
                if len(argv)!=4:raise ValueError('네이버 연결 인자 오류')
                result=run_editor(page,store.root,workspace.work,blog,name,mode,task['id'],checkpoint)
            accounts.state(account['id'],'READY')
            accounts.event(account['id'],'RESULT_VERIFIED')
        finally:context.close()
    return {'status':'review','output':('네이버 임시 저장 검증 완료' if result['state']=='draft' else '네이버 게시물 원문 검증 완료')+'\n'+result.get('url',result['title']),
            'error':'','evidence':{'action':{'type':'naver',**result},'changes':workspace.changes()}}


def execute(store,task,workspace,argv,end):
    # A separate interpreter avoids Streamlit/Tornado's Windows event-loop policy.
    import subprocess
    import sys
    import tempfile
    from office.engine import stop_process,safe_diagnostic
    logs=store.root/'logs';logs.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='office-browser-') as directory:
        result_file=Path(directory)/'result.json'
        log_path=logs/('naver-'+hashlib.sha256(task['id'].encode()).hexdigest()[:24]+'.log')
        args=[sys.executable,'-m','office.naver','run','--root',str(store.root),'--task',task['id'],
              '--end',str(end),'--result',str(result_file)]
        kwargs={'start_new_session':True} if os.name!='nt' else {'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP}
        env=dict(os.environ)
        for key in ('OPENAI_API_KEY','CODEX_API_KEY'):env.pop(key,None)
        with log_path.open('w',encoding='utf-8') as log:
            process=subprocess.Popen(args,cwd=Path(__file__).resolve().parents[1],env=env,stdout=log,stderr=subprocess.STDOUT,**kwargs)
            try:
                while process.poll() is None:
                    if time.time()>=end or store.get(task['id'])['status']=='cancel_requested' or log_path.stat().st_size>8_000_000:
                        stop_process(process)
                        return {'status':'interrupted','error':'네이버 작업을 중단했습니다. 이미 요청된 발행 결과는 네이버에서 확인하세요.'}
                    time.sleep(.2)
            finally:
                if process.poll() is None:stop_process(process)
        if result_file.is_file():return json.loads(result_file.read_text(encoding='utf-8'))
        raise RuntimeError('네이버 브라우저 실행 실패: '+safe_diagnostic(log_path.read_text(encoding='utf-8',errors='replace'))[-1500:]+' · 진단 파일: '+str(log_path))


def login(root,blog):
    """The user signs in normally in a dedicated local browser, without exporting sessions."""
    from playwright.sync_api import sync_playwright
    root=Path(root)
    status=root/'naver-login.json'
    from office.store import Store
    from office.browser_accounts import BrowserAccounts
    from office.browser_session import ensure_authenticated
    accounts=BrowserAccounts(Store(root));account=accounts.register(blog_id(blog))
    try:
        with profile_lock(root/'browser-locks'/account['id']),sync_playwright() as playwright:
            context=playwright.chromium.launch_persistent_context(str(accounts.profile(account)),headless=False)
            try:
                page=context.new_page()
                write_receipt(status,{'status':'waiting','message':'열린 브라우저에서 직접 로그인하세요. 인증·CAPTCHA는 직접 처리하세요.'})
                ensure_authenticated(page,accounts,account,blog,manual=True)
                write_receipt(status,{'status':'ready','message':'글쓰기 화면 접근 확인. 로그인 창을 닫았습니다.','updated':time.time()})
            finally:context.close()
    except Exception as error:
        write_receipt(status,{'status':'failed','message':type(error).__name__+' · 브라우저 설치·로그인·열린 창을 확인하세요.'})


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['login','run']);parser.add_argument('--root',required=True);parser.add_argument('--blog');parser.add_argument('--task');parser.add_argument('--end',type=float);parser.add_argument('--result')
    args=parser.parse_args()
    if args.command=='login':
        if not args.blog:parser.error('--blog required')
        login(args.root,args.blog)
    else:
        if not args.task or args.end is None or not args.result:parser.error('--task, --end, --result required')
        from office.store import Store
        from office.workspaces import Workspace
        from office.engine import exception_result
        store=Store(args.root)
        try:
            task=store.get(args.task)
            if not task or task['status']!='running':raise ValueError('실행 중인 업무가 아닙니다.')
            workspace=Workspace(store,task);project=workspace.prepare()
            if not project or not project.get('network'):raise ValueError('네트워크 사용 프로젝트가 필요합니다.')
            result=_execute_browser(store,task,workspace,json.loads(json.loads(task['action_json'])['argv']),args.end)
        except Exception as error:result=exception_result(store,error)
        Path(args.result).write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8')
