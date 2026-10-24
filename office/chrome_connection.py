"""Restore the *existing* local Chrome MCP bridge; never invent a replacement.

All discovery uses supported app-server APIs. No executable scanning, copied
credentials, patched plugin bundles, remote-debugging ports or new MCP install.
"""
import hashlib
import json
from pathlib import Path
import re
import time

BRIDGES=('cua_repl','node_repl')


def provider(name):
    for bridge in BRIDGES:
        if re.search(r'(?:^|[_-])'+bridge.replace('_',r'[_-]')+r'(?:$|[_-])',str(name)):
            return bridge
    return None


def required(task):
    if task.get('kind') in ('plan','report') or task.get('action_json'):return False
    context=json.loads(task.get('context_json') or '{}')
    if 'browser_required' in context:return context['browser_required'] is True
    # Conservative compatibility hint for old single tasks, not a permission grant.
    return bool(re.search(r'Chrome|크롬|브라우저|탭\s*목록|cua_repl|node_repl',task.get('prompt',''),re.I))


def skill_snapshot(skills):
    result=[]
    for skill in skills:
        name=str(skill.get('name',''))
        if not re.search(r'browser|chrome|computer-use',name,re.I):continue
        path=Path(skill['path'])
        item={'name':name[:100],'enabled':bool(skill.get('enabled')),'bridge':None,'sha256':None,'version':None}
        item['version']=next((p for p in path.parts if re.fullmatch(r'\d+\.\d+\.\d+(?:[.-][\w.-]+)?',p)),None)
        try:
            if path.is_file() and path.stat().st_size<=128000:
                data=path.read_bytes();body=data.decode('utf-8',errors='replace')
                item['sha256']=hashlib.sha256(data).hexdigest()
                matches=[b for b in BRIDGES if 'mcp__'+b in body]
                if len(matches)==1:item['bridge']=matches[0]
        except OSError:pass
        # Paths and document text never leave this process.
        result.append((skill['path'],item))
    return result


def launch_overrides(config,skills,root):
    """Warm configured enabled bridges and repair only a broken/versioned cwd.

Never reconstruct missing commands/env, enable disabled servers, or change an
approval decision. Relative launcher files keep their original cwd.
"""
    args=[];repairs=[];hint=None;configured=[]
    servers=config.get('mcp_servers') or {}
    for name,server in servers.items():
        bridge=provider(name)
        if bridge:
            configured.append({'provider':bridge,'enabled':server.get('enabled') is not False,
                               'cwd_exists':Path(server['cwd']).is_dir() if server.get('cwd') else None})
        if not bridge or server.get('enabled') is False:continue
        if not re.fullmatch(r'[A-Za-z0-9_-]+',name):continue
        if not server.get('command'):continue  # No incomplete override-only server.
        if bridge=='cua_repl':hint=name
        args+=['-c','mcp_servers.'+name+'.required=true']
        cwd=server.get('cwd')
        launcher=str(server.get('command',''))
        relative_launcher=bool(('/' in launcher or '\\' in launcher) and not Path(launcher).is_absolute())
        relative_scripts=relative_launcher or any(isinstance(a,str) and re.search(r'\.(?:mjs|cjs|js|py|exe)$',a,re.I) and not Path(a).is_absolute() for a in (server.get('args') or []))
        if cwd and not relative_scripts and (not Path(cwd).is_dir() or '/plugins/cache/' in str(cwd).replace('\\','/')):
            stable=Path(root)/'browser-runtime'/bridge;stable.mkdir(parents=True,exist_ok=True)
            args+=['-c','mcp_servers.'+name+'.cwd='+json.dumps(str(stable.resolve()))]
            repairs.append({'provider':bridge,'change':'stable_cwd'})
    metadata=skill_snapshot(skills)
    # A node-only document must not override a functioning, explicitly configured
    # legacy CUA tool. Preserve unrelated skills and the user's disabled servers.
    disabled=[path for path,item in metadata if hint and item['bridge']=='node_repl' and item['enabled']]
    return args,disabled,{'required':True,'server_hint':hint,'configured':configured,'skills':[item for _,item in metadata],'repairs':repairs,
                             'ego_skill_present':any(s.get('name')=='ego-browser' for s in skills),
                             'feature_flags':{key:value for key,value in (config.get('features') or {}).items() if key in ('browser_use','browser_use_external','in_app_browser') and type(value) is bool}}


