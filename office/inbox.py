"""Actionable owner decisions shared by the avatar badge and popup."""
from office.workspaces import Workspace


class Decisions:
    def initialize_decisions(self):
        with self.connect() as con:
            con.execute('CREATE TABLE IF NOT EXISTS decision_ack(task_id TEXT PRIMARY KEY,version REAL NOT NULL)')

    def pending_decisions(self):
        with self.connect() as con:
            return [dict(row) for row in con.execute('''SELECT t.*,
                CASE WHEN status='awaiting_approval' THEN 'approval' WHEN status='review' THEN 'review' ELSE 'attention' END AS decision_type,
                EXISTS(SELECT 1 FROM tasks p WHERE p.root_id=t.root_id AND p.ordinal<t.ordinal
                    AND p.status NOT IN ('review','completed')) AS waiting_for_previous
                FROM tasks t WHERE
                (status='review' AND root_id IS NULL AND kind IN ('single','plan')) OR status='awaiting_approval' OR
                (root_id IS NULL AND status IN ('failed','blocked','interrupted','quota_wait') AND
                 NOT EXISTS(SELECT 1 FROM decision_ack a WHERE a.task_id=t.id AND a.version=t.updated))
                ORDER BY CASE WHEN status='awaiting_approval' THEN 0 WHEN status='review' THEN 1 ELSE 2 END,created DESC''')]

    def acknowledge_decision(self,identifier,version):
        with self.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row=con.execute('SELECT * FROM tasks WHERE id=?',(identifier,)).fetchone()
            if not row or row['root_id'] or row['status'] not in ('failed','blocked','interrupted','quota_wait') or row['updated']!=version:
                raise ValueError('확인할 업무 상태가 바뀌었습니다. 목록을 새로고침하세요.')
            con.execute('INSERT OR REPLACE INTO decision_ack VALUES(?,?)',(identifier,version))
            self._message(con,identifier,'attention-ack:'+str(version),'owner','status','문제 보고를 확인했습니다. 실행 완료나 재시도로 처리하지 않습니다.')


def approve_decision(store,identifier,version,fingerprint):
    task=store.get(identifier)
    if not task or task['status']!='awaiting_approval' or task['updated']!=version:
        raise ValueError('승인 대상 상태가 바뀌었습니다. 목록을 새로고침하세요.')
    workspace=Workspace(store,task);workspace.prepare()
    if workspace.fingerprint()!=fingerprint:
        raise ValueError('검토한 뒤 작업 파일이 바뀌었습니다. 변경 내용을 새로 확인한 뒤 승인하세요.')
    store.approve(identifier,fingerprint)
