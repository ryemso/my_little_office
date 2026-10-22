"""Opt-in loopback presence bridge. Keys authorize status only, never execution."""
import hashlib
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
import secrets
import threading
import time
import uuid
from office.activity import normalize_state


def initialize(store):
    with store.connect() as con:
        con.execute('''CREATE TABLE IF NOT EXISTS visitors(id TEXT PRIMARY KEY,name TEXT NOT NULL,key_hash TEXT UNIQUE NOT NULL,
            revoked INTEGER NOT NULL DEFAULT 0,state TEXT NOT NULL DEFAULT 'idle',detail TEXT NOT NULL DEFAULT '',seen REAL NOT NULL DEFAULT 0)''')


def issue_key(store,name):
    name=name.strip()
    if not 1<=len(name)<=60:raise ValueError('표시 이름은 1~60자입니다.')
    initialize(store);token=secrets.token_urlsafe(32);identifier=str(uuid.uuid4())
    with store.connect() as con:
        con.execute('INSERT INTO visitors(id,name,key_hash) VALUES(?,?,?)',(identifier,name,hashlib.sha256(token.encode()).hexdigest()))
    return identifier,token


def revoke(store,identifier):
    with store.connect() as con:con.execute('UPDATE visitors SET revoked=1 WHERE id=?',(identifier,))


def visitors(store,now=None):
    initialize(store);now=time.time() if now is None else now
    with store.connect() as con:
        return [dict(id=r['id'],name=r['name'],state=r['state'],detail=r['detail'],seen=r['seen'],
                     online=not r['revoked'] and r['seen']>0 and now-r['seen']<=60,revoked=bool(r['revoked']))
                for r in con.execute('SELECT * FROM visitors ORDER BY name')]


class PresenceServer:
    def __init__(self,store,port=8787):
        initialize(store)
        if not 0<=int(port)<=65535:raise ValueError('포트 번호를 확인하세요.')
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def setup(self):
                super().setup();self.connection.settimeout(5)
            def respond(self,code,value):
                data=json.dumps(value,ensure_ascii=False).encode()
                self.send_response(code);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data)
            def dispatch(self):
                host=self.headers.get('Host','').split(':')[0]
                if host not in ('localhost','127.0.0.1') or self.headers.get('Origin'):
                    self.respond(403,{'error':'local clients only'});return
                if self.command=='GET' and self.path=='/health':self.respond(200,{'ok':True,'scope':'presence-only'});return
                token=self.headers.get('Authorization','')
                if not token.startswith('Bearer ') or len(token)>200:self.respond(401,{'error':'key required'});return
                digest=hashlib.sha256(token[7:].encode()).hexdigest()
                with store.connect() as con:row=con.execute('SELECT id FROM visitors WHERE key_hash=? AND revoked=0',(digest,)).fetchone()
                if not row:self.respond(403,{'error':'key revoked or invalid'});return
                if self.command=='GET' and self.path=='/agents':self.respond(200,{'agents':visitors(store)});return
                if self.command!='POST' or self.path not in ('/join-agent','/agent-push','/leave-agent'):
                    self.respond(404,{'error':'not found'});return
                try:
                    size=int(self.headers.get('Content-Length','0'))
                    if not 0<size<=4096:raise ValueError('body must be 1..4096 bytes')
                    body=json.loads(self.rfile.read(size))
                    if not isinstance(body,dict) or set(body)-{'state','detail'}:raise ValueError('state/detail only')
                    state=normalize_state(body.get('state','idle'));detail=body.get('detail','')
                    if not isinstance(detail,str) or len(detail)>240:raise ValueError('detail max 240 chars')
                    from office.engine import safe_diagnostic
                    with store.connect() as con:
                        updated=con.execute('UPDATE visitors SET state=?,detail=?,seen=? WHERE id=? AND revoked=0',
                            (state,safe_diagnostic(detail.replace(token[7:],'[REDACTED]')),0 if self.path=='/leave-agent' else time.time(),row['id']))
                    if not updated.rowcount:self.respond(403,{'error':'key revoked'});return
                    self.respond(200,{'agentId':row['id'],'scope':'presence-only'})
                except (ValueError,UnicodeError):self.respond(400,{'error':'invalid status payload'})
            do_GET=dispatch
            do_POST=dispatch
        self.server=ThreadingHTTPServer(('127.0.0.1',int(port)),Handler)
        self.server.daemon_threads=True
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True,name='office-presence');self.thread.start()
    @property
    def url(self):return 'http://127.0.0.1:'+str(self.server.server_address[1])
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
