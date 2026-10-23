"""Deterministic Naver authentication; credentials never enter an AI prompt."""
import time
from office.browser_accounts import BrowserAccounts, require_origin


def challenge(page):
    if page.locator('#captcha, .captcha, input[name="captcha"]').count(): return 'CAPTCHA_REQUIRED'
    if page.locator('#otp, input[name="otp"], .two_step_verify').count(): return 'MFA_REQUIRED'
    return None


def ensure_authenticated(page, accounts, account, blog, manual=False, vault_factory=None):
    from office.naver import TITLE
    accounts.state(account['id'], 'PROFILE_CHECK')
    page.goto('https://blog.naver.com/'+blog+'/postwrite',wait_until='domcontentloaded')
    try:
        page.locator(TITLE).wait_for(state='visible',timeout=5000)
        accounts.state(account['id'],'READY');return
    except Exception: pass
    accounts.state(account['id'],'LOGIN_REQUIRED')
    if manual:
        # The visible browser is the only manual credential entry surface.
        page.locator(TITLE).wait_for(state='visible',timeout=600000)
        accounts.state(account['id'],'READY');return
    account=accounts.get(account['id'])
    if not account['auto_login'] or account['failures']>=2 or account['cooldown']>time.time() or challenge(page):
        accounts.state(account['id'],'NEEDS_USER')
        raise RuntimeError('LOGIN_REQUIRED: 연결 관리에서 해당 계정에 직접 로그인하세요.')
    require_origin(page.url, {'nid.naver.com'})
    # Never type into an unrecognised page, even if a redirect has the right host.
    if page.locator('#id').count()!=1 or page.locator('#pw').count()!=1 or page.locator(r'#log\.login').count()!=1:
        accounts.state(account['id'],'NEEDS_USER');raise RuntimeError('PAGE_CHANGED: 로그인 화면을 확인하세요.')
    if vault_factory is None:
        from office.secret_store import SecretStore
        vault_factory=SecretStore
    secret=vault_factory().get(account['id'])
    if secret is None:
        accounts.state(account['id'],'NEEDS_USER');raise RuntimeError('LOGIN_REQUIRED: PC 자격증명이 없습니다.')
    accounts.state(account['id'],'AUTO_LOGIN')
    try:
        require_origin(page.url, {'nid.naver.com'})
        page.locator('#id').fill(secret[0])
        require_origin(page.url, {'nid.naver.com'})
        page.locator('#pw').fill(secret[1])
        require_origin(page.url, {'nid.naver.com'})
        page.locator(r'#log\.login').click()
        page.locator(TITLE).wait_for(state='visible',timeout=15000)
    except Exception:
        accounts.state(account['id'],'AUTH_FAILED',failed=True)
        accounts.state(account['id'],'NEEDS_USER')
        raise RuntimeError('LOGIN_REQUIRED: 자동 로그인 실패·추가 인증을 직접 확인하세요.') from None
    finally: secret=None
    accounts.state(account['id'],'READY')
