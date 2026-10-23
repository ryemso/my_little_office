"""Durable approval metadata; raw RPC params and replies live only in the worker.

Tasks retain the running lease while a session waits, so the existing single
worker/dependency/schedule rules continue to block downstream execution.
"""
import hashlib
import json
import time
import uuid
import threading
from urllib.parse import urlsplit

OPEN = ('pending', 'responding')
APPROVALS = {'item/commandExecution/requestApproval', 'item/fileChange/requestApproval'}
SUPPORTED = APPROVALS | {'mcpServer/elicitation/request', 'item/tool/requestUserInput', 'item/permissions/requestApproval'}


def clean(value):
    from office.engine import safe_diagnostic
    return safe_diagnostic(str(value))[:4000]


def origin(url):
    parsed = urlsplit(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('지원하지 않는 인증 URL입니다.')
    if parsed.scheme == 'http' and parsed.hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('인증 URL은 HTTPS여야 합니다.')
    return parsed.scheme + '://' + parsed.netloc


def public_request(method, params):
    """Only deterministic supported forms; no arbitrary password/free-text fields."""
    import re
    forbidden = re.compile(r'password|passwd|token|cookie|secret|otp|credential|비밀번호|인증번호', re.I)
    def safe_text(value):
        value=str(value)
        redacted=clean(value)
        if redacted!=value or forbidden.search(value) or ('://' in value and '?' in value):
            raise ValueError('비밀 입력 가능성이 있는 요청은 공식 화면에서 직접 처리하세요.')
        return value
    result={'kind':'approval','message':'실행 중 사용자 확인이 필요합니다.','choices':['accept','decline','cancel']}
    if method not in SUPPORTED:raise ValueError('지원하지 않는 실행기 요청입니다.')
    if method in APPROVALS:
        result['message']=safe_text(params.get('reason') or '요청한 작업 범위를 확인하세요.')
        result['scope']={key:params[key] for key in ('command','cwd','networkApprovalContext','grantRoot') if key in params}
        safe_text(json.dumps(result['scope'],ensure_ascii=False))
    elif method=='item/permissions/requestApproval':
        # Network/filesystem permission profiles are not rendered as a generic yes/no.
        raise ValueError('세부 권한 요청은 아직 지원하지 않습니다. 실행 정책을 별도로 확인하세요.')
    elif method=='mcpServer/elicitation/request':
        result['message']=safe_text(params.get('message','확인 요청'))
        result['server']=safe_text(params.get('serverName',''))
        if params.get('mode')=='url':
            result.update(kind='external',origin=origin(params['url']))
            result['message']='표시된 사이트의 공식 인증 화면에서 절차를 마친 뒤 확인하세요. '+result['message']
        elif params.get('mode') in ('form','openai/form','openaiForm'):
            schema=params.get('requestedSchema',{})
            if schema.get('type')!='object' or len(schema.get('properties',{}))>12:
                raise ValueError('지원하지 않는 확인 양식입니다.')
            fields=[]
            for key,spec in schema.get('properties',{}).items():
                safe_text(key)
                if spec.get('type')=='boolean':options=[True,False]
                elif spec.get('type')=='string' and isinstance(spec.get('enum'),list) and 0<len(spec['enum'])<=20:
                    options=[safe_text(option) for option in spec['enum']]
                else:raise ValueError('자유 입력·비밀 입력 양식은 공식 화면에서 직접 처리하세요.')
                fields.append({'id':key,'label':safe_text(spec.get('title') or key),'options':options})
            if not set(schema.get('required') or []).issubset({f['id'] for f in fields}):raise ValueError('확인 양식의 필수 필드 오류')
            result.update(kind='form',fields=fields)
        else:raise ValueError('지원하지 않는 MCP 확인 형식입니다.')
    else:
        fields=[]
        for question in params.get('questions',[]):
            if question.get('isSecret') or not question.get('options'):raise ValueError('자유 입력·비밀 질문은 공식 화면에서 처리하세요.')
            options=[safe_text(option['label']) for option in question['options']]
            fields.append({'id':safe_text(question['id']),'label':safe_text(question['question']),'options':options})
        if not 1<=len(fields)<=12:raise ValueError('질문 개수를 확인하세요.')
        result.update(kind='question',fields=fields)
    return result


def rpc_reply(method, params, choice, content):
    if choice not in ('accept','decline','cancel'):raise ValueError('지원하지 않는 응답')
    if method in APPROVALS:return {'decision':choice}
    if method=='mcpServer/elicitation/request':return {'action':choice,'content':content if choice=='accept' and params.get('mode')!='url' else None}
    if method=='item/tool/requestUserInput':return {'answers':{key:{'answers':[value]} for key,value in (content or {}).items()}} if choice=='accept' else {'answers':{}}
    if method=='item/permissions/requestApproval':return {'permissions':{}}
    raise ValueError('지원하지 않는 응답 형식')


class RequestBroker:
    def __init__(self, store):
        self.store=store
        self._content={}
        self._lock=threading.RLock()
        with store.connect() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS runtime_sessions (
                    id TEXT PRIMARY KEY,task_id TEXT NOT NULL,epoch TEXT NOT NULL,
                    state TEXT NOT NULL,thread_id TEXT,turn_id TEXT,updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS runtime_requests (
                    id TEXT PRIMARY KEY,session_id TEXT NOT NULL,rpc_id TEXT NOT NULL,
                    method TEXT NOT NULL,view_json TEXT NOT NULL,digest TEXT NOT NULL,
                    state TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1,choice TEXT,
                    created REAL NOT NULL,expires REAL NOT NULL,resolved REAL,
                    UNIQUE(session_id,rpc_id));
            ''')

    def session(self, task_id):
        identifier=str(uuid.uuid4())
        with self.store.connect() as con:
            con.execute('INSERT INTO runtime_sessions VALUES(?,?,?,?,?,?,?)',
                        (identifier,task_id,str(uuid.uuid4()),'starting',None,None,time.time()))
        return identifier

    def bind(self, session, thread, turn=None):
        with self.store.connect() as con:
            con.execute("UPDATE runtime_sessions SET thread_id=?,turn_id=?,state='running',updated=? WHERE id=?",
                        (thread,turn,time.time(),session))

    def add(self, session, rpc_id, method, params, ttl=900):
        view=public_request(method,params)
        digest=hashlib.sha256(json.dumps([method,params],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        identifier=str(uuid.uuid4());now=time.time()
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row=con.execute('SELECT * FROM runtime_sessions WHERE id=?',(session,)).fetchone()
            if not row or row['state'] not in ('running','waiting_input'):raise ValueError('살아 있는 실행기 요청이 아닙니다.')
            if params.get('threadId')!=row['thread_id'] or (params.get('turnId') and row['turn_id'] and params['turnId']!=row['turn_id']):
                raise ValueError('다른 업무의 승인 요청입니다.')
            con.execute('INSERT INTO runtime_requests(id,session_id,rpc_id,method,view_json,digest,state,created,expires) VALUES(?,?,?,?,?,?,?,?,?)',
                        (identifier,session,json.dumps(rpc_id),method,json.dumps(view,ensure_ascii=False),digest,'pending',now,now+ttl))
            con.execute("UPDATE runtime_sessions SET state='waiting_input',updated=? WHERE id=?",(now,session))
            task=con.execute('SELECT * FROM tasks WHERE id=?',(row['task_id'],)).fetchone()
            if task:
                con.execute('UPDATE schedules SET enabled=0,error=? WHERE last_task=?',('사용자 확인이 필요해 예약을 정지했습니다.',task['root_id'] or task['id']))
                self.store._message(con,task['id'],'runtime-request:'+identifier,'system','status','실행 중 사용자 확인 요청 · 대표 승인함에서 처리하세요.')
        self.store.activity(row['task_id'],'talking','대표 입력 대기 · 실행 중 요청')
        return identifier

    def list(self, active=True):
        query="WHERE r.state IN ('pending','responding')" if active else ''
        with self.store.connect() as con:
            rows=con.execute('SELECT r.*,s.task_id,s.state AS session_state,t.role FROM runtime_requests r JOIN runtime_sessions s ON s.id=r.session_id LEFT JOIN tasks t ON t.id=s.task_id '+query+' ORDER BY r.created DESC LIMIT 200').fetchall()
        return [dict(id=r['id'],task_id=r['task_id'],role=r['role'],method=r['method'],state=r['state'],session_state=r['session_state'],version=r['version'],digest=r['digest'],expires=r['expires'],view=json.loads(r['view_json']),choice=r['choice']) for r in rows]

    def decide(self, identifier, version, digest, choice, content=None):
        with self._lock:
            self._decide(identifier,version,digest,choice,content)
            self._content[identifier]=content

    def take_content(self, identifier):
        with self._lock:
            return self._content.pop(identifier,None)

    def _decide(self, identifier, version, digest, choice, content=None):
        if choice not in ('accept','decline','cancel'):raise ValueError('선택을 확인하세요.')
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row=con.execute('SELECT r.*,s.state AS session_state,t.status AS task_state FROM runtime_requests r JOIN runtime_sessions s ON s.id=r.session_id JOIN tasks t ON t.id=s.task_id WHERE r.id=?',(identifier,)).fetchone()
            if not row or row['state']!='pending' or row['version']!=version or row['digest']!=digest or row['expires']<=time.time() or row['session_state']!='waiting_input' or row['task_state']!='running':
                raise ValueError('승인 요청이 변경·만료됐습니다. 다시 확인하세요.')
            view=json.loads(row['view_json']);fields=view.get('fields',[])
            if choice=='accept' and fields:
                if not isinstance(content,dict) or set(content)!={f['id'] for f in fields}:raise ValueError('모든 질문에 답하세요.')
                for field in fields:
                    if not any(type(content[field['id']]) is type(option) and content[field['id']]==option for option in field['options']):raise ValueError('허용된 선택지가 아닙니다.')
            elif content not in (None,{}):raise ValueError('추가 입력을 받지 않는 요청입니다.')
            con.execute("UPDATE runtime_requests SET state='responding',choice=?,version=version+1 WHERE id=?",(choice,identifier))
        # The caller keeps content in memory; never persist form responses.

    def choice(self, identifier):
        with self.store.connect() as con:
            row=con.execute('SELECT state,choice,expires FROM runtime_requests WHERE id=?',(identifier,)).fetchone()
        return dict(row) if row else None

    def resolve(self, session, rpc_id):
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            con.execute("UPDATE runtime_requests SET state=CASE WHEN choice='accept' THEN 'accepted' WHEN choice='decline' THEN 'declined' WHEN choice='cancel' THEN 'cancelled' ELSE 'superseded' END,version=version+1,resolved=? WHERE session_id=? AND rpc_id=? AND state IN ('pending','responding')",
                        (time.time(),session,json.dumps(rpc_id)))
            if not con.execute("SELECT 1 FROM runtime_requests WHERE session_id=? AND state IN ('pending','responding')",(session,)).fetchone():
                con.execute("UPDATE runtime_sessions SET state='running',updated=? WHERE id=? AND state='waiting_input'",(time.time(),session))

    def end(self, session, state='disconnected'):
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            con.execute("UPDATE runtime_requests SET state=?,version=version+1,resolved=? WHERE session_id=? AND state IN ('pending','responding')",(state,time.time(),session))
            con.execute('UPDATE runtime_sessions SET state=?,updated=? WHERE id=?',(state,time.time(),session))

    def recover(self):
        with self._lock:self._content.clear()
        with self.store.connect() as con:
            con.execute("UPDATE runtime_requests SET state='disconnected',version=version+1 WHERE state IN ('pending','responding')")
            con.execute("UPDATE runtime_sessions SET state='disconnected' WHERE state IN ('starting','running','waiting_input')")


def browser_access_denied(item):
    """Classify a failed tool result, not quoted denial text in a read document."""
    import re
    result=item.get('result')
    is_error=(item.get('status') in ('failed','error','declined') or bool(item.get('error')) or
              isinstance(result,dict) and result.get('isError') is True)
    if not is_error:return False
    payload={key:item.get(key) for key in ('error','result','output','content')}
    return bool(re.search(r'origin approval gate|user declined permission for this action',json.dumps(payload,ensure_ascii=False),re.I))
