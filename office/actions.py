"""Execute only owner-registered commands with a concrete target and receipt."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import uuid
from office.workspaces import Workspace


def executable(argv):
    program=shutil.which(argv[0])
    if not program:raise ValueError('등록된 실행 프로그램을 찾지 못했습니다: '+argv[0])
    if Path(program).suffix.lower() in ('.cmd','.bat'):
        if Path(program).stem.lower() not in ('npm','npx'):raise ValueError('Windows 배치 대신 실제 실행 파일과 인자를 등록하세요.')
        node=shutil.which('node')
        script=Path(program).parent/'node_modules/npm/bin'/('npm-cli.js' if Path(program).stem.lower()=='npm' else 'npx-cli.js')
        if not node or not script.is_file():raise ValueError('Node.js/npm 설치 경로를 확인하세요.')
        return [node,str(script),*argv[1:]]
    return [program,*argv[1:]]


def run_action(store,task,end):
    from office.engine import stop_process
    workspace=Workspace(store,task);workspace.prepare()
    action=json.loads(task['action_json'])
    if not action['automatic'] and workspace.fingerprint()!=task.get('approval_hash'):
        return {'status':'failed','error':'승인 이후 작업 파일이 바뀌었습니다. 변경을 확인한 뒤 다시 지시하세요.'}
    argv=json.loads(action['argv'])
    args=executable(argv)
    env=dict(os.environ)
    for key in ('OPENAI_API_KEY','CODEX_API_KEY'):env.pop(key,None)
    logdir=store.root/'logs';logdir.mkdir(exist_ok=True)
    log=logdir/(str(uuid.uuid4())+'.action.log')
    kwargs={'start_new_session':True} if os.name!='nt' else {'creationflags':subprocess.CREATE_NEW_PROCESS_GROUP}
    with log.open('w',encoding='utf-8') as stream:
        process=subprocess.Popen(args,cwd=workspace.work,env=env,stdout=stream,stderr=subprocess.STDOUT,**kwargs)
        try:
            while process.poll() is None:
                if store.get(task['id'])['status']=='cancel_requested' or time.time()>=end or log.stat().st_size>8_000_000:
                    stop_process(process)
                    return {'status':'interrupted','error':'연결 작업을 중단했습니다. 외부 서비스에서 이미 진행된 결과는 대상 서비스에서 확인하세요.'}
                time.sleep(.2)
        finally:
            if process.poll() is None:stop_process(process)
    receipt={'type':'registered_action','name':action['name'],'target':action['target'],'argv':argv,'exit_code':process.returncode}
    output=f"연결 작업: {action['name']}\n대상: {action['target']}\n프로세스 종료 코드: {process.returncode}\n"+log.read_text(encoding='utf-8',errors='replace')[-5000:]
    return {'status':'review' if process.returncode==0 else 'failed','output':output,'error':'' if process.returncode==0 else '연결 작업 실행 실패','evidence':{'action':receipt,'changes':workspace.changes()}}
