"""Durable work-channel messages; no generated or inferred reasoning."""
import hashlib
import json
import time


class Conversations:
    def initialize_conversations(self):
        with self.connect() as con:
            con.executescript('''CREATE TABLE IF NOT EXISTS messages(
                id INTEGER PRIMARY KEY AUTOINCREMENT,thread_id TEXT NOT NULL,task_id TEXT NOT NULL,
                event_key TEXT NOT NULL,actor TEXT NOT NULL,kind TEXT NOT NULL,body TEXT NOT NULL,
                created REAL NOT NULL,historical INTEGER NOT NULL DEFAULT 0,UNIQUE(task_id,event_key));
                CREATE INDEX IF NOT EXISTS message_thread ON messages(thread_id,id);''')
            con.execute('BEGIN IMMEDIATE')
            if not self._get(con,'chat_backfill_v1',False):
                events=[]
                for task in con.execute('SELECT * FROM tasks ORDER BY created,id').fetchall():
                    actor='lead' if task['root_id'] else 'owner'
                    events.append((task['created'],task['id'],'submitted',actor,'assignment' if task['root_id'] else 'instruction',task['prompt']))
                    if (task['kind']!='plan' or not task['plan_json']) and task['output']:
                        events.append((task['updated'],task['id'],'result',task['role'],'result',task['output']))
                    if task['error']:events.append((task['updated'],task['id'],'error','system','error',task['error']))
                for created,task_id,key,actor,kind,body in sorted(events,key=lambda event:event[0]):
                    self._message(con,task_id,key,actor,kind,body,created,True)
                self._put(con,'chat_backfill_v1',True)

    def _thread(self,con,identifier):
        seen=set()
        while identifier not in seen:
            seen.add(identifier)
            task=con.execute('SELECT id,root_id,parent FROM tasks WHERE id=?',(identifier,)).fetchone()
            if not task:raise ValueError('대화의 원래 업무를 찾을 수 없습니다.')
            ancestor=task['root_id'] or task['parent']
            if not ancestor:return identifier
            identifier=ancestor
        raise ValueError('업무 대화 연결이 순환합니다.')

    def thread_id(self,identifier):
        with self.connect() as con:return self._thread(con,identifier)

    def _message(self,con,task_id,key,actor,kind,body,created=None,historical=False):
        if not body:return
        con.execute('INSERT OR IGNORE INTO messages(thread_id,task_id,event_key,actor,kind,body,created,historical) VALUES(?,?,?,?,?,?,?,?)',
                    (self._thread(con,task_id),task_id,key,actor,kind,body,time.time() if created is None else created,int(historical)))

    def message(self,task_id,key,actor,kind,body):
        with self.connect() as con:self._message(con,task_id,key,actor,kind,body)

    def channels(self):
        with self.connect() as con:
            return [dict(row) for row in con.execute('''SELECT t.*,MAX(m.id) AS last_message FROM tasks t
                LEFT JOIN messages m ON m.thread_id=t.id WHERE t.root_id IS NULL AND t.parent IS NULL
                GROUP BY t.id ORDER BY last_message DESC,t.created DESC''')]

    def messages(self,thread_id,limit=200,before=None):
        with self.connect() as con:
            return [dict(row) for row in con.execute('''SELECT * FROM (SELECT * FROM messages WHERE thread_id=?
                AND (? IS NULL OR id<?) ORDER BY id DESC LIMIT ?) ORDER BY id''',(thread_id,before,before,limit))]

    def transcript(self,thread_id):
        with self.connect() as con:
            return [dict(row) for row in con.execute('SELECT * FROM messages WHERE thread_id=? ORDER BY id',(thread_id,))]


class LiveEvents:
    """Tail complete JSONL records without reading the whole growing log repeatedly."""
    def __init__(self,store,task,path):
        self.store=store;self.task=task;self.path=path;self.offset=0;self.pending=b''

    def poll(self,final=False):
        from office.engine import safe_diagnostic
        with self.path.open('rb') as stream:
            stream.seek(self.offset);data=stream.read();self.offset=stream.tell()
        lines=(self.pending+data).split(b'\n');self.pending=lines.pop()
        if final and self.pending:lines.append(self.pending);self.pending=b''
        for line in lines:
            try:event=json.loads(line)
            except (ValueError,UnicodeError):continue
            if not isinstance(event,dict):continue
            item=event.get('item')
            if not isinstance(item,dict):continue
            event_type=event.get('type');kind=item.get('type')
            if kind=='command_execution' and event_type in ('item.started','item.completed'):
                body='명령 실행 시작' if event_type=='item.started' else '명령 실행 종료 · 종료 코드 '+str(item.get('exit_code','미확인'))
                body+='\n'+str(item.get('command',''))[:3000]
            elif kind=='agent_message' and event_type=='item.completed' and self.task.get('kind')!='plan':
                body=str(item.get('text',''))
            elif kind=='web_search' and event_type in ('item.started','item.completed'):
                body=('웹 조사 시작' if event_type=='item.started' else '웹 조사 결과 수신')+'\n'+json.dumps(item.get('action',{}),ensure_ascii=False)[:2000]
            elif kind=='mcp_tool_call' and event_type in ('item.started','item.completed'):
                body=('연결 도구 호출 시작' if event_type=='item.started' else '연결 도구 호출 종료')+' · '+str(item.get('server',''))+' / '+str(item.get('tool',''))+' · '+str(item.get('status',''))
            else:continue
            key='live:'+str(event_type)+':'+str(item.get('id') or hashlib.sha256(line).hexdigest())
            self.store.message(self.task['id'],key,self.task['role'],'progress',safe_diagnostic(body))
