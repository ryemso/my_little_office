"""Local browser identities, session state and tamper-evident event metadata.

Secrets are deliberately absent from the database and API responses.
"""
import hashlib
import json
import re
import time
from pathlib import Path
from urllib.parse import urlsplit


class BrowserAccounts:
    def __init__(self, store):
        self.store = store
        with store.connect() as con:
            con.executescript('''
                CREATE TABLE IF NOT EXISTS browser_accounts (
                    id TEXT PRIMARY KEY, provider TEXT NOT NULL, alias TEXT NOT NULL,
                    auto_login INTEGER NOT NULL DEFAULT 0, state TEXT NOT NULL DEFAULT 'NEW',
                    failures INTEGER NOT NULL DEFAULT 0, cooldown REAL NOT NULL DEFAULT 0,
                    updated REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS browser_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, account_id TEXT NOT NULL,
                    event TEXT NOT NULL, created REAL NOT NULL, prev_hash TEXT NOT NULL,
                    entry_hash TEXT NOT NULL);
            ''')

    def register(self, alias):
        from office.naver import blog_id
        alias = blog_id(alias)
        identifier = hashlib.sha256(('naver\0' + alias).encode()).hexdigest()[:32]
        with self.store.connect() as con:
            con.execute('INSERT OR IGNORE INTO browser_accounts(id,provider,alias,updated) VALUES (?,?,?,?)',
                        (identifier, 'naver', alias, time.time()))
        return self.get(identifier)

    def get(self, identifier):
        with self.store.connect() as con:
            row = con.execute('SELECT * FROM browser_accounts WHERE id=?', (identifier,)).fetchone()
        if row is None:
            raise ValueError('등록된 브라우저 계정이 없습니다.')
        return dict(row)

    def list(self):
        with self.store.connect() as con:
            return [dict(row) for row in con.execute('SELECT * FROM browser_accounts ORDER BY alias')]

    def opt_in(self, identifier, enabled):
        self.get(identifier)
        if enabled:
            from office.secret_store import SecretStore
            if not SecretStore().exists(identifier):
                raise ValueError('PC 터미널에서 자격증명을 먼저 등록하세요.')
        with self.store.connect() as con:
            con.execute('UPDATE browser_accounts SET auto_login=?,updated=? WHERE id=?',
                        (int(bool(enabled)), time.time(), identifier))
        self.event(identifier, 'AUTO_LOGIN_ENABLED' if enabled else 'AUTO_LOGIN_DISABLED')

    def state(self, identifier, state, failed=False):
        if state not in {'NEW','PROFILE_CHECK','READY','LOGIN_REQUIRED','AUTO_LOGIN','NEEDS_USER','AUTH_FAILED','TASK_RUNNING','VERIFY_RESULT'}:
            raise ValueError('알 수 없는 브라우저 상태입니다.')
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            row = con.execute('SELECT failures,cooldown FROM browser_accounts WHERE id=?', (identifier,)).fetchone()
            if not row: raise ValueError('브라우저 계정이 없습니다.')
            failures = row['failures'] + 1 if failed else (0 if state == 'READY' else row['failures'])
            cooldown = time.time() + min(3600, 60 * 2 ** min(failures, 6)) if failed else (0 if state == 'READY' else row['cooldown'])
            con.execute('UPDATE browser_accounts SET state=?,failures=?,cooldown=?,updated=? WHERE id=?',
                        (state, failures, cooldown, time.time(), identifier))
        self.event(identifier, state)

    def event(self, identifier, event):
        # Only fixed machine codes, never page text, URLs, credentials or exception messages.
        if not re.fullmatch('[A-Z_]{2,50}', event): raise ValueError('잘못된 감사 이벤트')
        with self.store.connect() as con:
            con.execute('BEGIN IMMEDIATE')
            last = con.execute('SELECT entry_hash FROM browser_audit ORDER BY id DESC LIMIT 1').fetchone()
            previous = last[0] if last else ''
            created = time.time()
            digest = hashlib.sha256(json.dumps([identifier,event,created,previous], separators=(',',':')).encode()).hexdigest()
            con.execute('INSERT INTO browser_audit(account_id,event,created,prev_hash,entry_hash) VALUES (?,?,?,?,?)',
                        (identifier,event,created,previous,digest))

    def verify_audit(self):
        previous = ''
        with self.store.connect() as con:
            for row in con.execute('SELECT * FROM browser_audit ORDER BY id'):
                digest = hashlib.sha256(json.dumps([row['account_id'],row['event'],row['created'],previous], separators=(',',':')).encode()).hexdigest()
                if row['prev_hash'] != previous or row['entry_hash'] != digest: return False
                previous = digest
        return True

    def profile(self, account):
        # Keep the old Naver profile for the first registered identity only.
        legacy = self.store.root / 'naver-browser'
        with self.store.connect() as con:
            first = con.execute('SELECT id FROM browser_accounts ORDER BY rowid LIMIT 1').fetchone()
        destination = self.store.root / 'browser-profiles' / account['id']
        if legacy.exists() and not destination.exists() and first and first[0] == account['id']:
            destination.parent.mkdir(parents=True, exist_ok=True)
            legacy.rename(destination)
        return destination


def require_origin(url, hosts):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.hostname not in hosts or parsed.username or parsed.password or parsed.port not in (None,443):
        raise ValueError('POLICY_BLOCKED: 허용된 HTTPS 사이트가 아닙니다.')
