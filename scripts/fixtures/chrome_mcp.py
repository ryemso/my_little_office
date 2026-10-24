"""Offline MCP browser fixture, NOT a real Chrome or login session."""
import json
import sys

for line in sys.stdin:
    msg=json.loads(line);method=msg.get('method');identifier=msg.get('id');params=msg.get('params') or {}
    if method=='initialize':result={'protocolVersion':params.get('protocolVersion','2024-11-05'),'capabilities':{'tools':{}},'serverInfo':{'name':'office_chrome_fixture','version':'1'}}
    elif method=='tools/list':result={'tools':[{'name':'js','description':'Offline fixture state probe only','inputSchema':{'type':'object','properties':{'code':{'type':'string'},'title':{'type':'string'}},'required':['code']}}]}
    elif method=='tools/call':
        ok=params.get('name')=='js' and params.get('arguments',{}).get('code')=='await cua.getState();'
        result={'isError':not ok,'content':[{'type':'text','text':json.dumps({'browsers':[{'id':'fixture-chrome','name':'Chrome','type':'extension','url':'https://private.example/?token=fixture-secret'}]}) if ok else 'unsupported fixture call'}]}
    elif identifier is not None:result={}
    else:continue
    print(json.dumps({'jsonrpc':'2.0','id':identifier,'result':result}),flush=True)
