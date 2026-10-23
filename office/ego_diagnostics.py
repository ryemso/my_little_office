"""Official ego-browser CLI diagnostics; private CLI output stays in memory."""
import json
import shutil
import subprocess
import time

STATES=('NOT_INSTALLED','SKILL_MISSING','CONNECTED','AUTH_REQUIRED','POLICY_BLOCKED','CONNECTION_FAILED','READY')


def classify(text):
    text=text.lower()
    if any(s in text for s in ('permission denied','policy','not allowed','declined')):return 'POLICY_BLOCKED'
    if any(s in text for s in ('authentication required','sign in required','login required')):return 'AUTH_REQUIRED'
    return 'CONNECTION_FAILED'


def inspect_local(connect=False,page=False):
    result={'status':'NOT_INSTALLED','installed':False,'guide_available':False,'running':None,
            'connected':False,'page_verified':False,'checked_at':time.time(),'timings_ms':{}}
    command=shutil.which('ego-browser')
    if not command:return result
    result['installed']=True
    try:
        start=time.monotonic()
        guide=subprocess.run([command,'skill'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=10)
        result['timings_ms']['guide']=round((time.monotonic()-start)*1000,2)
        if guide.returncode or '[ego-browser:skill] end of guide' not in guide.stdout:
            result['status']=classify(guide.stderr+guide.stdout);return result
        result['guide_available']=True;result['status']='CONNECTION_FAILED'
        if not connect:return result
        if page:
            # Public page only; never inspect signed-in tabs or account data.
            script="const task = await useOrCreateTaskSpace('office public connection diagnostic'); await openOrReuseTab('https://example.com', {wait:true,timeout:10}); const text = await snapshotText(); cliLog(text.includes('Example Domain') ? 'OFFICE_PAGE_READY' : 'OFFICE_PAGE_UNVERIFIED');"
        else:script="await listTabs(); cliLog('OFFICE_CONNECTED');"
        required=('useOrCreateTaskSpace','openOrReuseTab','snapshotText') if page else ('listTabs',)
        if not all(name in guide.stdout for name in required):
            result['status']='CONNECTION_FAILED';result['unsupported']='설치된 공식 가이드에서 진단 API를 확인하지 못했습니다.';return result
        start=time.monotonic()
        probe=subprocess.run([command,'nodejs'],input=script,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
        result['timings_ms']['public_page' if page else 'connection']=round((time.monotonic()-start)*1000,2)
        marker='OFFICE_PAGE_READY' if page else 'OFFICE_CONNECTED'
        if probe.returncode==0 and marker in probe.stdout:
            result.update(status='READY' if page else 'CONNECTED',connected=True,running=True,page_verified=page)
        else:result['status']=classify(probe.stderr+probe.stdout)
    except (OSError,subprocess.TimeoutExpired):result['status']='CONNECTION_FAILED'
    return result


def status(store):
    with store.connect() as con:return store._get(con,'ego_diagnostic',{'status':'NOT_INSTALLED','checked_at':None,'installed':None,'connected':False,'page_verified':False,'message':'진단 전입니다.'})


def diagnose(store,page=False):
    result=inspect_local(connect=True,page=page)
    from office.browser_modes import Inventory
    from office.engine import codex_command
    import os
    inventory=None
    try:
        inventory=Inventory(codex_command(),str(store.root),dict(os.environ))
        _,skills=inventory.read(str(store.root))
        result['skill_recognized']=any(s.get('name')=='ego-browser' for s in skills)
        if result['installed'] and not result['skill_recognized']:result['status']='SKILL_MISSING'
    except Exception:
        result['skill_recognized']=None;result['catalog_error']='Codex 스킬 조회 실패. 실행기 연결 진단을 확인하세요.'
        if result['status']=='READY':result['status']='CONNECTED'
    finally:
        if inventory:inventory.close()
    with store.connect() as con:store._put(con,'ego_diagnostic',result)
    return result
