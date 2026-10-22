"""Publish reviewed workspace deltas to a dedicated GitHub branch via local gh."""
import base64
import hashlib
import json
import re
import shutil
import subprocess
import time
from office.workspaces import target


def repository(value):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',value) or '..' in value:
        raise ValueError('저장소는 owner/repository 형식이어야 합니다.')
    return value


def publish_workspace(workspace, repo, task_id, end, cancelled=lambda:False, api=None):
    repo=repository(repo)
    gh=shutil.which('gh') if api is None else None
    if api is None and not gh:raise ValueError('이 PC에 GitHub CLI(gh)가 필요합니다. 설치 후 gh auth login으로 연결하세요.')
    def request(method, path, body=None):
        if cancelled() or time.time()>=end:raise RuntimeError('GitHub 반영 중단. 생성된 브랜치 여부는 저장소에서 확인하세요.')
        if api is not None:return api(method,path,body)
        args=[gh,'api','--hostname','github.com','--method',method,'repos/'+repo+'/'+path]
        if body is not None:args+=['--input','-']
        result=subprocess.run(args,input=json.dumps(body) if body is not None else None,
                              capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=min(30,max(1,end-time.time())))
        if result.returncode:
            from office.engine import safe_diagnostic
            raise RuntimeError('GitHub API 실패: '+safe_diagnostic(result.stderr)[-1000:])
        return json.loads(result.stdout)
    def remote_at(tree,name):
        parts=name.split('/')
        for index,part in enumerate(parts):
            response=request('GET','git/trees/'+tree)
            if response.get('truncated'):raise ValueError('원격 파일 목록이 잘렸습니다. 반영을 중단합니다.')
            item=next((x for x in response['tree'] if x['path']==part),None)
            if item is None:return None
            if index==len(parts)-1:return item
            if item['type']!='tree':raise ValueError('원격 경로 충돌: '+name)
            tree=item['sha']
    def verify_existing(tree,delta):
        for change in delta:
            name=change['path'];remote=remote_at(tree,name);local=target(workspace.work,name)
            if not local.exists():
                if remote is not None:raise ValueError('기존 브랜치 삭제 결과 불일치: '+name)
                continue
            if not remote or remote['type']!='blob':raise ValueError('기존 브랜치 결과 불일치: '+name)
            blob=request('GET','git/blobs/'+remote['sha'])
            if base64.b64decode(blob['content'])!=local.read_bytes():raise ValueError('기존 브랜치 파일 불일치: '+name)
    delta=workspace.changes()
    if not delta:raise ValueError('GitHub에 반영할 작업 사본 변경이 없습니다.')
    baseline=json.loads(workspace.meta.read_text(encoding='utf-8'))['files']
    fingerprint=workspace.fingerprint()
    branch='office/'+hashlib.sha256(task_id.encode()).hexdigest()[:24]
    message='My Little Office reviewed output\n\nOffice-Fingerprint: '+fingerprint
    info=request('GET','')
    # The collection endpoint avoids interpreting authentication failures as 404.
    refs=request('GET','git/matching-refs/heads/'+branch)
    if refs:
        existing=next((r for r in refs if r['ref']=='refs/heads/'+branch),None)
        if existing:
            commit=request('GET','git/commits/'+existing['object']['sha'])
            if commit['message']!=message:raise ValueError('같은 업무 브랜치에 다른 결과가 있습니다. 새 업무로 제출하세요.')
            verify_existing(commit['tree']['sha'],delta)
            return {'repository':repo,'branch':branch,'commit':existing['object']['sha'],
                    'url':'https://github.com/'+repo+'/commit/'+existing['object']['sha'],'verified':True,'reused':True}
    head=request('GET','git/ref/heads/'+info['default_branch'])['object']['sha']
    base=request('GET','git/commits/'+head)['tree']['sha']
    entries=[]
    # Check remote contents before uploading any blobs; never silently replace changed remote files.
    for change in delta:
        name=change['path']
        remote=remote_at(base,name)
        original=baseline.get(name)
        if remote:
            if remote['type']!='blob' or remote['mode']=='120000':raise ValueError('원격 파일 형식 충돌: '+name)
            blob=request('GET','git/blobs/'+remote['sha'])
            digest=hashlib.sha256(base64.b64decode(blob['content'])).hexdigest()
            if digest!=original:raise ValueError('원격 변경과 충돌: '+name)
        elif original is not None:raise ValueError('원격에 원본 파일이 없습니다: '+name)
        entries.append({'path':name,'mode':remote['mode'] if remote else '100644','type':'blob','sha':None})
    for entry in entries:
        path=target(workspace.work,entry['path'])
        if path.exists():
            blob=request('POST','git/blobs',{'encoding':'base64','content':base64.b64encode(path.read_bytes()).decode('ascii')})
            entry['sha']=blob['sha']
    if workspace.fingerprint()!=fingerprint:raise ValueError('업로드 도중 작업 사본이 변경됐습니다. 다시 검토하세요.')
    tree=request('POST','git/trees',{'base_tree':base,'tree':entries})['sha']
    commit=request('POST','git/commits',{'message':message,'tree':tree,'parents':[head]})['sha']
    request('POST','git/refs',{'ref':'refs/heads/'+branch,'sha':commit})
    actual=request('GET','git/ref/heads/'+branch)['object']['sha']
    if actual!=commit:raise RuntimeError('GitHub 원격 커밋 검증 실패')
    return {'repository':repo,'branch':branch,'commit':commit,'base_commit':head,
            'url':'https://github.com/'+repo+'/commit/'+commit,'verified':True,'reused':False}