def error_kind(text):
    text=str(text).lower()
    if any(s in text for s in ('denied','declined','policy','not allowed','거절','정책')):return 'POLICY_BLOCKED'
    if any(s in text for s in ('auth','login','sign in','인증','로그인')):return 'AUTH_REQUIRED'
    if any(s in text for s in ('cwd','directory','os error 2','os error 3','no such file','not found')):return 'LAUNCH_PATH_ERROR'
    return 'CONNECTION_FAILED'


def inspect_catalog(rpc,thread_id,server_hint=None):
    cursor=None;seen=set();rows=[];raw={}
    for _ in range(20):
        params={'threadId':thread_id,'detail':'toolsAndAuthOnly','limit':100}
        if server_hint:params['serverName']=server_hint
        if cursor:params['cursor']=cursor
        page=rpc('mcpServerStatus/list',params)
        for server in page.get('data',[]):
            name=server.get('name','');bridge=provider(name)
            if not bridge or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',name):continue
            tools=server.get('tools') or {};js=tools.get('js')
            if not js:
                js=next((tool for key,tool in tools.items() if key.endswith('__js') and isinstance(tool,dict)),None)
            state=server.get('runtimeStatus')
            error=server.get('toolsError')
            status=('POLICY_BLOCKED' if state=='disabled' else 'AUTH_REQUIRED' if state=='authenticationRequired' else error_kind(error) if error else
                    'TOOLS_READY' if js and state not in ('failed','disconnected') else 'TOOL_MISSING')
            row={'provider':bridge,'server':name,'status':status,'connection':state,'js_available':bool(js)}
            rows.append(row);raw[name]=js
        cursor=page.get('nextCursor')
        if not cursor:break
        if cursor in seen:raise RuntimeError('브라우저 도구 목록 커서가 반복됐습니다.')
        seen.add(cursor)
    else:raise RuntimeError('브라우저 도구 목록 페이지 한도 초과')
    # A denied/failed existing CUA path is never retried via node_repl or ego.
    legacy=[r for r in rows if r['provider']=='cua_repl']
    candidates=legacy or [r for r in rows if r['provider']=='node_repl']
    chosen=next((r for r in candidates if r['status']=='TOOLS_READY'),None)
    if any(r['status']=='POLICY_BLOCKED' for r in candidates):chosen=None
    status=chosen['status'] if chosen else next((r['status'] for r in candidates),'BRIDGE_NOT_PROVIDED')
    result={'status':status,'providers':rows,'selected':chosen,'checked_at':time.time(),
            'tool_call_verified':False,'chrome_connection_verified':False,'model_tool_exposure_verified':False,
            'cause':'런타임 도구 제공 상태이며 로그인·사이트 접근 승인 결과가 아닙니다.'}
    return result,raw.get(chosen['server']) if chosen else None


def require_catalog(rpc,thread_id,policy,store=None,task_id=None):
    result,tool=inspect_catalog(rpc,thread_id,policy.get('server_hint'))
    flags=policy.get('feature_flags',{})
    if flags.get('browser_use') is False or flags.get('browser_use_external') is False:
        result['status']='POLICY_BLOCKED';result['selected']=None;tool=None
    result['task_id']=task_id
    result['skills']=policy.get('skills',[]);result['repairs']=policy.get('repairs',[]);result['configured']=policy.get('configured',[]);result['feature_flags']=policy.get('feature_flags',{})
    for key in ('cli_version','office_version','ego_skill_present'):
        if key in policy:result[key]=policy[key]
    if store:
        record_snapshot(store,result)
        if task_id:store.message(task_id,'browser-tools','system','status','브라우저 실행 도구 확인: '+result['status'])
    if result['status']!='TOOLS_READY':
        raise RuntimeError('Chrome 실행 도구 준비 실패: '+result['status']+' · 브라우저 스킬 파일만으로 실행 가능하다고 처리하지 않습니다.')
    return result,tool


