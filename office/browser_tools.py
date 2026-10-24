"""Use the explicitly registered Chrome DevTools MCP in the actual worker thread.

No runtime installation, config writes, browser fallback or automatic retries.
"""
import json
import re
import subprocess

SERVER='chrome-devtools'


def requested(task):
    return task.get('kind') not in ('plan','report') and bool(re.search(r'chrome-devtools|chrome|크롬|브라우저|지피티|chatgpt|탭\s*목록',task.get('prompt',''),re.I))


def prepare(command,cwd,env,task):
    if not requested(task):return [],False
    try:
        result=subprocess.run(command+['mcp','list','--json'],cwd=cwd,env=env,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
        rows=json.loads(result.stdout) if result.returncode==0 else None
        if not isinstance(rows,list):raise ValueError('unavailable')
    except (OSError,ValueError,subprocess.TimeoutExpired):
        raise RuntimeError('실무 실행 환경에서 MCP 등록 목록을 확인하지 못했습니다. 기존 도구로 전환하지 않았습니다.') from None
    registered=next((row for row in rows if row.get('name')==SERVER),None)
    if registered is None:return [],False
    if registered.get('enabled') is False:raise RuntimeError('chrome-devtools 연결이 비활성화되어 있습니다. 자동 활성화하지 않았습니다.')
    return ['-c','mcp_servers.chrome-devtools.startup_timeout_sec=60'],True


def catalog(rpc,thread):
    page=rpc('mcpServerStatus/list',{'threadId':thread,'serverName':SERVER,'detail':'toolsAndAuthOnly','limit':100},timeout=70)
    rows=[r for r in page.get('data',[]) if r.get('name')==SERVER]
    if not rows:raise RuntimeError('현재 직원 스레드에 chrome-devtools MCP가 없습니다. CLI 등록과 실무 환경 설정이 다릅니다.')
    row=rows[0];tools=row.get('tools') or {}
    names=sorted({str(value.get('name') or name) for name,value in tools.items() if isinstance(value,dict)})
    evidence={'server':SERVER,'runtime_status':row.get('runtimeStatus'),'tool_names':names,'tool_count':len(names),'page_verified':False}
    if row.get('toolsError') or row.get('runtimeStatus') in ('disabled','failed','cancelled','authenticationRequired') or not names:
        from office.engine import safe_diagnostic
        raise RuntimeError('chrome-devtools 실무 연결 실패 · 상태: '+str(row.get('runtimeStatus'))+' · 사유: '+safe_diagnostic(row.get('toolsError') or '실행 도구 목록이 비어 있습니다.')[:1000])
    if not any(name=='list_pages' or name.endswith('__list_pages') for name in names):raise RuntimeError('chrome-devtools에 탭 조회 도구가 제공되지 않았습니다.')
    prompt='\n앱이 이 직원의 실제 MCP 연결에서 확인한 도구: '+json.dumps(evidence,ensure_ascii=False)+'\n이 브라우저 업무는 대표가 등록한 chrome-devtools MCP를 사용하세요. 도구 검색이 있으면 chrome-devtools list_pages로 실제 호출 도구를 찾으세요. 탭·본문을 읽는 실제 호출을 수행한 뒤 결과를 보고하세요. node_repl·cua_repl 기반 Browser 스킬의 실행 절차와 혼동하지 마세요. 도구 목록 확인만으로 페이지 접근 성공을 주장하지 마세요. 접근이 거절되면 다른 실행 경로로 우회하지 말고 중단하세요.\n'
    return evidence,prompt
