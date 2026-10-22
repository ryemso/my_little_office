"""Send explicit local activity to My Little Office, not task content or credentials."""
import argparse
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8787');parser.add_argument('--state',default='idle');parser.add_argument('--state-file');parser.add_argument('--once',action='store_true');args=parser.parse_args()
    parsed=urlparse(args.url)
    if parsed.scheme!='http' or parsed.hostname not in ('127.0.0.1','localhost') or parsed.username or parsed.password or parsed.path not in ('','/') or parsed.query or parsed.fragment:parser.error('로컬 사무실 주소만 지원합니다.')
    token=os.getenv('OFFICE_AGENT_KEY','')
    if not token:parser.error('OFFICE_AGENT_KEY 환경변수에 발급한 키를 지정하세요.')
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*a,**k):return None
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    def send(endpoint,value):
        request=urllib.request.Request(args.url.rstrip('/')+endpoint,data=json.dumps(value).encode(),headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'},method='POST')
        with opener.open(request,timeout=5) as response:return json.load(response)
    try:
        while True:
            payload={'state':args.state}
            if args.state_file:
                path=Path(args.state_file)
                if path.stat().st_size>4096:raise ValueError('상태 파일 최대 4KB')
                value=json.loads(path.read_text(encoding='utf-8'))
                payload={'state':value['state'],'detail':value.get('detail','')}
            send('/agent-push',payload)
            if args.once:break
            time.sleep(15)
    except KeyboardInterrupt:
        try:send('/leave-agent',{'state':'idle'})
        except (OSError,ValueError):pass
    except (OSError,ValueError,KeyError):
        raise SystemExit('상태 전송 실패. 서버·키·상태 파일을 확인하세요. 자동으로 계속 재시도하지 않습니다.') from None

if __name__=='__main__':main()
