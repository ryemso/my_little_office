"""Version-gated bidirectional local Codex transport. No approval bypass/fallback.

Only protocol events needed for the UI are persisted; raw RPC payloads, OAuth
URLs and form responses remain in this process. CLI inference still uses the
user's own Codex ChatGPT login, never copied tokens.
"""
import json
import queue
import subprocess
import threading
import time
from pathlib import Path
from office.runtime_requests import rpc_reply

TESTED_VERSION='0.163.0'
ACTIVE={}
ACTIVE_LOCK=threading.RLock()


def inspect_cli(command):
    result=subprocess.run(command+['--version'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
    if result.returncode:raise RuntimeError('Codex 버전 조회 실패')
    version=result.stdout.strip().split()[-1]
    return {'version':version,'supported':version==TESTED_VERSION,'tested_version':TESTED_VERSION}


class Transport:
    def __init__(self, command, cwd, env=None):
        from office.engine import stop_process
        self.stop_process=stop_process
        kwargs={'start_new_session':True}
        import os
        if os.name=='nt':kwargs={'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP}
        self.process=subprocess.Popen(command,cwd=cwd,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                      text=True,encoding='utf-8',errors='replace',bufsize=1,**kwargs)
        self.queue=queue.Queue(maxsize=256);self.closed=threading.Event();self.write_lock=threading.Lock()
        self.stderr_seen=False
        self.reader=threading.Thread(target=self._read,daemon=True);self.reader.start()
        self.errors=threading.Thread(target=self._drain_errors,daemon=True);self.errors.start()

    def _read(self):
        total=0
        try:
            while not self.closed.is_set():
                line=self.process.stdout.readline(1_000_001)
                if not line:break
                total+=len(line)
                if len(line)>1_000_000 or total>16_000_000:raise ValueError('실행기 메시지 한도 초과')
                value=json.loads(line)
                if not isinstance(value,dict):raise ValueError('실행기 JSON 객체 오류')
                self.queue.put(value,timeout=2)
        except Exception:
            self.queue.put({'transport_error':True},timeout=2)
        finally:
            try:self.queue.put({'transport_closed':True},timeout=2)
            except queue.Full:pass

    def _drain_errors(self):
        # Drain without storing: third-party logs can include private values.
        while not self.closed.is_set():
            value=self.process.stderr.read(1024)
            if not value:break
            self.stderr_seen=True

    def send(self, value):
        with self.write_lock:
            self.process.stdin.write(json.dumps(value,ensure_ascii=False)+'\n');self.process.stdin.flush()

    def receive(self, timeout=.1):
        try:return self.queue.get(timeout=timeout)
        except queue.Empty:return None

    def close(self):
        self.closed.set()
        self.stop_process(self.process)
        for stream in (self.process.stdin,self.process.stdout,self.process.stderr):
            try:stream.close()
            except (OSError,ValueError):pass


class AppServerRun:
    def __init__(self, store, task, transport, end, timing=None):
        self.timing=timing
        self.store=store;self.task=task;self.transport=transport;self.deadline=end
        self.broker=store.runtime;self.session=self.broker.session(task['id'])
        self.thread=None;self.turn=None;self.serial=0;self.responses={};self.pending={};self.events=[]
        self.final=[];self.failure=None;self.completed=False;self.wait_started=None;self.denied=False
        self.max_wait=900;self.terminal_state='disconnected'

    def rpc(self, method, params, timeout=30):
        self.serial+=1;identifier='client:'+str(self.serial)
        self.transport.send({'id':identifier,'method':method,'params':params})
        until=time.monotonic()+timeout
        while identifier not in self.responses:
            if self.wait_started is not None:until=time.monotonic()+timeout
            if time.monotonic()>=until:raise RuntimeError('실행기 요청 응답 시간 초과: '+method)
            self.tick()
        result=self.responses.pop(identifier)
        if 'error' in result:raise RuntimeError('실행기가 요청을 거절했습니다: '+method)
        return result.get('result',{})

    def _server_request(self, message):
        identifier=message['id'];method=message['method'];params=message.get('params',{})
        if type(identifier) not in (int,str) or not isinstance(params,dict):raise RuntimeError('잘못된 실행기 승인 요청')
        key=json.dumps(identifier)
        if key in self.pending:raise RuntimeError('중복 실행기 승인 ID')
        try:request_id=self.broker.add(self.session,identifier,method,params,self.max_wait)
        except ValueError as error:
            diagnostic=self.broker.reject(self.session,method,params,error)
            # Unknown/secret-input requests never become generic approval prompts.
            self.transport.send({'id':identifier,'error':{'code':-32602,'message':'This client cannot safely handle this request; use the official host UI.'}})
            self.failure='실행기 요청을 처리하지 못했습니다. 요청: '+diagnostic['method']+' · 형식: '+diagnostic['shape']['mode']+' · 사유: '+diagnostic['reason']+' 권한을 우회하지 않았습니다.'
            return
        self.pending[key]={'id':identifier,'request':request_id,'method':method,'params':params,'sent':False,'created':time.time()}
        if self.wait_started is None:
            self.wait_started=time.monotonic()
            if self.timing:self.timing.approval_wait(True)

    def _deliver(self):
        for pending in list(self.pending.values()):
            row=self.broker.choice(pending['request'])
            if not row:raise RuntimeError('승인 요청 기록 없음')
            if row['expires']<=time.time() and not pending['sent']:
                self.terminal_state='expired';raise RuntimeError('사용자 확인 요청이 만료됐습니다. 자동 승인하지 않았습니다.')
            if row['state']=='responding' and not pending['sent']:
                content=self.broker.take_content(pending['request'])
                reply=rpc_reply(pending['method'],pending['params'],row['choice'],content)
                # Set before write: an uncertain delivery is never sent twice.
                pending['sent']=True
                if row['choice']!='accept':self.denied=True
                self.transport.send({'id':pending['id'],'result':reply})
                if row['choice']!='accept':
                    # Do not give the agent a chance to reroute a denied operation.
                    self.failure='실행 중 요청이 거절·취소됐습니다. 우회하지 않고 업무를 중단합니다.'
                    return

    def _resolved(self, identifier):
        pending=self.pending.pop(json.dumps(identifier),None)
        if pending:
            row=self.broker.choice(pending['request'])
            if row and row['state']=='pending':self.failure='실행기가 사용자 응답 전에 승인 요청을 해제했습니다. 완료로 처리하지 않습니다.'
            self.broker.resolve(self.session,identifier)
        if not self.pending and self.wait_started is not None:
            self.deadline+=time.monotonic()-self.wait_started
            self.wait_started=None
            if self.timing:self.timing.approval_wait(False)
            self.store.activity(self.task['id'],'executing','실행기 응답 처리 확인 · 작업 재개')

    def tick(self):
        current=self.store.get(self.task['id'])
        if not current or current['status']=='cancel_requested':raise RuntimeError('사용자가 업무를 중단했습니다.')
        if self.failure:raise RuntimeError(self.failure)
        if self.wait_started is None and time.time()>self.deadline:raise RuntimeError('업무 실행 시간 초과')
        if self.wait_started is not None and time.monotonic()-self.wait_started>self.max_wait:
            self.terminal_state='expired';raise RuntimeError('사용자 확인 시간이 만료됐습니다.')
        self._deliver()
        message=self.transport.receive()
        if not message:return
        if message.get('transport_error') or message.get('transport_closed'):raise RuntimeError('실행기 연결이 끊겼습니다. 이전 승인을 재전송하지 않습니다.')
        if 'id' in message and 'method' in message:
            self._server_request(message);return
        if 'id' in message:
            self.responses[message['id']]=message;return
        method=message.get('method');params=message.get('params',{})
        if method=='turn/started':
            self.turn=params['turn']['id'];self.broker.bind(self.session,self.thread,self.turn)
        elif method=='serverRequest/resolved':
            if params.get('threadId')==self.thread:self._resolved(params['requestId'])
        elif method=='item/started':
            if self.timing:self.timing.observe(method,params.get('item',{}))
            kind=params.get('item',{}).get('type')
            self.store.activity(self.task['id'],'syncing' if kind=='mcpToolCall' else 'executing','연결 도구 호출 중' if kind=='mcpToolCall' else '실행기 작업 시작')
        elif method=='item/completed':
            if self.timing:self.timing.observe(method,params.get('item',{}))
            item=params.get('item',{});kind=item.get('type')
            # Explicit origin/tool denial must not turn into success via a report.
            if kind=='mcpToolCall':
                from office.runtime_requests import browser_access_denied
                if browser_access_denied(item):
                    self.denied=True
            if kind=='agentMessage':
                from office.engine import safe_diagnostic
                text=safe_diagnostic(item.get('text',''))
                if item.get('phase')!='commentary':self.final.append(text)
                self.store.message(self.task['id'],'runtime-message:'+str(item.get('id')),self.task['role'],'progress',text)
            converted=convert_item(item)
            if converted:self.events.append({'type':'item.completed','item':converted})
            for pending in list(self.pending.values()):
                if pending['params'].get('itemId')==item.get('id'):self._resolved(pending['id'])
        elif method=='turn/completed':
            turn=params.get('turn',{})
            if turn.get('id')!=self.turn:raise RuntimeError('다른 턴 완료 이벤트')
            if turn.get('status')!='completed':self.failure='직원 턴이 실패·중단됐습니다.'
            self.completed=True
        elif method=='error':self.failure='실행기가 오류 이벤트를 반환했습니다.'

    def run(self, prompt, cwd, writable, images):
        try:
            self.rpc('initialize',{'clientInfo':{'name':'my_little_office','title':'My Little Office','version':'0.19'},
                                   'capabilities':{'mcpServerOpenaiFormElicitation':True}})
            self.transport.send({'method':'initialized'})
            thread=self.rpc('thread/start',{'cwd':cwd,'sandbox':'workspace-write' if writable else 'read-only',
                                           'approvalPolicy':'on-request','approvalsReviewer':'user'})
            if thread.get('approvalPolicy')!='on-request' or thread.get('approvalsReviewer')!='user':
                raise RuntimeError('실효 승인 정책이 사용자 확인 모드가 아닙니다. 상위 정책을 확인하세요.')
            self.thread=thread['thread']['id'];self.broker.bind(self.session,self.thread)
            inputs=[{'type':'text','text':prompt}]+[{'type':'localImage','path':str(path)} for path in images]
            response=self.rpc('turn/start',{'threadId':self.thread,'input':inputs})
            self.turn=response['turn']['id']
            # Do not erase waiting_input when an early elicitation preceded this response.
            with self.store.connect() as con:con.execute('UPDATE runtime_sessions SET turn_id=? WHERE id=?',(self.turn,self.session))
            while not self.completed:self.tick()
            if self.failure:raise RuntimeError(self.failure)
            if self.pending:raise RuntimeError('미해결 입력 요청이 남아 있습니다.')
            if self.denied:raise RuntimeError('도구 접근 또는 실행 승인이 거절됐습니다. 보고서 작성으로 원래 업무를 완료 처리하지 않습니다.')
            self.terminal_state='completed'
            return {'text':'\n\n'.join(self.final),'events':self.events+[{'type':'turn.completed'}],
                    'session':self.session,'thread':self.thread,'turn':self.turn}
        finally:
            if self.terminal_state!='completed' and self.thread and self.turn:
                try:self.transport.send({'id':'interrupt','method':'turn/interrupt','params':{'threadId':self.thread,'turnId':self.turn}})
                except (OSError,ValueError):pass
            self.broker.end(self.session,self.terminal_state)
            self.transport.close()


def convert_item(item):
    from office.engine import safe_diagnostic
    kind=item.get('type')
    if kind=='commandExecution':
        return {'id':item.get('id'),'type':'command_execution','command':safe_diagnostic(item.get('command','')),
                'status':item.get('status'),'exit_code':item.get('exitCode'),
                'aggregated_output':safe_diagnostic(item.get('aggregatedOutput') or '')[-4000:]}
    if kind=='mcpToolCall':return {'id':item.get('id'),'type':'mcp_tool_call','server':item.get('server'),'tool':item.get('tool'),'status':item.get('status')}
    if kind=='webSearch':return {'id':item.get('id'),'type':'web_search','action':{'observed':True}}


def execute(store, task, command, cwd, env, prompt, writable, images, end, windows_args=None, browser_args=None, timing=None):
    info=inspect_cli(command)
    if not info['supported']:raise RuntimeError('대화형 실행기 검증 버전은 '+TESTED_VERSION+'입니다. 연결 진단에서 버전을 확인하세요.')
    args=command+['app-server','--listen','stdio://','-c','forced_login_method="chatgpt"','-c','model_provider="openai"','-c','web_search="live"']+(windows_args or [])+(browser_args or [])
    if writable:
        project=store.project(task['project_id'])
        args+=['-c','sandbox_workspace_write.network_access='+str(bool(project.get('network'))).lower()]
    if task.get('kind')=='plan':args+=['-c','features.shell_tool=false']
    transport=Transport(args,cwd,env)
    runner=AppServerRun(store,task,transport,end,timing=timing)
    with ACTIVE_LOCK:ACTIVE[runner.session]=runner
    try:return runner.run(prompt,cwd,writable,images)
    finally:
        with ACTIVE_LOCK:ACTIVE.pop(runner.session,None)


def external_url(store, identifier):
    """Expose a live URL only to the authenticated UI, never the DB/chat/log."""
    with ACTIVE_LOCK:
        for runner in ACTIVE.values():
            if runner.store is not store:continue
            for pending in list(runner.pending.values()):
                if pending['request']==identifier and pending['params'].get('mode')=='url':
                    row=store.runtime.choice(identifier)
                    if row and row['state']=='pending' and row['expires']>time.time():
                        from office.runtime_requests import origin
                        origin(pending['params']['url'])
                        return pending['params']['url']
    raise ValueError('살아 있는 외부 인증 요청이 아닙니다.')
