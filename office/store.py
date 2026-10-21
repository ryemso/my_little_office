import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from scripts.local_office import ROLES
from office.planning import parse_plan

TERMINAL = ('review', 'completed', 'failed', 'interrupted', 'cancelled', 'quota_wait', 'blocked')

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
            columns = {row['name'] for row in con.execute('PRAGMA table_info(tasks)')}
            for name, definition in [('kind', "TEXT NOT NULL DEFAULT 'single'"), ('root_id', 'TEXT'), ('ordinal', 'INTEGER NOT NULL DEFAULT 0'), ('plan_json', "TEXT NOT NULL DEFAULT ''"), ('project_id', 'TEXT'), ('action_json', "TEXT NOT NULL DEFAULT ''"), ('evidence_json', "TEXT NOT NULL DEFAULT '{}'"), ('approval_hash', "TEXT NOT NULL DEFAULT ''")]:
                if name not in columns:
                    con.execute(f'ALTER TABLE tasks ADD COLUMN {name} {definition}')
            con.execute('CREATE INDEX IF NOT EXISTS team_tasks ON tasks(root_id,ordinal)')
            con.execute('CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,name TEXT NOT NULL,path TEXT NOT NULL,network INTEGER NOT NULL DEFAULT 0)')
            con.execute('CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY,project_id TEXT NOT NULL,name TEXT NOT NULL,target TEXT NOT NULL,argv TEXT NOT NULL,automatic INTEGER NOT NULL DEFAULT 0)')


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

    def submit(self, role, prompt, identifier=None, parent=None, delegate=False, project_id=None):
        prompt = prompt.strip()
        if role not in ROLES or not 5 <= len(prompt) <= 5000:
            raise ValueError('담당 직원을 선택하고 업무를 5~5000자로 입력하세요.')
        kind = 'plan' if role == 'lead' and delegate else 'single'
        identifier = identifier or str(uuid.uuid4())
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT * FROM tasks WHERE id=?', (identifier,)).fetchone()
            if old:
                if old['role'] != role or old['prompt'] != prompt or old['kind'] != kind or old['project_id'] != project_id:
                    raise ValueError('같은 업무 ID에 다른 내용을 제출할 수 없습니다.')
                return identifier
            state = self._get(con, 'office', {})
            if not state.get('on_duty'):
                raise ValueError('먼저 출근하세요. 입력한 명령은 아직 접수되지 않았습니다.')
            if parent and not con.execute('SELECT 1 FROM tasks WHERE id=?', (parent,)).fetchone():
                raise ValueError('원래 업무를 찾을 수 없습니다.')
            if project_id and not con.execute('SELECT 1 FROM projects WHERE id=?',(project_id,)).fetchone():
                raise ValueError('등록된 프로젝트를 선택하세요.')
            now = time.time()
            con.execute('INSERT INTO tasks(id,role,prompt,status,created,updated,parent,kind,project_id) VALUES(?,?,?,?,?,?,?,?,?)',
                        (identifier, role, prompt, 'queued', now, now, parent, kind, project_id))
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
            task = con.execute("""SELECT t.* FROM tasks t WHERE t.status='queued'
                AND (t.root_id IS NULL OR EXISTS(SELECT 1 FROM tasks r WHERE r.id=t.root_id AND r.status='delegating'))
                AND NOT EXISTS(SELECT 1 FROM tasks prev WHERE prev.root_id=t.root_id
                    AND prev.ordinal<t.ordinal AND prev.status NOT IN ('review','completed'))
                ORDER BY t.created LIMIT 1""").fetchone()
            if task:
                con.execute("UPDATE tasks SET status='running',updated=? WHERE id=?", (time.time(), task['id']))
                return dict(task)

    def children(self, identifier):
        with self.connect() as con:
            return [dict(t) for t in con.execute('SELECT * FROM tasks WHERE root_id=? ORDER BY ordinal', (identifier,))]

    def _block_team(self, con, root_id, reason):
        con.execute("UPDATE tasks SET status='blocked',error=?,updated=? WHERE id=? AND status='delegating'", (reason, time.time(), root_id))
        con.execute("UPDATE tasks SET status='cancelled',error=?,updated=? WHERE root_id=? AND status IN ('queued','awaiting_approval')", (reason, time.time(), root_id))

    def cancel(self, identifier):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            task = con.execute('SELECT * FROM tasks WHERE id=?', (identifier,)).fetchone()
            if not task:
                return
            if task['status'] == 'delegating':
                con.execute("UPDATE tasks SET status='cancelled',updated=? WHERE id=?", (time.time(), identifier))
                con.execute("UPDATE tasks SET status=CASE WHEN status='running' THEN 'cancel_requested' ELSE 'cancelled' END,updated=? WHERE root_id=? AND status IN ('queued','running','awaiting_approval')", (time.time(), identifier))
            else:
                con.execute("UPDATE tasks SET status=CASE WHEN status IN ('queued','awaiting_approval') THEN 'cancelled' ELSE 'cancel_requested' END, updated=? WHERE id=? AND status IN ('queued','running','awaiting_approval')", (time.time(), identifier))
                if task['root_id'] and task['status'] in ('queued', 'running', 'awaiting_approval'):
                    self._block_team(con, task['root_id'], '직원 업무 중단으로 팀 진행을 멈췄습니다.')

    def finish(self, identifier, result):
        if result.get('status') not in TERMINAL:
            raise ValueError('Invalid result status')
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            old = con.execute('SELECT * FROM tasks WHERE id=?', (identifier,)).fetchone()
            if not old or old['status'] not in ('running', 'cancel_requested'):
                return  # Duplicate delivery must not create duplicate children/reports.
            if old['status'] == 'cancel_requested':
                result = dict(result, status='interrupted', error='사용자 중단 또는 퇴근으로 실행을 멈췄습니다.')
            steps = None
            if old['kind'] == 'plan' and result['status'] == 'review':
                try:
                    steps = parse_plan(result.get('output', ''))
                    registered = {a['id']:a for a in self.actions(old['project_id'])} if old['project_id'] else {}
                    if any(step.get('action') and step['action'] not in registered for step in steps):
                        raise ValueError('연결되지 않은 외부 실행 작업')
                except (ValueError, TypeError):
                    steps = None
                    result = dict(result, status='failed', error='총괄 배정 형식이 올바르지 않아 실행하지 않았습니다. 결과 확인 후 추가 지시하세요.')
            con.execute('UPDATE tasks SET status=?,output=?,error=?,usage=?,evidence_json=?,updated=? WHERE id=?',
                        (result['status'], result.get('output', ''), result.get('error', ''), json.dumps(result.get('usage', {})), json.dumps(result.get('evidence', {}),ensure_ascii=False), time.time(), identifier))
            if steps:
                con.execute("UPDATE tasks SET status='delegating',plan_json=? WHERE id=?", (json.dumps({'tasks': steps}, ensure_ascii=False), identifier))
                for ordinal, step in enumerate(steps, 1):
                    now = time.time()
                    action = registered.get(step.get('action'))
                    status = 'awaiting_approval' if action and not action['automatic'] else 'queued'
                    con.execute('INSERT INTO tasks(id,role,prompt,status,created,updated,kind,root_id,ordinal,project_id,action_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                                (str(uuid.uuid4()), step['role'], step['prompt'], status, now, now, 'employee', identifier, ordinal, old['project_id'], json.dumps(action,ensure_ascii=False) if action else ''))
            if old['root_id']:
                if result['status'] != 'review':
                    self._block_team(con, old['root_id'], '직원 실행이 실패·중단되어 팀 진행을 멈췄습니다. 완료 결과를 확인하고 다시 지시하세요.')
                elif old['kind'] == 'report':
                    con.execute("UPDATE tasks SET status='review',output=?,updated=? WHERE id=? AND status='delegating'", (result.get('output',''), time.time(), old['root_id']))
                else:
                    remaining = con.execute("SELECT 1 FROM tasks WHERE root_id=? AND status NOT IN ('review','completed')", (old['root_id'],)).fetchone()
                    if not remaining:
                        ordinal = con.execute('SELECT MAX(ordinal) FROM tasks WHERE root_id=?', (old['root_id'],)).fetchone()[0] + 1
                        now = time.time()
                        con.execute('INSERT INTO tasks(id,role,prompt,status,created,updated,kind,root_id,ordinal,project_id) VALUES(?,?,?,?,?,?,?,?,?,?)',
                                    (str(uuid.uuid4()), 'lead', '직원들의 제출물을 검토하고 대표에게 최종 결과와 남은 문제를 보고하세요.', 'queued', now, now, 'report', old['root_id'], ordinal, old['project_id']))

    def complete(self, identifier):
        with self.connect() as con:
            con.execute("UPDATE tasks SET status='completed',updated=? WHERE id=? AND status='review'", (time.time(), identifier))

    def recover(self):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            active = con.execute("SELECT root_id FROM tasks WHERE status IN ('running','cancel_requested') AND root_id IS NOT NULL").fetchall()
            con.execute("UPDATE tasks SET status='interrupted',error='PC 실행 중단. 결과 확인 후 후속 지시로 재개하세요.',updated=? WHERE status IN ('running','cancel_requested')", (time.time(),))
            for row in active:
                self._block_team(con, row['root_id'], 'PC 실행 중단으로 팀 업무를 멈췄습니다.')
        self.pause('앱 시작 · 출근 대기')

    def projects(self):
        with self.connect() as con:
            return [dict(row) for row in con.execute('SELECT * FROM projects ORDER BY name')]

    def project(self, identifier):
        with self.connect() as con:
            row=con.execute('SELECT * FROM projects WHERE id=?',(identifier,)).fetchone()
            return dict(row) if row else None

    def register_project(self, name, path, network=False, identifier=None):
        path=Path(path).expanduser().resolve()
        if not name.strip() or not path.is_dir() or path==Path(path.anchor) or path==Path.home() or self.root.resolve().is_relative_to(path):
            raise ValueError('개별 프로젝트 폴더를 선택하세요. 홈·시스템·사무실 상태 폴더 전체는 사용할 수 없습니다.')
        identifier=identifier or str(uuid.uuid4())
        with self.connect() as con:
            con.execute('INSERT INTO projects(id,name,path,network) VALUES(?,?,?,?)',(identifier,name.strip(),str(path),int(network)))
        return identifier

    def company_project(self):
        path=self.root/'company';path.mkdir(exist_ok=True)
        with self.connect() as con:
            con.execute("INSERT OR IGNORE INTO projects VALUES('company',?,?,1)",('회사 작업실',str(path.resolve())))
        return 'company'

    def actions(self, project_id):
        with self.connect() as con:
            return [dict(row) for row in con.execute('SELECT * FROM actions WHERE project_id=? ORDER BY name',(project_id,))]

    def register_action(self, project_id, name, destination, argv, automatic=False):
        if not self.project(project_id) or not name.strip() or not destination.strip() or not isinstance(argv,list) or not argv or not all(isinstance(a,str) and a and '\x00' not in a for a in argv):
            raise ValueError('프로젝트·작업 이름·게시/배포 대상·실행 인자 배열을 확인하세요.')
        identifier=str(uuid.uuid4())
        with self.connect() as con:
            con.execute('INSERT INTO actions VALUES(?,?,?,?,?,?)',(identifier,project_id,name.strip(),destination.strip(),json.dumps(argv,ensure_ascii=False),int(automatic)))
        return identifier

    def approve(self, identifier, fingerprint):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            task=con.execute('SELECT * FROM tasks WHERE id=?',(identifier,)).fetchone()
            if not task or task['status']!='awaiting_approval':raise ValueError('승인 대기 작업이 아닙니다.')
            if con.execute("SELECT 1 FROM tasks WHERE root_id=? AND ordinal<? AND status NOT IN ('review','completed')",(task['root_id'],task['ordinal'])).fetchone():
                raise ValueError('앞 직원의 결과가 나온 뒤 실행할 내용을 확인하고 승인하세요.')
            con.execute("UPDATE tasks SET status='queued',approval_hash=?,updated=? WHERE id=?",(fingerprint,time.time(),identifier))

    def set_project_network(self, identifier, enabled):
        with self.connect() as con:
            con.execute('UPDATE projects SET network=? WHERE id=?',(int(enabled),identifier))

    def has_active_work(self):
        with self.connect() as con:
            return bool(con.execute("SELECT 1 FROM tasks WHERE status IN ('running','cancel_requested') LIMIT 1").fetchone())
