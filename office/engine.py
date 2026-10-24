"""Background worker independent of Streamlit browser reruns."""
import json
import os
import platform
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import traceback
import uuid
from scripts.local_office import ROLES
from office.planning import instructions, EXTERNAL_EXECUTION_POLICY
from office.workspaces import Workspace, files
from office.knowledge import prepare_inputs
from office.conversation import LiveEvents
from office.windows_settings import windows_settings
from office.preflight import check_workspace


def safe_diagnostic(value):
    """Diagnostics are local, but still omit common credentials from UI/logs."""
    value=str(value)
    value=re.sub(r'-----BEGIN [^-]*PRIVATE KEY-----.*?-----END [^-]*PRIVATE KEY-----','[REDACTED PRIVATE KEY]',value,flags=re.S)
    value=re.sub(r'sk-[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]+', '[REDACTED]',value)
    value=re.sub(r'(?i)(bearer\s+)[^\s\"\']+',r'\1[REDACTED]',value)
    value=re.sub(r'(?i)((?:api[_-]?key|access[_-]?token|refresh[_-]?token|password)\s*[\"\']?\s*[:=]\s*[\"\']?)[^\s\"\',}]+',r'\1[REDACTED]',value)
    for name in ('OPENAI_API_KEY','CODEX_API_KEY','GH_TOKEN','GITHUB_TOKEN'):
        secret=os.getenv(name)
        if secret:value=value.replace(secret,'[REDACTED]')
    return value


def exception_result(store, error):
    identifier=str(uuid.uuid4())
    message=f'{type(error).__name__}: {safe_diagnostic(error)}'
    try:
        logs=store.root/'logs';logs.mkdir(exist_ok=True)
        path=logs/('worker-'+identifier+'.log')
        path.write_text(safe_diagnostic(traceback.format_exc()),encoding='utf-8')
        detail='\n진단 파일: '+str(path)
    except OSError:
        detail='\n진단 파일 저장에도 실패했습니다. PC 폴더 권한·저장 공간을 확인하세요.'
    return {'status':'failed','error':'로컬 실행 실패 · '+message[:1200]+detail}


def codex_command():
    executable = shutil.which('codex')
    if not executable:
        raise RuntimeError('Codex CLI가 없습니다. npm install -g @openai/codex 후 로그인하세요.')
    if Path(executable).suffix.lower() in ('.cmd', '.bat'):
        # Prefer the native binary: Node's second spawn can fail even when
        # the very same installed exe runs successfully from PowerShell.
        modules=Path(executable).parent/'node_modules'
        package=modules/'@openai/codex'
        architecture='arm64' if platform.machine().lower() in ('arm64','aarch64') else 'x64'
        triple='aarch64-pc-windows-msvc' if architecture=='arm64' else 'x86_64-pc-windows-msvc'
        relative=Path('vendor')/triple/'bin/codex.exe'
        candidates=[package/'node_modules/@openai'/('codex-win32-'+architecture)/relative,
                    modules/'@openai'/('codex-win32-'+architecture)/relative,
                    package/relative]
        for candidate in candidates:
            if candidate.is_file():return [str(candidate)]
        # Other npm layouts can still use the upstream wrapper.
        entry = package/'bin/codex.js'
        node = shutil.which('node')
        if not node or not entry.is_file():
            raise RuntimeError('Windows npm Codex 설치를 확인하세요. Node.js와 npm install -g @openai/codex가 필요합니다.')
        return [node, str(entry)]
    return [executable]


def require_login():
    cli = codex_command()
    if os.getenv('OPENAI_API_KEY') or os.getenv('CODEX_API_KEY'):
        raise RuntimeError('API 키 환경변수를 해제하세요. 이 앱은 ChatGPT 로그인만 사용합니다.')
    try:
        result = subprocess.run(cli + ['login', 'status'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        raise RuntimeError('Codex 로그인 상태 확인에 실패했습니다.') from None
    if result.returncode or 'chatgpt' not in (result.stdout + result.stderr).lower():
        raise RuntimeError('터미널에서 codex login을 실행해 ChatGPT 계정으로 로그인하세요.')


def stop_process(process):
    if process.poll() is not None:
        return
    if os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=15)
    else:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=10)


