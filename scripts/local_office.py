"""Personal local Codex worker. No credentials are copied into the repository."""
import base64
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timedelta, timezone

REPO = 'ryemso/my_little_office'
API = f'repos/{REPO}/contents/site/data/tasks.json'
STATE = Path(os.getenv('LOCALAPPDATA', str(Path.home() / '.local/state'))) / 'MyLittleOffice'
KST = timezone(timedelta(hours=9))
ROLES = {'lead': '총괄', 'plan': '기획·사업개발', 'dev': '개발', 'design': '디자인·콘텐츠', 'market': '마케팅·영업', 'data': '데이터·운영'}


def command(args, **kwargs):
    return subprocess.run(args, text=True, encoding='utf-8', errors='replace', capture_output=True, check=True, **kwargs)


def read_remote():
    result = json.loads(command(['gh', 'api', API]).stdout)
    return json.loads(base64.b64decode(result['content'])), result['sha']


def update_remote(change):
    # Compare-and-swap: never overwrite a concurrently queued task/result.
    for attempt in range(4):
        data, sha = read_remote()
        change(data)
        payload = {'message': 'Update local office work record [skip ci]', 'sha': sha,
                   'content': base64.b64encode(json.dumps(data, ensure_ascii=False, indent=2).encode()).decode()}
        try:
            command(['gh', 'api', '--method', 'PUT', API, '--input', '-'], input=json.dumps(payload))
            return data
        except subprocess.CalledProcessError as error:
            if '409' not in error.stderr and '422' not in error.stderr:
                raise RuntimeError('GitHub write failed; local checkpoint retained.') from None
    raise RuntimeError('Concurrent GitHub writes; restart to retry local checkpoint.')


def save(state):
    STATE.mkdir(parents=True, exist_ok=True)
    temp = STATE / 'state.tmp'
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(STATE / 'state.json')


def publish_result(state):
    result = state.get('result')
    if not result:
        return
    def apply(data):
        task = next(t for t in data['tasks'] if t['id'] == result['id'])
        task.update(result)
    update_remote(apply)
    state.pop('result', None)
    state.pop('active', None)
    save(state)


def execute(task, seconds):
    env = dict(os.environ)
    for key in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'GH_TOKEN', 'GITHUB_TOKEN'):
        env.pop(key, None)
    with tempfile.TemporaryDirectory(prefix='office-draft-') as directory:
        output = Path(directory) / 'result.txt'
        prompt = (f"You are the {ROLES[task['role']]} employee of My Little Office. "
                  'Produce a Korean deliverable for human review. Do not claim external actions were performed. '
                  'Do not access credentials, private files, or external accounts. '
                  'Only draft the requested document or code as text; do not execute generated code.\nTask:\n' + task['prompt'])
        args = ['codex', 'exec', '--ignore-user-config', '--sandbox', 'read-only',
                '--skip-git-repo-check', '--json', '-o', str(output), '-']
        try:
            run = subprocess.run(args, input=prompt, cwd=directory, env=env, text=True,
                                 encoding='utf-8', errors='replace', capture_output=True,
                                 timeout=max(1, min(1200, seconds)))
        except subprocess.TimeoutExpired:
            return {'status': 'interrupted', 'error': '작업 시간 초과. 재등록 전 결과를 확인하세요.'}
        text = output.read_text(encoding='utf-8') if output.exists() else ''
        events = []
        for line in run.stdout.splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        completed = any(e.get('type') == 'turn.completed' for e in events)
        failed = any(e.get('type') in ('turn.failed', 'error') for e in events)
        if run.returncode or failed or not completed or not text.strip():
            # Raw CLI diagnostics remain local; may contain local paths or account details.
            STATE.mkdir(parents=True, exist_ok=True)
            (STATE / 'last-error.txt').write_text(run.stderr + '\n' + run.stdout, encoding='utf-8')
            return {'status': 'failed', 'error': 'Codex 실행 실패 또는 사용 한도. PC의 last-error.txt 확인 후 수동 재등록하세요.'}
        if re.search(r'sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|-----BEGIN .*PRIVATE KEY-----', text):
            return {'status': 'failed', 'error': '비밀 키로 의심되는 출력의 공개를 차단했습니다.'}
        usage = next((e.get('usage', {}) for e in reversed(events) if e.get('type') == 'turn.completed'), {})
        return {'status': 'review', 'output': text, 'usage': usage, 'model': 'Codex · 로컬 설정 기본 모델'}


def main():
    for name in ('gh', 'codex'):
        if not shutil.which(name):
            raise RuntimeError(f'{name} is not installed. Read docs/AI_SETUP.md.')
    if os.getenv('OPENAI_API_KEY') or os.getenv('CODEX_API_KEY'):
        raise RuntimeError('Remove API-key environment variables; this worker requires ChatGPT login.')
    login = command(['codex', 'login', 'status'])
    if 'chatgpt' not in (login.stdout + login.stderr).lower():
        raise RuntimeError('Run codex login and choose ChatGPT before clocking in.')
    command(['gh', 'auth', 'status'])
    STATE.mkdir(parents=True, exist_ok=True)
    # OS lock is released even if the PC/process crashes. One worker per PC.
    lock = (STATE / 'worker.lock').open('a+b')
    if os.name == 'nt':
        import msvcrt
        lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    path = STATE / 'state.json'
    state = json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    publish_result(state)
    if state.get('active'):
        state['result'] = {'id': state['active'], 'status': 'interrupted', 'error': 'PC 작업 중단. 수동 확인 후 재등록하세요.'}
        save(state); publish_result(state)
    print('Clocked in. Ctrl+C clocks out. No daily work-period limit; Codex usage limits still apply.')
    print(f'Local checkpoint: {STATE}')
    while True:
        data, _ = read_remote()
        pending = next((t for t in reversed(data['tasks']) if t.get('status') == 'queued'), None)
        if not pending:
            time.sleep(20)
            continue
        if pending.get('role') not in ROLES or not 5 <= len(pending.get('prompt', '')) <= 5000 or not pending.get('publish_consent'):
            raise RuntimeError('Invalid queued task; inspect GitHub record.')
        identifier = pending['id']
        def claim(record):
            task = next(t for t in record['tasks'] if t['id'] == identifier)
            if task['status'] != 'queued':
                raise RuntimeError('Task already claimed by another worker. Restart.')
            task.update(status='running', engine='local-codex', started_at=datetime.now(timezone.utc).isoformat())
        # Claim atomically before checkpoint; a crash here leaves a stale task for manual review.
        update_remote(claim)
        state['active'] = identifier; save(state)
        print('Working:', pending['role'], identifier)
        result = execute(pending, 1200)
        state['result'] = dict(result, id=identifier, finished_at=datetime.now(timezone.utc).isoformat())
        save(state); publish_result(state)
        if result['status'] != 'review':
            print('Paused after failure/interruption. Inspect locally before restarting.')
            return


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print('\nClocked out. Restart recovers checkpoints; interrupted tasks are not rerun automatically.')
    except (RuntimeError, subprocess.CalledProcessError, OSError, ValueError, KeyError, StopIteration) as error:
        print('Office stopped:', str(error) if not isinstance(error, subprocess.CalledProcessError) else 'Local command failed. Check login/network.')
        raise SystemExit(1)
