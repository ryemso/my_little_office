"""Offline app-server protocol fixture. No model, account or external site."""
import json
import sys

mode=sys.argv[1] if len(sys.argv)>1 else 'accept'
remaining=set()


def emit(value):
    print(json.dumps(value),flush=True)


for line in sys.stdin:
    msg=json.loads(line);method=msg.get('method');identifier=msg.get('id')
    if method=='initialize':emit({'id':identifier,'result':{'userAgent':'office-fixture'}})
    elif method=='thread/start':emit({'id':identifier,'result':{'thread':{'id':'fixture-thread'},'approvalPolicy':'on-request','approvalsReviewer':'user'}})
    elif method=='turn/start':
        emit({'method':'turn/started','params':{'threadId':'fixture-thread','turn':{'id':'fixture-turn'}}})
        emit({'id':identifier,'result':{'turn':{'id':'fixture-turn','status':'inProgress'}}})
        if mode=='disconnect':sys.exit(0)
        for value in ('server-a','server-b'):
            remaining.add(value)
            emit({'id':value,'method':'item/commandExecution/requestApproval','params':{'threadId':'fixture-thread','turnId':'fixture-turn','itemId':value,'reason':'오프라인 모형의 승인 왕복 확인','command':'python --version','cwd':'/fixture'}})
    elif 'result' in msg and identifier in remaining:
        if msg['result'].get('decision')!='accept':mode='declined'
        remaining.remove(identifier)
        emit({'method':'serverRequest/resolved','params':{'threadId':'fixture-thread','requestId':identifier}})
        if not remaining:
            emit({'method':'item/completed','params':{'threadId':'fixture-thread','item':{'id':'message','type':'agentMessage','phase':'final_answer','text':'승인 왕복 모형 완료' if mode!='declined' else '거절됨'}}})
            emit({'method':'turn/completed','params':{'threadId':'fixture-thread','turn':{'id':'fixture-turn','status':'completed'}}})
    elif method=='turn/interrupt':break
