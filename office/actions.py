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
    workspace=Workspace(store,task);project=workspace.prepare()
    action=json.loads(task['action_json'])
    if not action['automatic'] and workspace.fingerprint()!=task.get('approval_hash'):
        return {'status':'failed','error':'승인 이후 작업 파일이 바뀌었습니다. 변경을 확인한 뒤 다시 지시하세요.'}
    store.message(task['id'],'action-start',task['role'],'status','연결 작업을 실행합니다.\n작업: '+action['name']+'\n대상: '+action['target'])
    argv=json.loads(action['argv'])
    if argv[0]=='office:naver':
        if not project or not project.get('network'):raise ValueError('프로젝트 네트워크 사용을 허용해야 네이버에 연결할 수 있습니다.')
        from office.naver import execute
        return execute(store,task,workspace,argv,end)
    if argv[0]=='office:github':
        if len(argv)!=2:raise ValueError('GitHub 연결 인자 오류')
        if not project or not project.get('network'):raise ValueError('프로젝트 네트워크 사용을 허용해야 GitHub에 반영할 수 있습니다.')
        from office.github_publish import publish_workspace
        receipt=publish_workspace(workspace,argv[1],task['id'],end,
                                  cancelled=lambda:store.get(task['id'])['status']=='cancel_requested')
        return {'status':'review','output':'GitHub 원격 커밋 확인 완료\n'+receipt['url']+'\n브랜치: '+receipt['branch'],
                'error':'','evidence':{'action':{'type':'github_branch_publish',**receipt},'changes':workspace.changes()}}
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
