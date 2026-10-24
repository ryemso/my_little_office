"""Verified ZIP updater for both ZIP installations and clean git checkouts."""
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import uuid
import zipfile

REPO = 'ryemso/my_little_office'
MANIFEST = 'office-release.json'
MAX_DOWNLOAD = 30_000_000


def digest(data):
    return hashlib.sha256(data).hexdigest()


def valid_path(value):
    path = PurePosixPath(value)
    if not value or '\\' in value or ':' in value or path.is_absolute() or '..' in path.parts or '.' in path.parts or str(path) != value:
        return False
    return not any(part.startswith('.') and part != '.github' and part != '.streamlit' and part not in ('.gitignore', '.gitattributes') for part in path.parts)


def validate_manifest(value):
    if value.get('format') != 1 or not isinstance(value.get('files'), dict) or not 1 <= len(value['files']) <= 500:
        raise ValueError('Invalid update manifest')
    for name, checksum in value['files'].items():
        if not valid_path(name) or name == MANIFEST or not isinstance(checksum, str) or len(checksum) != 64 or any(c not in '0123456789abcdef' for c in checksum):
            raise ValueError('Unsafe update manifest entry')
    return value


def download(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'MyLittleOffice-Updater', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=40) as response:
        content = response.read(MAX_DOWNLOAD + 1)
    if len(content) > MAX_DOWNLOAD:
        raise ValueError('Update exceeds size limit')
    return content


def latest_release():
    commit = json.loads(download(f'https://api.github.com/repos/{REPO}/commits/main'))['sha']
    if len(commit) != 40 or any(c not in '0123456789abcdef' for c in commit):
        raise ValueError('Invalid release revision')
    manifest_bytes = download(f'https://raw.githubusercontent.com/{REPO}/{commit}/{MANIFEST}')
    manifest = validate_manifest(json.loads(manifest_bytes))
    archive = download(f'https://codeload.github.com/{REPO}/zip/{commit}')
    return manifest, manifest_bytes, archive, commit


def verified_files(manifest, archive):
    result = {}
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        seen = set()
        total = 0
        for item in bundle.infolist():
            if item.is_dir():
                continue
            parts = item.filename.split('/', 1)
            if len(parts) != 2:
                raise ValueError('Invalid archive layout')
            name = parts[1]
            if name not in manifest['files']:
                continue  # Never extract unlisted files or arbitrary paths.
            if name in seen or item.file_size > MAX_DOWNLOAD or item.external_attr >> 16 & 0o170000 == 0o120000:
                raise ValueError('Unsafe archive member')
            total += item.file_size
            if total > MAX_DOWNLOAD:
                raise ValueError('Oversized update content')
            seen.add(name)
            content = bundle.read(item)
            if digest(content) != manifest['files'][name]:
                raise ValueError('Downloaded file checksum mismatch: ' + name)
            result[name] = content
    if set(result) != set(manifest['files']) or sum(map(len, result.values())) > MAX_DOWNLOAD:
        raise ValueError('Incomplete or oversized update')
    return result


def safe_target(root, name):
    target = root / name
    current = target
    while current != root:
        if current.is_symlink():
            raise ValueError('Symlink in installation: ' + name)
        current = current.parent
    if target.exists() and not target.is_file():
        raise ValueError('Non-file at managed path: ' + name)
    return target


