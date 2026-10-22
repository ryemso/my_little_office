"""Persistent project workspaces, change evidence and conflict-checked application."""
import difflib
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import time
import uuid
import zipfile

IGNORED = {'.git','.venv','venv','node_modules','__pycache__','.codex','.ssh','.aws','.azure','.office-backups','.pytest_cache','.mypy_cache','.next'}
SENSITIVE = {'.npmrc','.pypirc','.netrc','secrets.toml','auth.json'}
LIMIT = 50_000_000


def walk_error(error):
    raise error


def files(root):
    root = Path(root)
    found = {}
    total = 0
    for folder, dirs, names in os.walk(root, followlinks=False,onerror=walk_error):
        dirs[:] = [d for d in dirs if d not in IGNORED and not (Path(folder)/d).is_symlink()]
        for name in names:
            path=Path(folder)/name
            if path.is_symlink() or name in SENSITIVE or name.startswith('.env') or name.startswith('.office-new-'):
                continue
            if not path.is_file():
                continue
            total += path.stat().st_size
            if total > LIMIT or len(found) >= 10000:
                raise ValueError('작업공간이 너무 큽니다. 코드·자료 폴더만 등록하세요 (최대 50MB/10,000개 파일).')
            found[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def target(root, name):
    root=Path(root).resolve()
    path=root/name
    if not path.resolve().is_relative_to(root) or name.startswith('/') or '\\' in name or '..' in Path(name).parts:
        raise ValueError('잘못된 작업 파일 경로')
    current=path
    while current != root:
        if current.is_symlink():raise ValueError('심볼릭 링크 경로는 반영하지 않습니다.')
        current=current.parent
    if path.exists() and not path.is_file():raise ValueError('파일 경로가 디렉터리와 충돌합니다.')
    return path


class Workspace:
    def __init__(self, store, task):
        self.store=store
        self.task=task
        self.key=task.get('root_id') or task['id']
        self.directory=store.root/'runs'/hashlib.sha256(self.key.encode()).hexdigest()[:24]
        self.work=self.directory/'work'
        self.meta=self.directory/'baseline.json'

    def prepare(self):
        if not self.task.get('project_id'):
            return None
        project=self.store.project(self.task['project_id'])
        if not project:raise ValueError('연결된 프로젝트를 찾을 수 없습니다.')
        if self.meta.exists():
            info=json.loads(self.meta.read_text(encoding='utf-8'))
            if info['project_id'] != project['id'] or not self.work.is_dir():raise ValueError('작업공간 기록이 일치하지 않습니다.')
            return project
        source=Path(project['path'])
        if not source.is_dir():raise ValueError('프로젝트 폴더를 찾을 수 없습니다.')
        baseline=files(source)
        self.directory.mkdir(parents=True,exist_ok=True)
        if self.work.exists():shutil.rmtree(self.work)
        self.work.mkdir()
        for name in baseline:
            output=self.work/name;output.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(source/name,output)
        self.meta.write_text(json.dumps({'project_id':project['id'],'source':str(source),'files':baseline,'applied':False},ensure_ascii=False),encoding='utf-8')
        return project

    def changes(self):
        if not self.meta.exists():return []
        baseline=json.loads(self.meta.read_text(encoding='utf-8'))['files']
        current=files(self.work)
        return [{'path':name,'change':'삭제' if name not in current else '추가' if name not in baseline else '수정'}
                for name in sorted(set(baseline)|set(current)) if baseline.get(name)!=current.get(name)]

    def preview(self):
        if not self.meta.exists():return ''
        info=json.loads(self.meta.read_text(encoding='utf-8'))
        chunks=[]
        for entry in self.changes()[:50]:
            name=entry['path']
            before=target(info['source'],name)
            after=target(self.work,name)
            old=before.read_text(encoding='utf-8',errors='replace') if before.is_file() else ''
            new=after.read_text(encoding='utf-8',errors='replace') if after.is_file() else ''
            chunks.extend(difflib.unified_diff(old[:20000].splitlines(True),new[:20000].splitlines(True),fromfile='원본/'+name,tofile='작업/'+name))
        return ''.join(chunks)[:50000]

    def archive(self):
        memory=io.BytesIO()
        with zipfile.ZipFile(memory,'w',zipfile.ZIP_DEFLATED) as archive:
            for name in files(self.work):archive.write(self.work/name,name)
        return memory.getvalue()

    def fingerprint(self):
        return hashlib.sha256(json.dumps(files(self.work),sort_keys=True).encode()).hexdigest()

    def apply(self):
        state,_=self.store.status()
        if state.get('on_duty') or self.store.has_active_work():
            raise ValueError('실행 중인 작업이 끝난 뒤 퇴근하고 반영하세요.')
        root=self.store.get(self.key)
        if root['status'] not in ('review','completed'):raise ValueError('결과가 제출된 업무만 원본에 반영할 수 있습니다.')
        info=json.loads(self.meta.read_text(encoding='utf-8'))
        if info.get('applied'):raise ValueError('이미 반영한 결과입니다.')
        changes=self.changes()
        current=files(self.work)
        for entry in changes:
            name=entry['path'];path=target(info['source'],name)
            checksum=hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
            if checksum != info['files'].get(name):raise ValueError('원본 변경과 충돌하여 반영하지 않았습니다: '+name)
        backup=self.directory/('apply-backup-'+uuid.uuid4().hex[:8]);backup.mkdir()
        saved={}
        try:
            for entry in changes:
                name=entry['path'];path=target(info['source'],name)
                saved[name]=path.read_bytes() if path.exists() else None
                if saved[name] is not None:
                    old=backup/name;old.parent.mkdir(parents=True,exist_ok=True);old.write_bytes(saved[name])
                if name in current:
                    path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(target(self.work,name).read_bytes())
                else:path.unlink()
        except BaseException:
            for name,content in saved.items():
                path=target(info['source'],name)
                if content is None:path.unlink(missing_ok=True)
                else:path.write_bytes(content)
            raise
        info.update(applied=True,applied_at=time.time(),backup=str(backup))
        self.meta.write_text(json.dumps(info,ensure_ascii=False),encoding='utf-8')
        return len(changes)
