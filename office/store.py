import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from scripts.local_office import ROLES

TERMINAL = ('review', 'completed', 'failed', 'interrupted', 'cancelled', 'quota_wait')

class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.db = self.root / 'office.sqlite3'
        with self.connect() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, role TEXT NOT NULL, prompt TEXT NOT NULL,
                    status TEXT NOT NULL, output TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
                    created REAL NOT NULL, updated REAL NOT NULL, parent TEXT,
                    usage TEXT NOT NULL DEFAULT '{}');
            ''')

    @contextmanager
    def connect(self):
        con = sqlite3.connect(self.db, timeout=10)
        con.row_factory = sqlite3.Row
        try:
            with con:
                yield con
        finally:
            con.close()

    def _get(self, con, key, default):
        row = con.execute('SELECT value FROM meta WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else default

    def _put(self, con, key, value):
        con.execute('INSERT OR REPLACE INTO meta VALUES (?,?)', (key, json.dumps(value)))

    def status(self):
        with self.connect() as con:
            return self._get(con, 'office', {'on_duty': False, 'message': '출근 전'}), self._get(con, 'attendance', {})

    def clock_in(self, now=None):
        now = time.time() if now is None else now
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            self._put(con, 'office', {'on_duty': True, 'started': now, 'message': '근무 중'})

    def pause(self, message='퇴근'):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            state = self._get(con, 'office', {})
            state.update(on_duty=False, message=message)
            self._put(con, 'office', state)
            con.execute("UPDATE tasks SET status='cancel_requested', updated=? WHERE status='running'", (time.time(),))

    def submit(self, role, prompt, identifier=None, parent=None):
        prompt = prompt.strip()
        if role not in ROLES or not 5 <= len(prompt) <= 5000:
            raise ValueError('담당 직원을 선택하고 업무를 5~5000자로 입력하세요.')
        identifier = identifier or str(uuid.uuid4())
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT * FROM tasks WHERE id=?', (identifier,)).fetchone()
            if old:
                if old['role'] != role or old['prompt'] != prompt:
                    raise ValueError('같은 업무 ID에 다른 내용을 제출할 수 없습니다.')
                return identifier
            state = self._get(con, 'office', {})
            if not state.get('on_duty'):
                raise ValueError('먼저 출근하세요. 입력한 명령은 아직 접수되지 않았습니다.')
            if parent and not con.execute('SELECT 1 FROM tasks WHERE id=?', (parent,)).fetchone():
                raise ValueError('원래 업무를 찾을 수 없습니다.')
            now = time.time()
            con.execute('INSERT INTO tasks(id,role,prompt,status,created,updated,parent) VALUES(?,?,?,?,?,?,?)',
                        (identifier, role, prompt, 'queued', now, now, parent))
        return identifier

    def tasks(self):
        with self.connect() as con:
            return [dict(t) for t in con.execute('SELECT * FROM tasks ORDER BY created DESC LIMIT 100')]

    def get(self, identifier):
        with self.connect() as con:
            row = con.execute('SELECT * FROM tasks WHERE id=?', (identifier,)).fetchone()
            return dict(row) if row else None

    def claim(self):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            state = self._get(con, 'office', {})
            if not state.get('on_duty'):
                return None
            if con.execute("SELECT 1 FROM tasks WHERE status IN ('running','cancel_requested')").fetchone():
                return None
            task = con.execute("SELECT * FROM tasks WHERE status='queued' ORDER BY created LIMIT 1").fetchone()
            if task:
                con.execute("UPDATE tasks SET status='running',updated=? WHERE id=?", (time.time(), task['id']))
                return dict(task)

    def cancel(self, identifier):
        with self.connect() as con:
            con.execute("UPDATE tasks SET status=CASE WHEN status='queued' THEN 'cancelled' ELSE 'cancel_requested' END, updated=? WHERE id=? AND status IN ('queued','running')", (time.time(), identifier))

    def finish(self, identifier, result):
        if result.get('status') not in TERMINAL:
            raise ValueError('Invalid result status')
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT status FROM tasks WHERE id=?', (identifier,)).fetchone()
            if old and old[0] == 'cancel_requested':
                result = dict(result, status='interrupted', error='사용자 중단 또는 퇴근으로 실행을 멈췄습니다.')
            con.execute('UPDATE tasks SET status=?,output=?,error=?,usage=?,updated=? WHERE id=?',
                        (result['status'], result.get('output', ''), result.get('error', ''), json.dumps(result.get('usage', {})), time.time(), identifier))

    def complete(self, identifier):
        with self.connect() as con:
            con.execute("UPDATE tasks SET status='completed',updated=? WHERE id=? AND status='review'", (time.time(), identifier))

    def recover(self):
        with self.connect() as con:
            con.execute("UPDATE tasks SET status='interrupted',error='PC 실행 중단. 결과 확인 후 후속 지시로 재개하세요.',updated=? WHERE status IN ('running','cancel_requested')", (time.time(),))
        self.pause('앱 시작 · 출근 대기')
