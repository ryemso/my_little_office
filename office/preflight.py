"""Real host checks; these do not certify the separate Codex sandbox."""
import json
from pathlib import Path
import subprocess
from subprocess import Popen as HostProcess
import sys
import tempfile


def check_workspace(directory):
    root = Path(directory).resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(str(root))
    with tempfile.TemporaryDirectory(prefix='.office-check-', dir=root) as temporary:
        folder = Path(temporary)
        probe = folder / 'probe.txt'
        probe.write_text('office-read-write', encoding='utf-8')
        if probe.read_text(encoding='utf-8') != 'office-read-write':
            raise RuntimeError('작업 폴더 파일 읽기·쓰기 검증 실패')
        with HostProcess(
            [sys.executable, '-c', 'import os,json; print(json.dumps({"cwd":os.getcwd()}))'],
            cwd=root, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8') as process:
            try:
                stdout, stderr=process.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill();process.communicate();raise
            if process.returncode:
                raise RuntimeError('작업 폴더에서 Python 실행 실패: '+stderr[-1000:])
        actual = Path(json.loads(stdout)['cwd']).resolve()
        if actual != root:
            raise RuntimeError('명령 실행 작업 경로 불일치')
    return {'scope':'app_host', 'cwd':str(root), 'read':True, 'write':True,
            'process':True, 'codex_sandbox_verified':False}
