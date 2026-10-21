import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile
from scripts.update_office import digest, apply_release, verified_files, validate_manifest, recover_update, acquire_lock, MANIFEST


def release(files):
    manifest={'format':1,'version':'test','files':{n:digest(v) for n,v in files.items()}}
    return manifest,json.dumps(manifest).encode()

class UpdaterTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.old={'app.py':b'old code','obsolete.py':b'old helper'}
        manifest,raw=release(self.old)
        (self.root/MANIFEST).write_bytes(raw)
        for n,v in self.old.items():(self.root/n).write_bytes(v)
        (self.root/'.venv').mkdir();(self.root/'.venv/keep.txt').write_text('keep')
        (self.root/'my-notes.txt').write_text('personal note')

    def tearDown(self):self.temp.cleanup()

    def test_update_preserves_venv_custom_files_and_backup(self):
        files={'app.py':b'new code','new.py':b'new helper'};manifest,raw=release(files)
        self.assertTrue(apply_release(self.root,manifest,raw,files))
        self.assertEqual((self.root/'app.py').read_bytes(),b'new code')
        self.assertFalse((self.root/'obsolete.py').exists())
        self.assertEqual((self.root/'.venv/keep.txt').read_text(),'keep')
        self.assertEqual((self.root/'my-notes.txt').read_text(),'personal note')
        self.assertEqual(next((self.root/'.office-backups').glob('*/app.py')).read_bytes(),b'old code')
        self.assertFalse(apply_release(self.root,manifest,raw,files))

    def test_modified_code_and_untracked_collision_abort(self):
        (self.root/'app.py').write_bytes(b'my edits')
        files={'app.py':b'new code'};manifest,raw=release(files)
        with self.assertRaises(ValueError):apply_release(self.root,manifest,raw,files)
        self.assertEqual((self.root/'app.py').read_bytes(),b'my edits')
        self.assertTrue((self.root/'obsolete.py').exists())

    def test_post_install_failure_rolls_back_files(self):
        files={'app.py':b'new code','new.py':b'new helper'};manifest,raw=release(files)
        old_manifest=(self.root/MANIFEST).read_bytes()
        def fail(*args):raise RuntimeError('dependency failure')
        with self.assertRaises(RuntimeError):apply_release(self.root,manifest,raw,files,fail)
        self.assertEqual((self.root/'app.py').read_bytes(),b'old code')
        self.assertTrue((self.root/'obsolete.py').exists())
        self.assertFalse((self.root/'new.py').exists())
        self.assertEqual((self.root/MANIFEST).read_bytes(),old_manifest)

    def test_hash_and_path_validation(self):
        files={'app.py':b'new code'};manifest,raw=release(files)
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w') as bundle:bundle.writestr('repo/app.py',b'tampered')
        with self.assertRaises(ValueError):verified_files(manifest,archive.getvalue())
        for name in ('../outside','.venv/attack.py','/outside','dir/../../outside','C:/outside'):
            bad,_=release({name:b'bad'})
            with self.assertRaises(ValueError):validate_manifest(bad)

    def test_interrupted_update_recovery(self):
        backup=self.root/'.office-backups/recovery';backup.mkdir(parents=True)
        (backup/'app.py').write_bytes(b'old code');(backup/MANIFEST).write_bytes((self.root/MANIFEST).read_bytes())
        (self.root/'app.py').write_bytes(b'partial update');(self.root/'new.py').write_bytes(b'partial addition')
        journal={'backup':'.office-backups/recovery','files':{'app.py':True,'new.py':False}}
        (self.root/'.office-update-journal.json').write_text(json.dumps(journal))
        recover_update(self.root)
        self.assertEqual((self.root/'app.py').read_bytes(),b'old code')
        self.assertFalse((self.root/'new.py').exists())

    def test_active_worker_lock_blocks_updating(self):
        lock=acquire_lock(self.root/'worker.lock')
        try:
            with self.assertRaises(RuntimeError):acquire_lock(self.root/'worker.lock')
        finally:lock.close()
