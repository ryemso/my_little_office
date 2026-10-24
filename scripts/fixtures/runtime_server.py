"""Offline app-server protocol fixture. No model, account or external site."""
import json
import sys

mode=sys.argv[1] if len(sys.argv)>1 else 'accept'
remaining=set()
probe_id=None


def emit(value):
    print(json.dumps(value),flush=True)


for line in sys.stdin:
    msg=json.loads(line);method=msg.get('method');identifier=msg.get('id')
    if method=='initialize':emit({'id':identifier,'result':{'userAgent':'office-fixture'}})
    elif method=='thread/start':emit({'id':identifier,'result':{'thread':{'id':'fixture-thread'},'approvalPolicy':'on-request','approvalsReviewer':'user'}})
    elif method=='mcpServerStatus/list':
        server='node_repl' if mode=='chrome-node-only' else 'cua_repl'
        data=[] if mode=='chrome-missing' else [{'name':server,'runtimeStatus':'connected','tools':{'js':{'name':'js','inputSchema':{'type':'object','properties':{'code':{'type':'string'}},'required':['code']}}}}]
        emit({'id':identifier,'result':{'data':data,'nextCursor':None}})
    elif method=='mcpServer/tool/call':
        if mode=='chrome-approval':
            probe_id=identifier;remaining.add('probe-approval')
            emit({'id':'probe-approval','method':'mcpServer/elicitation/request','params':{'threadId':'fixture-thread','mode':'form','message':'Allow Chrome connection diagnostic?','requestedSchema':{'type':'object','properties':{}}}})
        else:
            emit({'id':identifier,'result':{'content':[{'type':'text','text':json.dumps({'browsers':[{'id':'fixture','name':'Chrome','url':'https://private.example/?token=fixture-secret'}]})}]}})
    elif method=='turn/start':
        emit({'method':'turn/started','params':{'threadId':'fixture-thread','turn':{'id':'fixture-turn'}}})
        emit({'id':identifier,'result':{'turn':{'id':'fixture-turn','status':'inProgress'}}})
        if mode=='disconnect':sys.exit(0)
        for value in ('server-a','server-b'):
            remaining.add(value)
            emit({'id':value,'method':'item/commandExecution/requestApproval','params':{'threadId':'fixture-thread','turnId':'fixture-turn','itemId':value,'reason':'오프라인 모형의 승인 왕복 확인','command':'python --version','cwd':'/fixture'}})
    elif 'result' in msg and identifier in remaining:
        if identifier=='probe-approval':
            remaining.remove(identifier)
            emit({'method':'serverRequest/resolved','params':{'threadId':'fixture-thread','requestId':identifier}})
            emit({'id':probe_id,'result':{'isError':msg['result'].get('action')!='accept','content':[]}})
            continue
        if msg['result'].get('decision')!='accept':mode='declined'
        remaining.remove(identifier)
        emit({'method':'serverRequest/resolved','params':{'threadId':'fixture-thread','requestId':identifier}})
        if not remaining:
            emit({'method':'item/completed','params':{'threadId':'fixture-thread','item':{'id':'message','type':'agentMessage','phase':'final_answer','text':'승인 왕복 모형 완료' if mode!='declined' else '거절됨'}}})
            emit({'method':'turn/completed','params':{'threadId':'fixture-thread','turn':{'id':'fixture-turn','status':'completed'}}})
    elif method=='turn/interrupt':break