def browser_count(value):
    """Recognize only structured browser inventory, never a keyword in docs."""
    found=[]
    def visit(obj,depth=0):
        if depth>10:return
        if isinstance(obj,dict):
            browsers=obj.get('browsers')
            if isinstance(browsers,list):
                found.extend(b for b in browsers if isinstance(b,dict) and str(b.get('name','')).lower() in ('chrome','google chrome') and b.get('id') is not None and b.get('connected') is not False)
            for key,item in obj.items():
                if key not in ('description','inputSchema'):visit(item,depth+1)
        elif isinstance(obj,list):
            for item in obj:visit(item,depth+1)
        elif isinstance(obj,str) and len(obj)<300000:
            try:parsed=json.loads(obj)
            except ValueError:return
            if not isinstance(parsed,str):visit(parsed,depth+1)
    visit(value)
    return len(found)


def state_call(rpc,thread_id,result,tool,record=None):
    selected=result['selected']
    if selected['provider']!='cua_repl':
        result['status']='LEGACY_CUA_MISSING'
        return result  # No guessing bootstrap code for the newer Node bridge.
    schema=tool.get('inputSchema') or {};props=schema.get('properties') or {}
    if 'code' not in props or set(schema.get('required',[]))-{'code','title'}:
        result['status']='UNSUPPORTED_TOOL_SCHEMA';return result
    arguments={'code':'await cua.getState();'}
    if 'title' in props:arguments['title']='기존 Chrome 연결 상태 확인'
    result.update(tool_call_attempted=True,tool_call_completed=False,
                  call={'server':selected['server'],'tool':tool.get('name','js'),'operation':'cua.getState'})
    if record:record(result)
    started=time.monotonic()
    try:
        response=rpc('mcpServer/tool/call',{'threadId':thread_id,'server':selected['server'],'tool':tool.get('name','js'),'arguments':arguments})
        result['tool_call_completed']=True
        if response.get('isError'):
            result['status']=error_kind(json.dumps(response,ensure_ascii=False));return result
        result['tool_call_verified']=True
        count=browser_count(response)
        result.update(status='CHROME_CONNECTED' if count else 'STATE_CALL_OK',chrome_connection_verified=bool(count),chrome_count=count)
        # The response can contain tabs/account context. Never persist it.
        return result
    except RuntimeError as error:
        result['status']=error_kind(error);raise
    finally:
        result['probe_round_trip_ms']=round((time.monotonic()-started)*1000,2)
        if record:record(result)


def receipts(result):
    if not result.get('tool_call_attempted'):return []
    call=result['call']
    return [{'type':'mcp_tool_call','server':call['server'],'tool':call['tool'],
             'status':'completed' if result.get('tool_call_verified') else 'failed' if result.get('tool_call_completed') else 'unconfirmed',
             'source':'app_server_direct_probe'}]


def latest(store,task_id=None):
    with store.connect() as con:result=store._get(con,'chrome_diagnostic',{'status':'NOT_CHECKED','chrome_connection_verified':False})
    if task_id is not None and result.get('task_id')!=task_id:
        return {'status':'NOT_CHECKED','task_id':task_id,'chrome_connection_verified':False}
    return result


def record_snapshot(store,result):
    with store.connect() as con:
        baseline=store._get(con,'chrome_baseline',{})
        result['comparison']={'baseline_available':bool(baseline),'skill_changed':None,'bridge_changed':None,
                              'ego_presence_changed':None,'causality':'not_established'}
        if baseline:
            result['comparison'].update(skill_changed=baseline.get('skills')!=result.get('skills'),
                bridge_changed=(baseline.get('selected') or {}).get('provider')!=(result.get('selected') or {}).get('provider'),
                ego_presence_changed=baseline.get('ego_skill_present')!=result.get('ego_skill_present'))
        store._put(con,'chrome_diagnostic',result)
        history=store._get(con,'chrome_history',[])
        history.append(result);store._put(con,'chrome_history',history[-10:])
        if result.get('chrome_connection_verified'):store._put(con,'chrome_baseline',result)
