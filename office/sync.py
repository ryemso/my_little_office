"""Optional explicit publication; never required to execute local work."""
from datetime import datetime, timezone
from scripts.local_office import ROLES, update_remote


def publish(tasks):
    records = []
    for task in tasks:
        # Only settled records. A queued public record must not trigger the legacy worker.
        if task['status'] in ('queued', 'running', 'cancel_requested', 'delegating', 'awaiting_approval'):
            continue
        records.append(dict(id='streamlit-'+task['id'], role=task['role'], role_name=ROLES[task['role']],
                            prompt=task['prompt'], status=task['status'], output=task['output'],
                            error=task['error'], engine='streamlit-local', publish_consent=True,
                            started_at=datetime.fromtimestamp(task['created'], timezone.utc).isoformat(),
                            model='Codex · PC 실행', root_id=task.get('root_id'), kind=task.get('kind', 'single'), ordinal=task.get('ordinal', 0), plan_json=task.get('plan_json', '')))
    if not records:
        raise ValueError('공개할 종료 기록이 없습니다.')
    def apply(data):
        identifiers = {record['id'] for record in records}
        data['tasks'] = records + [task for task in data['tasks'] if task['id'] not in identifiers]
    update_remote(apply)
    return len(records)