def atomic_write(target, content):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.office-new-', dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def apply_release(root, manifest, manifest_bytes, contents, post_install=None):
    root = Path(root).resolve()
    validate_manifest(manifest)
    old_path = root / MANIFEST
    if not old_path.is_file() or old_path.is_symlink():
        raise ValueError('Download v0.7 or newer once to bootstrap automatic updates.')
    old = validate_manifest(json.loads(old_path.read_text(encoding='utf-8')))
    if set(contents) != set(manifest['files']) or any(digest(contents[n]) != v for n, v in manifest['files'].items()):
        raise ValueError('Unverified update content')
    if json.loads(manifest_bytes) != manifest:
        raise ValueError('Manifest content mismatch')
    names = set(old['files']) | set(manifest['files'])
    previous = {}
    for name in sorted(names):
        target = safe_target(root, name)
        existing = target.read_bytes() if target.exists() else None
        previous[name] = existing
        baseline = old['files'].get(name)
        if existing is not None and (baseline is None or digest(existing) != baseline):
            # A file already identical to the new release is safe to retain.
            if name not in contents or existing != contents[name]:
                raise ValueError('Local changes detected; nothing updated: ' + name)
        elif existing is None and baseline is not None:
            raise ValueError('Managed file was removed locally; nothing updated: ' + name)
    if old == manifest:
        return False
    # Backups and the unfinished journal stay outside managed paths.
    backup = root / '.office-backups' / (time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8])
    if (root / '.office-backups').is_symlink():
        raise ValueError('Update backup directory must not be a symlink')
    backup.mkdir(parents=True)
    for name, content in previous.items():
        if content is not None:
            target = backup / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    old_bytes = old_path.read_bytes()
    (backup / MANIFEST).write_bytes(old_bytes)
    journal = root / '.office-update-journal.json'
    if journal.exists():
        raise ValueError('An interrupted update needs recovery before retrying.')
    record = {'backup': str(backup.relative_to(root)), 'files': {name: content is not None for name, content in previous.items()}}
    atomic_write(journal, json.dumps(record).encode('utf-8'))
    try:
        for name in sorted(names):
            target = safe_target(root, name)
            if name in contents:
                target.parent.mkdir(parents=True, exist_ok=True)
                atomic_write(target, contents[name])
            elif target.exists():
                target.unlink()
        if post_install:
            post_install(root, old['files'].get('requirements.txt') != manifest['files'].get('requirements.txt'))
        atomic_write(old_path, manifest_bytes)
        journal.unlink()
        return True
    except BaseException:
        for name, content in previous.items():
            target = root / name
            if content is None:
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
        old_path.write_bytes(old_bytes)
        journal.unlink(missing_ok=True)
        raise


def recover_update(root):
    root = Path(root).resolve()
    journal = root / '.office-update-journal.json'
    if not journal.exists():
        return
    record = json.loads(journal.read_text(encoding='utf-8'))
    backup = (root / record['backup']).resolve()
    if backup.parent != root / '.office-backups' or backup.is_symlink():
        raise ValueError('Invalid update recovery backup')
    for name, existed in record['files'].items():
        if not valid_path(name):
            raise ValueError('Invalid recovery path')
        target = safe_target(root, name)
        if existed:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((backup / name).read_bytes())
        else:
            target.unlink(missing_ok=True)
    (root / MANIFEST).write_bytes((backup / MANIFEST).read_bytes())
    journal.unlink()
    print('Recovered previous files after an interrupted update.')


def acquire_lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.open('a+b')
    try:
        if os.name == 'nt':
            import msvcrt
            lock.seek(0); lock.write(b'0'); lock.flush(); lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        raise RuntimeError('Close the running office terminal first, then retry.') from None
    return lock


def post_install(root, dependencies_changed):
    if dependencies_changed:
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-r', str(root / 'requirements.txt')], cwd=root, check=True)
    # Compile rather than importing the app or running any AI task.
    for name in ('streamlit_app.py', 'office/store.py', 'office/engine.py', 'office/planning.py'):
        compile((root / name).read_text(encoding='utf-8'), name, 'exec')


def main():
    root = Path(__file__).resolve().parents[1]
    state = Path(os.getenv('LOCALAPPDATA', str(Path.home() / '.local/state'))) / 'MyLittleOffice'
    # Do not import office code while replacing it; this lock matches the worker.
    with acquire_lock(state / 'worker.lock'):
        recover_update(root)
        print('Checking GitHub for an office update...')
        manifest, raw, archive, commit = latest_release()
        changed = apply_release(root, manifest, raw, verified_files(manifest, archive), post_install)
        print(('Updated to ' if changed else 'Already current: ') + str(manifest.get('version','unknown')) + ' (' + commit[:12] + ')')


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Update stopped:', error)
        print('Your work database and virtual environment were not replaced. If dependencies failed, rerun install-office.bat.')
        raise SystemExit(1)