def run_codex(store, task, end):
    from office.browser_modes import mode,prepare
    from office.browser_timing import BrowserTiming
    selected=mode(task)
    diagnostic=json.loads(task.get('context_json') or '{}').get('host_operation')=='chrome_probe'
    timing=BrowserTiming()
    if task.get('action_json'):
        from office.actions import run_action
        result=run_action(store,task,end)
        result.setdefault('evidence',{}).setdefault('environment',{})['browser_mode']=selected
        result['evidence']['browser_timing']=timing.summary()
        return result
    require_login()
    env = dict(os.environ)
    for key in ('OPENAI_API_KEY', 'CODEX_API_KEY'):
        env.pop(key, None)
    logs = store.root / 'logs'
    logs.mkdir(exist_ok=True)
    # IDs come from the local database; log filenames are independent random temp names.
    with tempfile.TemporaryDirectory(prefix='office-draft-') as directory:
        output = Path(directory) / 'result.txt'
        workspace=Workspace(store,task)
        project=workspace.prepare()
        working_directory=str(workspace.work.resolve()) if project else str(Path(directory).resolve())
        writable=bool(project) and task.get('kind','single') != 'plan'
        try:
            preflight=check_workspace(working_directory) if writable else {'scope':'app_host','skipped':'read-only stage'}
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
            return {'status':'failed','error':'업무 시작 전 로컬 실행 점검 실패: '+safe_diagnostic(error),
                    'evidence':{'preflight':{'scope':'app_host','passed':False,'cwd':working_directory}}}
        if writable:
            store.message(task['id'],'host-preflight','system','status','로컬 사전 점검 통과: 파일 읽기·쓰기·Python 실행. Codex 내부 명령 실행은 별도 확인합니다.')
        inventory=sorted(files(workspace.work)) if project else []
        project_context={'registered':bool(project),'id':project['id'] if project else None,
                         'name':project['name'] if project else None,'source':project['path'] if project else None,
                         'cwd':working_directory,'file_count':len(inventory),'git_metadata_copied':False}
        stdout = logs / (str(uuid.uuid4()) + '.jsonl')
        stderr = stdout.with_suffix('.log')
        prompt = f'당신은 My Little Office의 {ROLES[task["role"]]} 직원입니다. 한국어로 검토할 결과물을 제출하세요. '
        prompt+='\n앱이 직접 확인한 프로젝트 연결 정보:\n'+json.dumps(project_context,ensure_ascii=False)
        prompt+='\n이 실행 단계: '+task.get('kind','single')+' · 이 단계의 작업 범위: '+('workspace-write' if writable else 'read-only')
        prompt+='\n명령의 작업 디렉터리는 위 cwd의 정확한 절대 경로를 사용하세요. 임의의 경로나 다른 운영체제 경로를 만들지 마세요. registered=true이고 file_count=0이면 등록된 빈 작업실이며 프로젝트 미연결이나 쓰기 금지라는 뜻이 아닙니다. .git은 사본에서 의도적으로 제외하므로 여기서 origin·브랜치가 없다고 원본 저장소 미연결로 판단하지 마세요. GitHub 계정 인증, 원본 저장소 연결, 작업 사본, 배포 action은 각각 구분하세요.\n'
        prompt += ('현재 프로젝트에서 필요한 문서·코드·홍보물을 실제 파일로 작성하고 수정하세요. 필요한 테스트·빌드·분석 명령을 실행하고 실패하면 수정하세요. 프로젝트 밖의 파일·인증 정보에는 접근하지 마세요. 실제로 실행한 증거와 남은 문제를 보고하세요.\n' if writable else '분석·계획·검토를 수행하세요. 현재 단계는 읽기 전용입니다. 실제로 실행하지 않은 일을 완료했다고 말하지 마세요.\n')
        if task.get('parent'):
            parent = store.get(task['parent'])
            history=store.messages(store.thread_id(parent['id']),limit=30)
            prompt+='\n같은 업무방의 최근 공개 대화(실행 증거·발화자 구분 참고):\n'+('\n'.join(event['actor']+': '+event['body'] for event in history if event['task_id']!=task['id']))[-12000:]+'\n'
            prompt += '\n이전 업무: ' + parent['prompt'] + '\n이전 결과: ' + parent['output'][-20000:] + '\n'
        knowledge,images=prepare_inputs(task,workspace.directory/'inputs')
        prompt += '\n아래 첨부 원본 경로는 대표가 제공한 읽기 전용 자료이며 프로젝트 밖이어도 열람 가능합니다. 수정·게시하지 마세요.\n'+knowledge
        planning=task.get('kind')=='plan'
        if planning:
            prompt+='\n현재 작업 사본 파일 목록(앱이 직접 확인, 최대 100개):\n'+json.dumps(inventory[:100],ensure_ascii=False)
            prompt+='\n이 단계에서는 명령 실행 도구를 사용하지 않습니다. 제공된 지시·프로필·자료 발췌·파일 목록·직원 제출물로 계획 또는 보고를 작성하세요. 추가 파일 열람·테스트는 담당 직원의 업무로 명시하세요. 실행하지 않은 검증을 완료했다고 하지 마세요.\n'
        prompt+='\n외부 조사: 공개 웹 검색과 공개 GitHub 원문을 실제로 열어 근거를 확인하세요. PC의 Codex에 연결된 MCP 도구·기존 gh 로그인은 해당 도구의 권한 범위에서 사용 가능합니다. ChatGPT 웹의 연결 계정이 자동 이전됐다고 가정하지 마세요. 비밀 값이나 인증 파일을 직접 읽거나 출력하지 마세요.\n'
        if writable:prompt+='\n제작·개발 지시는 제안으로 끝내지 말고 프로젝트 작업 사본에 검토 가능한 실제 결과물을 작성하세요. 사용자가 제안·설명만 요청한 경우는 예외입니다. 결과 파일 경로와 실제 검증 결과를 제출하세요.\n'
        if task.get("kind") not in ("plan", "report"):
            prompt += EXTERNAL_EXECUTION_POLICY
        browser_mode=selected
        if browser_mode=='ego':
            prompt+='\n브라우저 모드: ego. ego-browser 스킬이 실제로 설치되고 접근 허용된 경우에만 사용하세요. 다른 브라우저나 Playwright로 자동 전환하지 마세요. 동일한 Task Space를 재사용하고 화면이 바뀌지 않았다면 중복 스냅샷을 줄이세요. 설치된 공식 가이드가 지원하는 동작만 사용하세요. 없는 기능을 성공으로 표시하지 마세요. 비밀번호를 프롬프트나 도구 인자로 보내지 마세요.\n'
        else:
            prompt+='\n브라우저 모드: 기본. ego-browser를 사용하지 마세요. 연결된 기본 브라우저·커넥터·기존 Playwright 작업 등 허용된 기존 수단을 사용하세요.\n'
        prompt += instructions(store, task)
        prompt+='\n필수 산출물 파일: '+task.get('expected_json','[]')+' · 이 파일이 없거나 비어 있으면 검증 실패로 처리합니다.\n'
        prompt += '\n현재 업무:\n' + task['prompt']
        try:
            browser_args,browser_policy=prepare(task,codex_command(),working_directory,env,state_root=store.root)
        except Exception as error:
            return {'status':'blocked','error':'브라우저 모드 준비 실패: '+safe_diagnostic(error),
                    'evidence':{'environment':{'browser_mode':selected,'office_version':'0.20.1','stage':task.get('kind','single')},'browser_timing':timing.summary()}}
        args = codex_command() + ['exec', '--cd', working_directory, '--sandbox', 'workspace-write' if writable else 'read-only', '--skip-git-repo-check', '--json', '-o', str(output), '-']
        args[-1:-1]=['-c','forced_login_method="chatgpt"','-c','model_provider="openai"','-c','web_search="live"','-c','features.shell_tool='+('false' if planning else 'true')]
        windows_args,environment=windows_settings()
        args[-1:-1]=windows_args
        args[-1:-1]=browser_args
        environment.update(browser_mode=selected,browser_policy=browser_policy,sandbox='workspace-write' if writable else 'read-only',cwd=working_directory,executable=args[0],stage=task.get('kind','single'),connected_tools='local Codex user config',web_search='live',network=bool(project and project.get('network')),project=project_context,preflight=preflight)
        stdout.with_suffix('.environment.json').write_text(json.dumps(environment,ensure_ascii=False,indent=2),encoding='utf-8')
        stage_name={'plan':'총괄 배정(계획)','employee':'직원 실무','report':'총괄 최종 검토','single':'직접 지시'}.get(environment['stage'],environment['stage'])
        store.message(task['id'],'execution-environment','system','status','실행 단계: '+stage_name+' · 담당: '+ROLES[task['role']]+'\n프로젝트: '+str(project_context['name'] or '미지정')+' · 시작 파일 '+str(project_context['file_count'])+'개\n작업 범위: '+environment['sandbox']+' · Windows 샌드박스: '+environment['windows_sandbox']+'\n브라우저 모드: '+selected+'\n작업 폴더: '+working_directory)
        for image_path in images:
            args[-1:-1]=['--image',image_path]
        if writable:
            args[-1:-1] = ['-c','sandbox_workspace_write.network_access='+str(bool(project.get('network'))).lower()]
        kwargs = {'start_new_session': True} if os.name != 'nt' else {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP}
        with store.connect() as con:
            runtime_mode=store._get(con,'runtime_mode','exec')
        environment['configured_runtime']=runtime_mode
        if diagnostic:runtime_mode='appserver'
        environment['runtime']=runtime_mode
        environment['office_version']='0.20.1'
        if runtime_mode=='appserver' or diagnostic:
            from office.app_server import execute
            from types import SimpleNamespace
            try:
                result=execute(store,task,codex_command(),working_directory,env,prompt,writable,images,end,windows_args,browser_args=browser_args,timing=timing,browser_policy=browser_policy.get('chrome'),diagnostic=diagnostic)
            except Exception as error:
                from office.chrome_connection import latest,receipts
                return {'status':'blocked','error':'대화형 실행 중단: '+safe_diagnostic(error),
                        'evidence':{'browser_timing':timing.summary(),'environment':environment,'runtime_requests':store.runtime.list(active=False,task_id=task['id']),'runtime_rejections':store.runtime.rejections(task['id']),'browser_tools':latest(store,task['id']),'external_tools':receipts(latest(store,task['id']))}}
            environment['browser_tools']=result.get('browser_tools',{})
            if diagnostic:
                from office.chrome_connection import receipts
                environment.update(runtime_session=result['session'],runtime_thread=result['thread'],runtime_turn=result['turn'])
                probe_timing=timing.summary()
                probe_timing['browser_tool_calls']=int(bool(result.get('browser_tools',{}).get('tool_call_attempted')))
                status=result.get('browser_tools',{}).get('status')
                return {'status':'review' if status in ('CHROME_CONNECTED','STATE_CALL_OK') else 'blocked',
                        'output':result['text'],'error':'' if status in ('CHROME_CONNECTED','STATE_CALL_OK') else '기존 Chrome 연결 복구 진단: '+str(status),
                        'evidence':{'environment':environment,'browser_tools':result.get('browser_tools',{}),'browser_timing':probe_timing,'commands':[],'external_tools':receipts(result.get('browser_tools',{})),'changes':[],'artifacts':[]}}
            output.write_text(result['text'],encoding='utf-8')
            stdout.write_text('\n'.join(json.dumps(event,ensure_ascii=False) for event in result['events']),encoding='utf-8')
            stderr.write_text('',encoding='utf-8')
            process=SimpleNamespace(returncode=0)
            environment.update(runtime_session=result['session'],runtime_thread=result['thread'],runtime_turn=result['turn'])
        else:
            if browser_policy.get('chrome',{}).get('required'):
                from office.browser_modes import Inventory
                from office.chrome_connection import require_catalog
                check=None
                try:
                    check=Inventory(codex_command(),working_directory,env,browser_args)
                    thread=check.call('thread/start',{'cwd':working_directory,'sandbox':'workspace-write' if writable else 'read-only','approvalPolicy':'on-request','approvalsReviewer':'user'})
                    inventory,_=require_catalog(check.call,thread['thread']['id'],browser_policy['chrome'],store,task['id'])
                    environment['browser_tools']=inventory
                except Exception:
                    from office.chrome_connection import latest
                    return {'status':'blocked','error':'기존 실행기 브라우저 연결 확인 실패. 실제 도구 상태를 확인하고 승인 입력이 필요하면 대화형 실행기를 사용하세요.','evidence':{'environment':environment,'browser_tools':latest(store,task['id'])}}
                finally:
                    if check:check.close()
            with stdout.open('w', encoding='utf-8') as out, stderr.open('w', encoding='utf-8') as err:
                process = subprocess.Popen(args, cwd=working_directory, env=env, stdin=subprocess.PIPE, stdout=out, stderr=err, text=True, encoding='utf-8', **kwargs)
                live=LiveEvents(store,task,stdout,timing=timing)
                try:
                    try:
                        process.stdin.write(prompt)
                        process.stdin.close()
                    except (BrokenPipeError, OSError):
                        # A CLI that rejects arguments can exit before it consumes stdin.
                        # Continue to its exit status/stderr instead of hiding the cause.
                        pass
                    while process.poll() is None:
                        live.poll()
                        current = store.get(task['id'])
                        if current['status'] == 'cancel_requested' or time.time() >= end or stdout.stat().st_size + stderr.stat().st_size > 8_000_000:
                            stop_process(process)
                            return {'status': 'interrupted', 'error': '중단 요청 또는 작업 시간·로그 크기 제한으로 멈췄습니다.','evidence':{'environment':environment,'browser_timing':timing.summary()}}
                        time.sleep(.2)
                finally:
                    if process.poll() is None:
                        stop_process(process)
                    live.poll(final=True)
        events = []
        for line in stdout.read_text(encoding='utf-8', errors='replace').splitlines():
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    events.append(value)
            except ValueError:
                pass
        completed=any(e.get('type')=='turn.completed' for e in events)
        turn_failed=any(e.get('type')=='turn.failed' for e in events)
        text = output.read_text(encoding='utf-8', errors='replace') if output.exists() else ''
        if not text.strip():
            text=next((str(e['item'].get('text','')) for e in reversed(events)
                       if e.get('type')=='item.completed' and isinstance(e.get('item'),dict)
                       and e['item'].get('type')=='agent_message' and e['item'].get('phase')!='commentary'),'')
        stderr_text=stderr.read_text(encoding='utf-8',errors='replace')
        diagnostics=stderr_text+json.dumps(events,ensure_ascii=False)
        denial_events=[e for e in events if e.get('type') in ('error','turn.failed') or
                       isinstance(e.get('item'),dict) and e['item'].get('type')=='command_execution']
        policy_block=bool(re.search(r'blocked by policy|rejected:.*policy|approval required|denied by.*policy',stderr_text+json.dumps(denial_events),re.I))
        from office.runtime_requests import browser_access_denied
        browser_denied=any(e.get('type')=='item.completed' and isinstance(e.get('item'),dict) and e['item'].get('type')=='mcp_tool_call' and
                           browser_access_denied(e['item']) for e in events)
        launch_failure=bool(re.search(r'CreateProcessWithLogonW failed|CreateProcess.*(?:failed|Rejected)|Failed to create parent directories',json.dumps(denial_events,ensure_ascii=False),re.I))
        failed=browser_denied or launch_failure or bool(process.returncode) or turn_failed or not completed or not text.strip() or policy_block
        if failed:
            quota = re.search(r'usage.limit|rate.limit|quota.exceeded', diagnostics, re.I)
            event_errors=[e.get('message') or e.get('error') for e in events if e.get('type') in ('error','turn.failed')]
            reason=stderr_text.strip() or json.dumps(event_errors or denial_events,ensure_ascii=False)
            category=('브라우저 도구 접근 승인이 거절됐습니다. 보고서 작성으로 원래 업무를 완료하지 않습니다.' if browser_denied else
                      'Codex 내부 명령 실행에 실패했습니다. 작업 경로·실행 환경 복구가 필요합니다.' if launch_failure else
                      'Codex 명령이 실행 정책에 차단됐습니다. 로그인 오류가 아닙니다. 차단된 작업은 수행하지 않았습니다.' if policy_block else
                      'Codex 프로세스가 오류로 종료됐습니다.' if process.returncode else
                      'Codex 작업 턴이 실패했습니다.' if turn_failed else
                      'Codex 완료 이벤트를 받지 못했습니다.' if not completed else
                      'Codex가 제출한 최종 결과가 없습니다.')
            error='Codex 사용 한도 대기. 복구 시각은 미확인입니다.' if quota else category+' (프로세스 종료 코드 '+str(process.returncode)+')\n'+safe_diagnostic(reason)[-1800:]+'\n진단 파일: '+str(stderr)
            # Keep partial output for review; never turn a policy denial into success.
            safe_text=safe_diagnostic(text)
            return {'status':'quota_wait' if quota else 'blocked' if browser_denied else 'failed','error':error,'output':safe_text,'evidence':{'environment':environment,'browser_timing':timing.summary()}}
        if re.search(r'sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9_]{20,}|-----BEGIN .*PRIVATE KEY-----', text):
            return {'status': 'failed', 'error': '비밀 키로 의심되는 결과의 표시를 차단했습니다. PC 로그를 확인하세요.'}
        usage = next((e.get('usage', {}) for e in reversed(events) if e.get('type') == 'turn.completed'), {})
        commands=[{k:e['item'].get(k) for k in ('command','status','exit_code','aggregated_output')} for e in events if e.get('type')=='item.completed' and isinstance(e.get('item'),dict) and e['item'].get('type')=='command_execution']
        for command in commands:
            if isinstance(command.get('aggregated_output'),str):command['aggregated_output']=command['aggregated_output'][-4000:]
        external=[]
        for event in events:
            item=event.get('item',{})
            if event.get('type')!='item.completed' or not isinstance(item,dict):continue
            if item.get('type')=='web_search':external.append({'type':'web_search','action':safe_diagnostic(json.dumps(item.get('action',{}),ensure_ascii=False))})
            elif item.get('type')=='mcp_tool_call':external.append({key:item.get(key) for key in ('type','server','tool','status')})
        evidence={'browser_timing':timing.summary(),'environment':environment,'commands':commands[-40:],'external_tools':external[-40:],'changes':workspace.changes() if project else []}
        from office.smoke import PREFIX, verify
        if task['prompt'].startswith(PREFIX):
            acceptance=verify(workspace.work,commands)
            evidence['acceptance']=acceptance
            if not acceptance['passed']:
                return {'status':'failed','output':text,'evidence':evidence,
                        'error':'실행·분석 검증 실패: '+acceptance['reason']}
        from office.artifacts import inspect_artifacts
        artifacts=inspect_artifacts(workspace.work,json.loads(task.get('expected_json','[]'))) if project else []
        evidence['artifacts']=artifacts
        if any(not artifact['present'] for artifact in artifacts):
            return {'status':'failed','output':text,'evidence':evidence,'error':'필수 산출물 파일이 없거나 비어 있습니다. 후속 업무를 진행하지 않습니다.'}
        checks={} 
        for command in commands:
            match=re.search(r'pytest|unittest|vitest|jest|npm (?:run )?test|npm run build|cargo test|go test|tsc',str(command.get('command','')))
            if match and command.get('exit_code') is not None:checks[match.group(0)]=command['exit_code']
        failed_checks=any(code!=0 for code in checks.values())
        return {'status':'failed' if failed_checks else 'review', 'output':text, 'usage':usage,'evidence':evidence,
                'error':'마지막 테스트·빌드 실행이 실패했습니다. 후속 배포를 진행하지 않습니다.' if failed_checks else ''}


