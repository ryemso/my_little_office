"""Per-task Codex catalog controls, using public config/skills RPCs.

No alternate CODEX_HOME, credential copying, global config writes or approval
changes. This restricts the skill/MCP catalog, NOT arbitrary host shell code.
"""
import json
import time
from pathlib import Path

MODES=('standard','ego')


def mode(task):
    context=json.loads(task.get('context_json') or '{}')
    if not isinstance(context,dict):raise ValueError('브라우저 모드 업무 설정이 손상됐습니다.')
    value=context.get('browser_mode','standard')
    if value not in MODES:raise ValueError('지원하지 않는 브라우저 모드입니다.')
    return value


def is_ego(value):
    import re
    return bool(re.search(r'(?i)(?:^|[^a-z0-9])ego(?:[-_ /]|$)',str(value)))


class Inventory:
    def __init__(self,command,cwd,env,overrides=()):
        from office.app_server import Transport,inspect_cli
        if not inspect_cli(command)['supported']:raise RuntimeError('브라우저 모드 검증은 Codex 0.163.0에서 지원합니다.')
        self.transport=Transport(command+['app-server','--listen','stdio://',*overrides],cwd,env)
        self.serial=0
        try:
            self.call('initialize',{'clientInfo':{'name':'office_browser_policy','version':'1'}})
            self.transport.send({'method':'initialized'})
        except Exception:self.close();raise

    def call(self,method,params):
        self.serial+=1;identifier='browser:'+str(self.serial)
        self.transport.send({'id':identifier,'method':method,'params':params})
        until=time.monotonic()+12
        while time.monotonic()<until:
            value=self.transport.receive()
            if value and value.get('id')==identifier:
                if 'error' in value:raise RuntimeError('브라우저 모드 설정 조회 실패: '+method)
                return value.get('result',{})
            if value and (value.get('transport_error') or value.get('transport_closed')):break
        raise RuntimeError('브라우저 모드 설정 조회 시간 초과: '+method)

    def read(self,cwd):
        # Raw user config can contain private data. Keep it in memory only.
        config=self.call('config/read',{'cwd':cwd,'includeLayers':False})['config']
        listing=self.call('skills/list',{'cwds':[cwd],'forceReload':True})
        skills=[s for entry in listing.get('data',[]) for s in entry.get('skills',[])]
        if any(entry.get('errors') for entry in listing.get('data',[])):
            raise RuntimeError('스킬 목록에 오류가 있어 브라우저 모드를 검증하지 못했습니다.')
        return config,skills

    def close(self):self.transport.close()


def overrides(config,skills,selected):
    """Preserve unrelated skill overrides; never enable a disabled MCP server."""
    controlled=[s for s in skills if is_ego(s.get('name')) or is_ego(s.get('pluginId','')) or is_ego(s.get('path'))]
    settings=list((config.get('skills') or {}).get('config') or [])
    paths={str(s['path']) for s in controlled}
    settings=[s for s in settings if str(s.get('path')) not in paths and str(Path(s.get('path',''))/'SKILL.md') not in paths]
    settings.extend({'path':s['path'],'enabled':selected=='ego'} for s in controlled)
    args=['-c','skills.config='+'['+','.join('{path='+json.dumps(s['path'])+',enabled='+str(s.get('enabled',True)).lower()+'}' for s in settings)+']'] if settings else []
    servers=config.get('mcp_servers') or {}
    dependencies={d.get('value') for s in controlled for d in (s.get('dependencies') or {}).get('tools',[]) if d.get('type')=='mcp'}
    affected=[name for name,server in servers.items() if name in dependencies or is_ego(name) or is_ego(server.get('command','')) or any(is_ego(a) for a in (server.get('args') or [])) or is_ego(server.get('url',''))]
    if selected=='standard':
        for name in affected:args+=['-c','mcp_servers.'+json.dumps(name)+'.enabled=false']
    return args,controlled,affected


def prepare(task,command,cwd,env,base_args=()):
    selected=mode(task);start=time.monotonic()
    inventory=Inventory(command,cwd,env,base_args)
    try:config,skills=inventory.read(cwd)
    finally:inventory.close()
    args,controlled,servers=overrides(config,skills,selected)
    if selected=='ego':
        if not any(s.get('name')=='ego-browser' for s in controlled):raise RuntimeError('SKILL_MISSING: Codex에서 ego-browser 스킬을 찾지 못했습니다.')
        from office.ego_diagnostics import inspect_local
        result=inspect_local(connect=True)
        if result['status'] not in ('CONNECTED','READY'):raise RuntimeError(result['status']+': ego 연결 진단을 확인하세요. 다른 브라우저로 전환하지 않습니다.')
    # Check the actual effective config/catalog in a fresh process before inference.
    check=Inventory(command,cwd,env,[*base_args,*args])
    try:
        effective,available=check.read(cwd)
        enabled=[s for s in available if s.get('enabled') and (is_ego(s.get('name')) or is_ego(s.get('pluginId','')) or is_ego(s.get('path')))]
        if selected=='standard' and (enabled or any((effective.get('mcp_servers') or {}).get(s,{}).get('enabled',True) for s in servers)):
            raise RuntimeError('POLICY_BLOCKED: 기본 모드의 스킬/MCP 비활성화 검증 실패')
        if selected=='ego' and not any(s.get('name')=='ego-browser' for s in enabled):raise RuntimeError('POLICY_BLOCKED: ego 스킬 활성화가 상위 정책에 의해 차단됐습니다.')
    finally:check.close()
    return args,{'mode':selected,'catalog_verified':True,'ego_skills':len(controlled),'ego_mcp_servers':len(servers),
                 'preparation_ms':round((time.monotonic()-start)*1000,2),
                 'scope':'codex_skill_mcp_catalog','host_shell_isolated':False}
