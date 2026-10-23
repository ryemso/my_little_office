import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
from office.store import Store
from office.browser_accounts import BrowserAccounts, require_origin
from office.browser_session import ensure_authenticated
from office.naver import TITLE


class BrowserAccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.store=Store(self.tmp.name);self.accounts=BrowserAccounts(self.store)
        self.account=self.accounts.register('test_blog')

    def page(self, authenticated=False):
        page=Mock();page.url='https://nid.naver.com/nidlogin.login'
        title=Mock()
        if not authenticated:title.wait_for.side_effect=RuntimeError('not logged in')
        fields={key:Mock() for key in ['#id','#pw',r'#log\.login']}
        for field in fields.values():field.count.return_value=1
        empty=Mock();empty.count.return_value=0
        page.locator.side_effect=lambda selector: title if selector==TITLE else fields.get(selector,empty)
        return page,title,fields

    def test_profile_isolation_and_stable_registration(self):
        self.assertEqual(self.account['id'],self.accounts.register('test_blog')['id'])
        other=self.accounts.register('another_blog')
        self.assertNotEqual(self.accounts.profile(self.account),self.accounts.profile(other))
        legacy=Path(self.tmp.name)/'naver-browser';legacy.mkdir();(legacy/'marker').write_text('old')
        self.accounts.state(self.account['id'],'READY')
        self.assertTrue((self.accounts.profile(self.account)/'marker').exists())
        self.assertFalse((self.accounts.profile(other)/'marker').exists())

    def test_audit_detects_tampering_and_persists(self):
        self.accounts.state(self.account['id'],'NEEDS_USER')
        self.assertTrue(BrowserAccounts(self.store).verify_audit())
        with self.store.connect() as con:con.execute("UPDATE browser_audit SET event='READY'")
        self.assertFalse(self.accounts.verify_audit())

    def test_no_opt_in_never_reads_credentials(self):
        page,_,_=self.page();vault=Mock()
        with self.assertRaisesRegex(RuntimeError,'LOGIN_REQUIRED'):
            ensure_authenticated(page,self.accounts,self.account,'test_blog',vault_factory=vault)
        vault.assert_not_called()
        self.assertEqual(self.accounts.get(self.account['id'])['state'],'NEEDS_USER')

    def test_logged_in_session_never_reads_credentials(self):
        page,_,_=self.page(True);vault=Mock()
        ensure_authenticated(page,self.accounts,self.account,'test_blog',vault_factory=vault)
        vault.assert_not_called()
        self.assertEqual(self.accounts.get(self.account['id'])['state'],'READY')

    def opt_in(self):
        with self.store.connect() as con:con.execute('UPDATE browser_accounts SET auto_login=1 WHERE id=?',(self.account['id'],))

    def test_auto_login_success(self):
        self.opt_in();page,title,fields=self.page();title.wait_for.side_effect=[RuntimeError(),None]
        vault=Mock();vault.return_value.get.return_value=('user','secret')
        ensure_authenticated(page,self.accounts,self.account,'test_blog',vault_factory=vault)
        fields['#pw'].fill.assert_called_once_with('secret')
        self.assertNotIn('secret',str(self.accounts.list()))
        self.assertEqual(self.accounts.get(self.account['id'])['state'],'READY')

    def test_failed_login_cooldown_survives_user_attention(self):
        self.opt_in();page,_,_=self.page();vault=Mock();vault.return_value.get.return_value=('user','secret')
        with self.assertRaises(RuntimeError):ensure_authenticated(page,self.accounts,self.account,'test_blog',vault_factory=vault)
        self.assertGreater(self.accounts.get(self.account['id'])['cooldown'],0)
        vault.reset_mock()
        with self.assertRaises(RuntimeError):ensure_authenticated(page,self.accounts,self.account,'test_blog',vault_factory=vault)
        vault.assert_not_called()

    def test_captcha_requires_human_without_secret_access(self):
        self.opt_in();page,_,_=self.page();old=page.locator.side_effect
        captcha=Mock();captcha.count.return_value=1
        page.locator.side_effect=lambda selector:captcha if selector.startswith('#captcha') else old(selector)
        vault=Mock()
        with self.assertRaises(RuntimeError):ensure_authenticated(page,self.accounts,self.account,'test_blog',vault_factory=vault)
        vault.assert_not_called()

    def test_origin_policy(self):
        for url in ['http://nid.naver.com','https://nid.naver.com.evil.test','https://user@nid.naver.com','https://nid.naver.com:444']:
            with self.assertRaises(ValueError):require_origin(url,{'nid.naver.com'})
        require_origin('https://nid.naver.com/nidlogin.login',{'nid.naver.com'})

    def test_unknown_login_page_does_not_get_password(self):
        self.opt_in();page,_,fields=self.page();fields['#pw'].count.return_value=0;vault=Mock()
        with self.assertRaisesRegex(RuntimeError,'PAGE_CHANGED'):ensure_authenticated(page,self.accounts,self.account,'test_blog',vault_factory=vault)
        vault.assert_not_called()