class Worker:
    def __init__(self, store, runner=None, start=True):
        self.store, self.runner = store, runner or run_codex
        self.presence_server=None
        # Same lock as the legacy polling worker; cannot run both simultaneously.
        self.lock = (store.root / 'worker.lock').open('a+b')
        try:
            if os.name == 'nt':
                import msvcrt
                self.lock.seek(0); self.lock.write(b'0'); self.lock.flush(); self.lock.seek(0)
                msvcrt.locking(self.lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.lock.close()
            raise RuntimeError('다른 출근 실행기가 사용 중입니다. 기존 실행기를 종료하세요.') from None
        store.recover()
        self.shutdown = threading.Event()
        if start:
            self.thread = threading.Thread(target=self.loop, daemon=True, name='office-worker')
            self.thread.start()

    def step(self):
        status, _ = self.store.status()
        if not status.get('on_duty'):
            return
        self.store.tick_schedules()
        task = self.store.claim()
        if not task:
            return
        self.store.activity(task['id'],'talking' if task['kind']=='plan' else 'syncing' if task.get('action_json') else 'executing','총괄 계획 시작' if task['kind']=='plan' else '실행 시작')
        pulse_stop=threading.Event()
        def pulse():
            while not pulse_stop.wait(5):
                try:self.store.heartbeat(task['id'])
                except Exception:pass
        pulse_thread=threading.Thread(target=pulse,daemon=True,name='office-heartbeat');pulse_thread.start()
        try:
            result = self.runner(self.store, task, time.time() + 1200)
        except Exception as error:
            result = exception_result(self.store,error)
        finally:
            pulse_stop.set();pulse_thread.join(timeout=1)
        self.store.finish(task['id'], result)
        if self.store.get(task['id'])['status'] in ('failed', 'quota_wait'):
            self.store.pause('실행 오류·한도 대기. 확인 후 출근 버튼으로 재개하세요.')

    def loop(self):
        while not self.shutdown.wait(.5):
            try:
                self.step()
            except Exception:
                self.store.pause('작업 저장 오류. PC 저장 공간과 로그를 확인하세요.')

    def start_presence(self,port=8787):
        if self.presence_server:return self.presence_server.url
        from office.presence import PresenceServer
        self.presence_server=PresenceServer(self.store,port)
        return self.presence_server.url

    def stop_presence(self):
        if self.presence_server:self.presence_server.close();self.presence_server=None

    def close(self):
        if self.lock.closed:
            return
        self.stop_presence()
        self.store.pause('앱 종료')
        self.shutdown.set()
        if hasattr(self, 'thread'):
            self.thread.join(timeout=45)
            if self.thread.is_alive():
                return  # Keep the process lock until the worker really stops.
        self.lock.close()
