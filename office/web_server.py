"""Authenticated loopback worker API and static office; independent of Streamlit."""
import argparse
import base64
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
from urllib.parse import urlparse,parse_qs
import webbrowser
from office.store import Store
from office.engine import Worker,require_login,safe_diagnostic
from office.workspaces import Workspace
from office.inbox import approve_decision
from scripts.local_office import STATE

SITE=Path(__file__).resolve().parents[1]/'site'


class WebOffice:
    def __init__(self,store,worker,port=8501,token=None):
        self.store=store;self.worker=worker;self.token=token or secrets.token_urlsafe(32)
        owner=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def setup(self):super().setup();self.connection.settimeout(15)
            def origin_ok(self):
                origin=self.headers.get('Origin')
                return not origin or origin in ('https://ryemso.github.io',owner.url,'http://localhost:'+str(owner.server.server_address[1]))
            def host_ok(self):return self.headers.get('Host','') in ('127.0.0.1:'+str(owner.server.server_address[1]),'localhost:'+str(owner.server.server_address[1]))
            def respond(self,status,value,kind='application/json; charset=utf-8',filename=None):
                data=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
                self.send_response(status)
                self.send_header('Content-Type',kind);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
                if self.origin_ok() and self.headers.get('Origin'):
                    self.send_header('Access-Control-Allow-Origin',self.headers['Origin']);self.send_header('Vary','Origin')
                if filename:self.send_header('Content-Disposition','attachment; filename="'+filename+'"')
                try:self.end_headers();self.wfile.write(data)
                except (ConnectionError,BrokenPipeError):self.close_connection=True
            def do_OPTIONS(self):
                if not self.host_ok() or not self.origin_ok():self.respond(403,{'error':'origin rejected'});return
                self.send_response(204);self.send_header('Access-Control-Allow-Origin',self.headers.get('Origin',owner.url));self.send_header('Vary','Origin');self.send_header('Access-Control-Allow-Methods','GET, POST, OPTIONS');self.send_header('Access-Control-Allow-Headers','Authorization, Content-Type');self.send_header('Access-Control-Allow-Private-Network','true');self.end_headers()
            def dispatch(self):
                if not self.host_ok() or not self.origin_ok():self.respond(403,{'error':'origin rejected'});return
                parsed=urlparse(self.path);path=parsed.path;query=parse_qs(parsed.query)
                if not path.startswith('/api/'):
                    if self.command!='GET':self.respond(405,{'error':'method rejected'});return
                    name='index.html' if path=='/' else path.lstrip('/')
                    local=(SITE/name).resolve()
                    if not local.is_relative_to(SITE.resolve()) or not local.is_file() or local.suffix not in ('.html','.js','.css','.svg','.json'):
                        self.respond(404,{'error':'not found'});return
                    kinds={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.svg':'image/svg+xml','.json':'application/json; charset=utf-8'}
                    self.respond(200,local.read_bytes(),kinds[local.suffix]);return
                supplied=self.headers.get('Authorization','')
                if not secrets.compare_digest(supplied.encode(),('Bearer '+owner.token).encode()):self.respond(401,{'error':'PC 연결 코드가 없거나 만료됐습니다.'});return
                try:
                    body={}
                    if self.command=='POST':
                        length=int(self.headers.get('Content-Length','0'))
                        if not 0<length<=15_000_000:raise ValueError('요청 크기를 확인하세요.')
                        body=json.loads(self.rfile.read(length))
                        if not isinstance(body,dict):raise ValueError('JSON 객체가 필요합니다.')
                    result=owner.route(self.command,path,body,query)
                    if isinstance(result,tuple):self.respond(200,*result)
                    else:self.respond(200,result)
                except (ValueError,KeyError,TypeError,OSError,RuntimeError) as error:self.respond(400,{'error':safe_diagnostic(str(error))[:1200]})
                except Exception:self.respond(500,{'error':'PC 요청 처리 실패. 로컬 실행 로그를 확인하세요.'})
            do_GET=dispatch
            do_POST=dispatch
        self.server=ThreadingHTTPServer(('127.0.0.1',port),Handler);self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True,name='office-web');self.thread.start()
    @property
    def url(self):return 'http://127.0.0.1:'+str(self.server.server_address[1])
    def task(self,identifier):
        task=self.store.get(identifier)
        if not task:raise ValueError('업무를 찾을 수 없습니다.')
        return task
    def route(self,method,path,b,q):
        store=self.store
        if method=='GET':
            if path=='/api/state':
                from office.presence import visitors
                return {'office':store.status()[0],'projects':store.projects(),'tasks':store.tasks(),'activity':store.activity_board(),
                        'runtime_requests':store.runtime.list(),'decisions':store.pending_decisions(),'channels':store.channels(),'schedules':store.schedules(),'visitors':visitors(store)}
            if path=='/api/messages':return {'messages':store.messages(store.thread_id(q['task'][0]),before=int(q['before'][0]) if 'before' in q else None)}
            if path=='/api/detail':
                task=self.task(q['task'][0]);workspace=Workspace(store,task);workspace.prepare()
                return {'task':task,'fingerprint':workspace.fingerprint() if task['project_id'] else '', 'preview':workspace.preview() if task['project_id'] else ''}
            if path=='/api/archive':
                task=self.task(q['task'][0]);workspace=Workspace(store,task);workspace.prepare()
                return workspace.archive(),'application/zip','office-output.zip'
            if path=='/api/sources':
                from office import knowledge
                return {'sources':knowledge.sources(store,q.get('project',[None])[0]),'profile':knowledge.profile(store)}
            if path=='/api/chrome':
                from office.chrome_connection import latest
                result=dict(latest(store));result['current_server_version']='0.20.5';return result
            if path=='/api/ego':
                from office.ego_diagnostics import status
                return status(store)
            if path=='/api/runtime':
                from office.runtime_diagnostics import status
                return status(store)
            if path=='/api/runtime/url':
                from office.app_server import external_url
                return {'url':external_url(store,q['id'][0])}
            if path=='/api/health':return {'ok':True,'version':'0.20.5','runtime':'web-worker'}
            if path=='/api/daily':
                from datetime import date
                return store.daily_memo(date.fromisoformat(q['day'][0]))
            if path=='/api/browser-accounts':
                from office.browser_accounts import BrowserAccounts
                return {'accounts':BrowserAccounts(store).list()}
            if path=='/api/connections':
                from office.connections import connection_status
                return connection_status()
            if path=='/api/setup-status':
                result={}
                file=store.root/'naver-login.json'
                if file.exists():result['login']=json.loads(file.read_text(encoding='utf-8'))
                result['processes']={k:process.poll() for k,process in getattr(self,'setup_processes',{}).items()}
                return result
        if method!='POST':raise ValueError('지원하지 않는 요청입니다.')
        if path=='/api/clock':
            if b['on']:require_login();store.clock_in()
            else:store.pause()
        elif path=='/api/chrome-probe':
            identifier=store.submit('dev','기존 Chrome 연결 복구 진단: 실제 cua_repl 도구와 연결 상태만 확인합니다. 로그인·게시·설정 변경은 하지 않습니다.',identifier=b['request_id'],project_id=b['project_id'],browser_mode='standard',host_operation='chrome_probe')
            return {'id':identifier,'thread':store.thread_id(identifier)}
        elif path=='/api/ego-diagnose':
            from office.ego_diagnostics import diagnose
            return diagnose(store,page=b.get('page') is True)
        elif path=='/api/submit':
            identifier=store.submit(b['role'],b['prompt'],identifier=b['request_id'],parent=b.get('parent'),delegate=bool(b.get('delegate')),project_id=b['project_id'],source_ids=b.get('source_ids',[]),browser_mode=b.get('browser_mode','standard'))
            return {'id':identifier,'thread':store.thread_id(identifier)}
        elif path=='/api/attention-batch':return {'acknowledged':store.acknowledge_many(b.get('items'))}
        elif path=='/api/review-batch':return {'completed':store.complete_many(b.get('items'))}
        elif path=='/api/decision':
            task=self.task(b['id']);action=b['action']
            if action=='approve':approve_decision(store,task['id'],b['version'],b['fingerprint'])
            elif action=='complete':store.complete(task['id'])
            elif action=='cancel':store.cancel(task['id'])
            elif action=='retry':store.retry_task(task['id'])
            elif action=='ack':store.acknowledge_decision(task['id'],b['version'])
            elif action=='apply':Workspace(store,task).apply()
            else:raise ValueError('지원하지 않는 조치입니다.')
        elif path=='/api/runtime-mode':
            if b.get('mode') not in ('exec','appserver'):raise ValueError('실행기 종류를 확인하세요.')
            if store.has_active_work():raise ValueError('실행 중에는 실행기를 변경할 수 없습니다.')
            if b['mode']=='appserver':
                if b.get('acknowledged') is not True:raise ValueError('대화형 시험 모드와 사용자 승인 요청을 확인하세요.')
                from office.runtime_diagnostics import diagnose
                result=diagnose(store)
                if not result.get('supported'):raise ValueError('연결 진단의 CLI 버전을 확인하세요.')
            with store.connect() as con:store._put(con,'runtime_mode',b['mode'])
        elif path=='/api/runtime-diagnose':
            from office.runtime_diagnostics import diagnose
            return diagnose(store)
        elif path=='/api/runtime-decision':
            store.runtime.decide(b['id'],b['version'],b['digest'],b['choice'],b.get('content'))
        elif path=='/api/project':return {'id':store.register_project(b['name'],b['path'],network=bool(b.get('network',True)))}
        elif path=='/api/network':store.set_project_network(b['id'],bool(b['enabled']))
        elif path=='/api/profile':
            from office.knowledge import save_profile
            save_profile(store,b['text'])
        elif path=='/api/source':
            from office import knowledge
            scope=b.get('scope','company');project=b.get('project_id')
            if b.get('url'):knowledge.link(store,b['url'],scope=scope,project_id=project)
            else:knowledge.upload(store,b['name'],base64.b64decode(b['data'],validate=True),scope=scope,project_id=project)
        elif path=='/api/smoke':
            from office.smoke import PROMPT
            return {'id':store.submit('data',PROMPT,project_id=b['project_id'])}
        elif path=='/api/action':
            kind=b['kind'];project=b['project_id']
            if kind=='github':
                from office.github_publish import repository
                repo=repository(b['repo']);store.register_action(project,'GitHub 결과 브랜치 생성','https://github.com/'+repo,['office:github',repo],automatic=False)
            elif kind=='naver':
                from office.naver import blog_id
                blog=blog_id(b['blog']);target=b.get('file','publishing/naver.json')
                from office.workspaces import target as safe_target
                safe_target(Path(store.project(project)['path']),target)
                for mode in ('draft','publish'):store.register_action(project,'네이버 '+mode,'https://blog.naver.com/'+blog,['office:naver',blog,target,mode],automatic=False)
            elif kind=='custom':store.register_action(project,b['name'],b['target'],b['argv'],automatic=bool(b.get('automatic',False)))
            else:raise ValueError('지원하지 않는 연결입니다.')
        elif path=='/api/naver-recover':
            from office.naver import blog_id,post_url
            from office.workspaces import target
            blog=blog_id(b['blog']);name=b['file'];project=store.project(b['project_id'])
            if not project:raise ValueError('프로젝트가 없습니다.')
            target(Path(project['path']),name)
            url=b.get('url','').strip()
            if url and not post_url(url,blog):raise ValueError('해당 블로그 게시 URL을 확인하세요.')
            argv=['office:naver',blog,name,'verify',url] if url else ['office:naver',blog,name,'recover-draft']
            store.register_action(project['id'],'네이버 기존 결과 확인·복구','https://blog.naver.com/'+blog,argv,automatic=False)
        elif path=='/api/actions':return {'actions':store.actions(b['project_id'])}
        elif path=='/api/browser-account':
            from office.browser_accounts import BrowserAccounts
            accounts=BrowserAccounts(store)
            account=accounts.register(b['blog'])
            if 'auto_login' in b:accounts.opt_in(account['id'],bool(b['auto_login']))
            return {'account':accounts.get(account['id'])}
        elif path=='/api/browser':
            from office.browser_setup import start_setup
            kind=b['kind']
            if kind not in ('install','login'):raise ValueError('브라우저 설정을 확인하세요.')
            if not hasattr(self,'setup_processes'):self.setup_processes={}
            process=self.setup_processes.get(kind)
            if not process or process.poll() is not None:self.setup_processes[kind]=start_setup(store.root,b['blog'] if kind=='login' else None)
        elif path=='/api/schedule':return {'id':store.add_schedule(b['project_id'],b['role'],b['prompt'],float(b['due']),int(b.get('interval',0)),browser_mode=b.get('browser_mode','standard'))}
        elif path=='/api/schedule-toggle':store.set_schedule(b['id'],bool(b['enabled']))
        elif path=='/api/presence-start':return {'url':self.worker.start_presence()}
        elif path=='/api/presence-stop':self.worker.stop_presence()
        elif path=='/api/presence-key':
            from office.presence import issue_key
            identifier,key=issue_key(store,b['name']);return {'id':identifier,'key':key}
        elif path=='/api/presence-revoke':
            from office.presence import revoke
            revoke(store,b['id'])
        else:raise ValueError('지원하지 않는 요청입니다.')
        return {'ok':True}
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--port',type=int,default=8501);parser.add_argument('--no-open',action='store_true');args=parser.parse_args()
    store=Store(STATE);store.company_project();worker=Worker(store)
    try:
        app=WebOffice(store,worker,args.port)
        token_file=store.root/'web-connection.txt'
        token_file.write_text(app.token,encoding='utf-8')
        try:token_file.chmod(0o600)
        except OSError:pass
        print('My Little Office: '+app.url,flush=True)
        print('Pages connection code: '+str(token_file),flush=True)
        if not args.no_open:webbrowser.open(app.url+'/#bridge='+app.token)
        try:
            while app.thread.is_alive():app.thread.join(timeout=1)
        except KeyboardInterrupt:pass
        finally:app.close()
    finally:worker.close()

if __name__=='__main__':main()
