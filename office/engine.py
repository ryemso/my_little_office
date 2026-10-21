"""Background worker independent of Streamlit browser reruns."""
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from scripts.local_office import ROLES
from office.planning import instructions


def codex_command():
    executable = shutil.which('codex')
    if not executable:
        raise RuntimeError('Codex CLI가 없습니다. npm install -g @openai/codex 후 로그인하세요.')
    if Path(executable).suffix.lower() in ('.cmd', '.bat'):
        # Avoid shell parsing of prompts or temporary paths in Windows npm shims.
        entry = Path(executable).parent / 'node_modules/@openai/codex/bin/codex.js'
        node = shutil.which('node')
        if not node or not entry.is_file():
            raise RuntimeError('Windows npm Codex 설치를 확인하세요. Node.js와 npm install -g @openai/codex가 필요합니다.')
        return [node, str(entry)]
    return [executable]


def require_login():
    cli = codex_command()
    if os.getenv('OPENAI_API_KEY') or os.getenv('CODEX_API_KEY'):
        raise RuntimeError('API 키 환경변수를 해제하세요. 이 앱은 ChatGPT 로그인만 사용합니다.')
    try:
        result = subprocess.run(cli + ['login', 'status'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError('Codex 로그인 상태 확인에 실패했습니다.') from None
    if result.returncode or 'chatgpt' not in (result.stdout + result.stderr).lower():
        raise RuntimeError('터미널에서 codex login을 실행해 ChatGPT 계정으로 로그인하세요.')


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=15)
    else:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=10)


def run_codex(store, task, end):
    require_login()
    env = dict(os.environ)
    for key in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'GH_TOKEN', 'GITHUB_TOKEN'):
        env.pop(key, None)
    logs = store.root / 'logs'
    logs.mkdir(exist_ok=True)
    # IDs come from the local database; log filenames are independent random temp names.
    with tempfile.TemporaryDirectory(prefix='office-draft-') as directory:
        output = Path(directory) / 'result.txt'
        stdout = logs / (str(uuid.uuid4()) + '.jsonl')
        stderr = stdout.with_suffix('.log')
        prompt = f'당신은 My Little Office의 {ROLES[task["role"]]} 직원입니다. 한국어로 검토할 결과물을 제출하세요. '
        prompt += '문서와 코드는 초안으로만 작성하세요. 파일 수정·코드 실행·외부 발송을 하지 마세요. 인증 정보나 개인 파일에 접근하지 마세요. 실제로 하지 않은 행동을 완료했다고 말하지 마세요.\n'
        if task.get('parent'):
            parent = store.get(task['parent'])
            prompt += '\n이전 업무: ' + parent['prompt'] + '\n이전 결과: ' + parent['output'][-20000:] + '\n'
        prompt += instructions(store, task)
        prompt += '\n현재 업무:\n' + task['prompt']
        args = codex_command() + ['exec', '--ignore-user-config', '--sandbox', 'read-only', '--skip-git-repo-check', '--json', '-o', str(output), '-']
        kwargs = {'start_new_session': True} if os.name != 'nt' else {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
        with stdout.open('w', encoding='utf-8') as out, stderr.open('w', encoding='utf-8') as err:
            process = subprocess.Popen(args, cwd=directory, env=env, stdin=subprocess.PIPE, stdout=out, stderr=err, text=True, encoding='utf-8', **kwargs)
            try:
                process.stdin.write(prompt)
                process.stdin.close()
                while process.poll() is None:
                    current = store.get(task['id'])
                    if current['status'] == 'cancel_requested' or time.time() >= end or stdout.stat().st_size + stderr.stat().st_size > 8_000_000:
                        stop_process(process)
                        return {'status': 'interrupted', 'error': '중단 요청 또는 작업 시간·로그 크기 제한으로 멈췄습니다.'}
                    time.sleep(.2)
            finally:
                if process.poll() is None:
                    stop_process(process)
        events = []
        for line in stdout.read_text(encoding='utf-8', errors='replace').splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    events.append(value)
            except ValueError:
                pass
        failed = process.returncode or any(e.get('type') in ('turn.failed', 'error') for e in events)
        text = output.read_text(encoding='utf-8', errors='replace') if output.exists() else ''
        if failed or not text.strip() or not any(e.get('type') == 'turn.completed' for e in events):
            diagnostics = stderr.read_text(encoding='utf-8', errors='replace') + json.dumps(events)
            quota = re.search(r'usage.limit|rate.limit|quota.exceeded', diagnostics, re.I)
            return {'status': 'quota_wait' if quota else 'failed', 'error': 'Codex 사용 한도 대기. 복구 시각은 미확인입니다.' if quota else 'Codex 실행 실패. PC의 logs 폴더에서 상세를 확인하세요.'}
        if re.search(r'sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|-----BEGIN .*PRIVATE KEY-----', text):
            return {'status': 'failed', 'error': '비밀 키로 의심되는 결과의 표시를 차단했습니다. PC 로그를 확인하세요.'}
        usage = next((e.get('usage', {}) for e in reversed(events) if e.get('type') == 'turn.completed'), {})
        return {'status': 'review', 'output': text, 'usage': usage}


class Worker:
    def __init__(self, store, runner=None, start=True):
        self.store, self.runner = store, runner or run_codex
        # Same lock as the legacy polling worker; cannot run both simultaneously.
        self.lock = (store.root / 'worker.lock').open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.lock.seek(0); self.lock.write(b'0'); self.lock.flush(); self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise RuntimeError('다른 출근 실행기가 사용 중입니다. 기존 실행기를 종료하세요.') from None
        store.recover()
        self.shutdown = threading.Event()
        if start:
            self.thread = threading.Thread(target=self.loop, daemon=True, name='office-worker')
            self.thread.start()

    def step(self):
        status, _ = self.store.status()
        if not status.get('on_duty'):
            return
        task = self.store.claim()
        if not task:
            return
        try:
            result = self.runner(self.store, task, time.time() + 1200)
        except Exception:
            result = {'status': 'failed', 'error': '로컬 실행 오류. Codex 로그인과 PC 환경을 확인하세요.'}
        self.store.finish(task['id'], result)
        if self.store.get(task['id'])['status'] in ('failed', 'quota_wait'):
            self.store.pause('실행 오류·한도 대기. 확인 후 출근 버튼으로 재개하세요.')

    def loop(self):
        while not self.shutdown.wait(.5):
            try:
                self.step()
            except Exception:
                self.store.pause('작업 저장 오류. PC 저장 공간과 로그를 확인하세요.')

    def close(self):
        if self.lock.closed:
            return
        self.store.pause('앱 종료')
        self.shutdown.set()
        if hasattr(self, 'thread'):
            self.thread.join(timeout=45)
            if self.thread.is_alive():
                return  # Keep the process lock until the worker really stops.
        self.lock.close()
