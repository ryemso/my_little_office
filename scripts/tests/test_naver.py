import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
from office.naver import read_post,blog_id,post_url,profile_lock,run_editor,write_receipt

class NaverTests(unittest.TestCase):
    def sample(self,root):
        post={'post_id':'example-1','title':'제목','body':'원문 본문'}
        (root/'post.json').write_text(json.dumps(post,ensure_ascii=False),encoding='utf-8')
        return post

    def test_target_validation_and_post_digest_changes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);post=self.sample(root)
            first=read_post(root,'post.json')[2]
            post['body']='다른 원문';(root/'post.json').write_text(json.dumps(post))
            self.assertNotEqual(first,read_post(root,'post.json')[2])
            for name in ['../post.json','/post.json']:
                with self.assertRaises(ValueError):read_post(root,name)
        self.assertTrue(post_url('https://blog.naver.com/qt0177/123','qt0177'))
        self.assertFalse(post_url('https://blog.naver.com.attacker.test/qt0177/123','qt0177'))
        self.assertFalse(post_url('https://blog.naver.com/another/123','qt0177'))
        with self.assertRaises(ValueError):blog_id('../bad')

    def test_profile_cannot_be_used_concurrently(self):
        with tempfile.TemporaryDirectory() as folder:
            with profile_lock(folder):
                with self.assertRaises(ValueError):
                    with profile_lock(folder):pass

    def test_uncertain_publication_never_clicks_again(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);post=self.sample(root);digest=read_post(root,'post.json')[2]
            key=hashlib.sha256(('qt0177\0'+post['post_id']).encode()).hexdigest()
            write_receipt(root/'publishing'/(key+'.json'),{'state':'uncertain','digest':digest})
            page=Mock()
            with self.assertRaisesRegex(RuntimeError,'불확실'):
                run_editor(page,root,root,'qt0177','post.json','publish','task')
            page.get_by_role.assert_not_called();page.goto.assert_not_called()

    def test_changed_approved_content_never_publishes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);post=self.sample(root)
            key=hashlib.sha256(('qt0177\0'+post['post_id']).encode()).hexdigest()
            write_receipt(root/'publishing'/(key+'.json'),{'state':'draft','digest':'old'})
            page=Mock()
            with self.assertRaisesRegex(ValueError,'내용이 바뀌었'):
                run_editor(page,root,root,'qt0177','post.json','publish','task')
            page.goto.assert_not_called()
