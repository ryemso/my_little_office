"""Check real installed CLI schema and handshake without model inference."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from office.app_server import Transport


def probe(command, cwd):
    with tempfile.TemporaryDirectory(prefix='office-protocol-') as directory:
        result=subprocess.run(command+['app-server','generate-json-schema','--out',directory],capture_output=True,timeout=20)
        if result.returncode:raise RuntimeError('설치된 CLI의 프로토콜 스키마 생성 실패')
        root=Path(directory)
        required=['McpServerElicitationRequestParams.json','CommandExecutionRequestApprovalResponse.json','ServerRequestResolvedNotification.json']
        digest=hashlib.sha256()
        supported=True
        for name in required:
            path=next(root.rglob(name),None)
            if path is None:supported=False;continue
            digest.update(path.read_bytes())
        params=next(root.rglob('ThreadStartParams.json'),None)
        supported=supported and params is not None and 'approvalsReviewer' in json.loads(params.read_text()).get('properties',{})
        schema_digest=digest.hexdigest()
    transport=Transport(command+['app-server','--listen','stdio://'],cwd,dict(os.environ))
    try:
        transport.send({'id':'probe-init','method':'initialize','params':{'clientInfo':{'name':'my_little_office_probe','title':'Office connection diagnostic','version':'0.19'}}})
        end=time.monotonic()+8;handshake=False
        while time.monotonic()<end:
            message=transport.receive()
            if not message:continue
            if message.get('id')=='probe-init':
                handshake='result' in message;break
            if message.get('transport_error') or message.get('transport_closed'):break
        if handshake:transport.send({'method':'initialized'})
        return {'handshake':handshake,'schema_supported':supported,'schema_digest':schema_digest,
                'inference_executed':False,'browser_origin_verified':False}
    finally:transport.close()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--codex',required=True)
    args=parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='office-probe-home-') as directory:
        # This independent transport test uses an empty home, never a real account.
        os.environ['CODEX_HOME']=directory
        result=probe([args.codex],directory)
        assert result['handshake'] and result['schema_supported'],result
        print(json.dumps(result))
