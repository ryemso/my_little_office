"""Read local connection health without displaying tokens or tool configuration."""
import json
import shutil
import subprocess


def connection_status():
    from office.engine import codex_command
    summary={'github':'GitHub CLI 미설치','mcp':[],'mcp_status':'미확인'}
    github=shutil.which('gh')
    if github:
        try:
            result=subprocess.run([github,'auth','status'],capture_output=True,timeout=15)
            summary['github']='GitHub CLI 로그인 확인됨' if result.returncode==0 else 'GitHub CLI 로그인 필요: gh auth login'
        except (OSError,subprocess.TimeoutExpired):summary['github']='GitHub CLI 상태 확인 실패'
    try:
        result=subprocess.run(codex_command()+['mcp','list','--json'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=15)
        values=json.loads(result.stdout) if result.returncode==0 else None
        if not isinstance(values,list):raise ValueError('unavailable')
        summary['mcp']=[str(item['name'])[:120] for item in values if isinstance(item,dict) and item.get('name') and item.get('enabled',True)]
        summary['mcp_status']='등록된 활성 MCP 목록 · 각 서비스 인증 성공은 해당 도구 호출 시 확인합니다.'
    except (OSError,subprocess.TimeoutExpired,ValueError,RuntimeError):summary['mcp_status']='로컬 Codex 연결 목록 확인 실패'
    return summary
