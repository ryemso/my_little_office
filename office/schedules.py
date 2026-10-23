"""Durable schedules; enqueue only while the owner's PC office is on duty."""
import math
import time
import uuid
from datetime import datetime, timezone


class Schedules:
    def initialize_schedules(self):
        with self.connect() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS schedules(
                id TEXT PRIMARY KEY,project_id TEXT NOT NULL,role TEXT NOT NULL,prompt TEXT NOT NULL,
                next_due REAL NOT NULL,interval_seconds INTEGER NOT NULL,enabled INTEGER NOT NULL DEFAULT 1,
                last_task TEXT,error TEXT NOT NULL DEFAULT '')''')
            if 'browser_mode' not in {row[1] for row in con.execute('PRAGMA table_info(schedules)')}:
                con.execute("ALTER TABLE schedules ADD COLUMN browser_mode TEXT NOT NULL DEFAULT 'standard'")

    def schedules(self):
        with self.connect() as con:return [dict(row) for row in con.execute('SELECT * FROM schedules ORDER BY next_due')]

    def add_schedule(self,project_id,role,prompt,due,interval_seconds=0,browser_mode='standard'):
        if browser_mode not in ('standard','ego'):raise ValueError('지원하지 않는 브라우저 모드입니다.')
        from scripts.local_office import ROLES
        if not self.project(project_id) or role not in ROLES or not 5<=len(prompt.strip())<=4500:
            raise ValueError('프로젝트·담당자·예약 지시를 확인하세요.')
        if not math.isfinite(due) or due<0 or interval_seconds!=int(interval_seconds) or interval_seconds<0 or 0<interval_seconds<300:
            raise ValueError('예약 시각과 반복 간격을 확인하세요 (반복 최소 5분).')
        identifier=str(uuid.uuid4())
        with self.connect() as con:
            con.execute('INSERT INTO schedules(id,project_id,role,prompt,next_due,interval_seconds,browser_mode) VALUES(?,?,?,?,?,?,?)',
                        (identifier,project_id,role,prompt.strip(),due,interval_seconds,browser_mode))
        return identifier

    def set_schedule(self,identifier,enabled):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            schedule=con.execute('SELECT * FROM schedules WHERE id=?',(identifier,)).fetchone()
            if not schedule:raise ValueError('예약을 찾을 수 없습니다.')
            previous=con.execute('SELECT status FROM tasks WHERE id=?',(schedule['last_task'],)).fetchone() if schedule['last_task'] else None
            if enabled and previous and previous['status'] not in ('queued','running','cancel_requested','delegating','awaiting_approval'):
                # Explicit resume starts a new occurrence; it never reuses a completed one-shot ID.
                con.execute("UPDATE schedules SET enabled=1,error='',last_task=NULL,next_due=? WHERE id=?",(max(time.time(),schedule['next_due']),identifier))
            else:
                con.execute("UPDATE schedules SET enabled=?,error='' WHERE id=?",(int(enabled),identifier))

    def tick_schedules(self,now=None):
        now=time.time() if now is None else now
        if not self.status()[0].get('on_duty'):return []
        queued=[]
        for schedule in self.schedules():
            if not schedule['enabled'] or schedule['next_due']>now:continue
            previous=self.get(schedule['last_task']) if schedule['last_task'] else None
            if previous and previous['status'] in ('queued','running','cancel_requested','delegating','awaiting_approval'):continue
            if previous and previous['status'] not in ('review','completed'):
                with self.connect() as con:con.execute('UPDATE schedules SET enabled=0,error=? WHERE id=?',('이전 실행 실패. 결과 확인 후 예약을 재개하세요.',schedule['id']))
                continue
            slot=schedule['next_due']
            identifier=str(uuid.uuid5(uuid.NAMESPACE_URL,'office-schedule:'+schedule['id']+':'+repr(slot)))
            stamp=datetime.fromtimestamp(slot,timezone.utc).isoformat()
            prompt=schedule['prompt']+'\n예약 회차 시각(UTC): '+stamp+'\n새 게시물은 이 회차를 반영한 고유 post_id를 사용하세요. 기존 글 재발행은 하지 마세요.'
            self.submit(schedule['role'],prompt,identifier=identifier,delegate=schedule['role']=='lead',project_id=schedule['project_id'],browser_mode=schedule['browser_mode'])
            interval=schedule['interval_seconds']
            following=slot+(int((now-slot)//interval)+1)*interval if interval else slot
            with self.connect() as con:
                con.execute('UPDATE schedules SET next_due=?,enabled=?,last_task=?,error=\'\' WHERE id=? AND next_due=?',
                            (following,int(bool(interval)),identifier,schedule['id'],slot))
            queued.append(identifier)
        return queued

    def retry_task(self,identifier):
        """Keep completed predecessors and the shared workspace; reapprove external effects."""
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            task=con.execute('SELECT * FROM tasks WHERE id=?',(identifier,)).fetchone()
            if not task:raise ValueError('업무가 없습니다.')
            if task['status']=='blocked' and task['kind']=='plan':
                task=con.execute("SELECT * FROM tasks WHERE root_id=? AND status IN ('failed','blocked','interrupted','quota_wait') ORDER BY ordinal LIMIT 1",(identifier,)).fetchone()
            if not task or task['status'] not in ('failed','blocked','interrupted','quota_wait'):raise ValueError('다시 실행할 실패 단계가 없습니다.')
            root=task['root_id']
            if root and con.execute("SELECT 1 FROM tasks WHERE root_id=? AND status IN ('running','cancel_requested')",(root,)).fetchone():
                raise ValueError('실행 중인 팀 업무가 끝난 뒤 재개하세요.')
            rows=[task]
            if root:
                con.execute("UPDATE tasks SET status='delegating',error='',updated=? WHERE id=? AND status='blocked'",(time.time(),root))
                rows+=con.execute("SELECT * FROM tasks WHERE root_id=? AND ordinal>? AND status='cancelled' ORDER BY ordinal",(root,task['ordinal'])).fetchall()
            import json
            for row in rows:
                action=json.loads(row['action_json']) if row['action_json'] else None
                state='awaiting_approval' if action and not action['automatic'] else 'queued'
                con.execute("UPDATE tasks SET status=?,error='',approval_hash='',updated=? WHERE id=?",(state,time.time(),row['id']))
                self._message(con,row['id'],'retry:'+str(time.time_ns()),'owner','status','실패 단계부터 재개합니다. 외부 실행은 필요한 승인을 다시 받습니다.')
            return task['id']
