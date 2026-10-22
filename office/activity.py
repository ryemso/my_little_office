"""Observed activity and presence, independent of task completion claims."""
import time
from scripts.local_office import ROLES

STATES={'idle':'대기','talking':'회의·계획','writing':'작성','researching':'조사','executing':'명령 실행','syncing':'외부 연동','error':'오류'}
ALIASES={'working':'writing','write':'writing','search':'researching','research':'researching','run':'executing','execute':'executing','chat':'talking','meeting':'talking','sync':'syncing','failed':'error','rest':'idle'}


def normalize_state(value):
    value=str(value).strip().lower();value=ALIASES.get(value,value)
    if value not in STATES:raise ValueError('지원하지 않는 활동 상태입니다.')
    return value


class Activity:
    def initialize_activity(self):
        with self.connect() as con:
            con.execute('''CREATE TABLE IF NOT EXISTS activity(task_id TEXT PRIMARY KEY,state TEXT NOT NULL,
                detail TEXT NOT NULL,heartbeat REAL NOT NULL,observed REAL NOT NULL)''')

    def activity(self,task_id,state,detail='',now=None):
        state=normalize_state(state);now=time.time() if now is None else now
        with self.connect() as con:
            task=con.execute('SELECT status FROM tasks WHERE id=?',(task_id,)).fetchone()
            if not task or task['status'] not in ('running','queued'):return
            con.execute('''INSERT INTO activity VALUES(?,?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET
                state=excluded.state,detail=excluded.detail,heartbeat=excluded.heartbeat,observed=excluded.observed''',
                (task_id,state,str(detail)[:240],now,now))

    def heartbeat(self,task_id,now=None):
        with self.connect() as con:
            con.execute('UPDATE activity SET heartbeat=? WHERE task_id=?',(time.time() if now is None else now,task_id))

    def activity_board(self,now=None):
        now=time.time() if now is None else now
        with self.connect() as con:
            rows=con.execute('''SELECT t.id,t.role,t.status,t.updated,a.state AS observed_state,a.detail AS observed_detail,
                a.heartbeat,a.observed FROM tasks t LEFT JOIN activity a ON a.task_id=t.id
                ORDER BY CASE WHEN t.status IN ('running','cancel_requested') THEN 0
                WHEN t.status='awaiting_approval' THEN 1 WHEN t.status='queued' THEN 2 ELSE 3 END,t.updated DESC''').fetchall()
        board=[]
        for role,label in ROLES.items():
            task=next((row for row in rows if row['role']==role),None)
            state='idle';detail='배정된 업무 없음';stale=False
            if task:
                status=task['status']
                if status in ('running','cancel_requested'):
                    stale=task['heartbeat'] is None or now-task['heartbeat']>45
                    state=task['observed_state'] or 'executing'
                    detail='실행기 응답 지연 · 완료 여부 미확인' if stale else task['observed_detail'] or '활동 이벤트 대기'
                elif status in ('failed','blocked','interrupted','quota_wait'):
                    state='error';detail='오류·중단 결과 확인 필요'
                elif status=='awaiting_approval':state='talking';detail='대표 실행 승인 대기'
                elif status=='queued':detail='업무 실행 순서 대기'
                elif status=='delegating':state='talking';detail='직원 배정·결과 취합 중'
                elif status=='review':detail='제출됨 · 대표 검토 대기'
                else:detail='완료 또는 중단된 업무'
            board.append({'role':role,'name':label,'state':state,'label':STATES[state],'detail':detail,
                          'stale':stale,'status':task['status'] if task else 'idle','task_id':task['id'] if task else None,
                          'heartbeat':task['heartbeat'] if task else None,'observed':task['observed'] if task else None})
        return board

    def daily_memo(self,day):
        from datetime import datetime,timedelta
        from scripts.local_office import KST
        start=datetime.combine(day,datetime.min.time(),KST).timestamp()
        end=datetime.combine(day+timedelta(days=1),datetime.min.time(),KST).timestamp()
        with self.connect() as con:
            rows=[dict(row) for row in con.execute('''SELECT t.id,t.role,t.prompt,t.status,t.updated FROM tasks t
                WHERE t.updated>=? AND t.updated<? AND t.root_id IS NULL ORDER BY t.updated''',(start,end))]
            messages=con.execute('SELECT COUNT(*) FROM messages WHERE created>=? AND created<?',(start,end)).fetchone()[0]
        return {'day':day.isoformat(),'tasks':rows,'messages':messages,
                'submitted':sum(t['status'] in ('review','completed') for t in rows),
                'failed':sum(t['status'] in ('failed','blocked','interrupted','quota_wait') for t in rows)}
