"""Safe local capability diagnostics: never read or publish complete CLI config."""
from office.app_server import inspect_cli, TESTED_VERSION


def status(store):
    with store.connect() as con:
        mode=store._get(con,'runtime_mode','exec')
        diagnostic=store._get(con,'runtime_diagnostic',{})
    return {'office_version':'0.20.3','mode':mode,'diagnostic':diagnostic,'tested_version':TESTED_VERSION,
            'exec_approval_bridge':False,'appserver_approval_bridge':True,
            'browser_origin_verified':False,
            'message':'실제 브라우저 origin 승인 경로는 사용자 PC에서 확인 전입니다. Chrome 사이트 권한과 별개입니다.'}


def diagnose(store, command=None):
    import time
    from office.engine import codex_command, safe_diagnostic
    try:
        result=inspect_cli(command or codex_command())
        if result['supported']:
            from office.protocol_probe import probe
            result.update(probe(command or codex_command(),str(store.root)))
            result['supported']=bool(result.get('handshake') and result.get('schema_supported'))
        result.update(checked_at=time.time(),origin_cause='unverified',
                      bridge='appserver opt-in',
                      next_step='대화형 시험 모드에서 실제 요청이 승인함에 나타나는지 확인하세요. 요청 없이 즉시 거절되면 상위 정책/도구 호스트 확인이 필요합니다.')
    except Exception as error:result={'supported':False,'checked_at':time.time(),'error':safe_diagnostic(error)}
    with store.connect() as con:store._put(con,'runtime_diagnostic',result)
    return result
