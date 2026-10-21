"""GitHub only queues public work; no AI credentials or inference here."""
import json
import os
from pathlib import Path
from datetime import datetime, timezone
from local_office import ROLES

role, prompt = os.environ['TASK_ROLE'], os.environ['TASK_PROMPT'].strip()
assert role in ROLES and 5 <= len(prompt) <= 5000, 'Invalid task'
assert os.environ.get('PUBLISH_CONSENT', '').lower() == 'true', 'Public consent required'
path = Path('site/data/tasks.json')
data = json.loads(path.read_text(encoding='utf-8'))
identifier = os.environ['GITHUB_RUN_ID']
if not any(t['id'] == identifier for t in data['tasks']):
    data['tasks'].insert(0, dict(id=identifier, run_id=identifier, role=role, role_name=ROLES[role],
                               prompt=prompt, publish_consent=True, status='queued', engine='local-codex',
                               started_at=datetime.now(timezone.utc).isoformat()))
path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
