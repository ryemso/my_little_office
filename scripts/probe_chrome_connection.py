"""Real Codex + offline MCP: restore existing CUA cwd and verify live tools.

No model inference, user authentication, Chrome install or real page access.
"""
import json
import os
from pathlib import Path
import tempfile
from office.browser_modes import Inventory,prepare
from office.chrome_connection import inspect_catalog,state_call


def probe(command):
    with tempfile.TemporaryDirectory(prefix='office-chrome-contract-',dir=Path.cwd()) as folder:
        root=Path(folder);home=root/'codex';home.mkdir();work=root/'work';work.mkdir()
        fixture=Path(__file__).resolve().parent/'fixtures/chrome_mcp.py'
        bad_cwd=root/'plugins/cache/old-version/missing'
        (home/'config.toml').write_text('[mcp_servers.cua_repl]\ncommand='+json.dumps(os.sys.executable)+'\nargs=['+json.dumps(str(fixture))+']\ncwd='+json.dumps(str(bad_cwd))+'\nenabled=true\n')
        original=(home/'config.toml').read_bytes()
        env={key:value for key,value in os.environ.items() if key in ('PATH','SystemRoot','WINDIR','TEMP','TMP','TMPDIR','LANG','LC_ALL')}
        env.update(CODEX_HOME=str(home),HOME=str(root),USERPROFILE=str(root))
        offline=['-c','features.apps=false','-c','model="fixture-model"','-c','model_provider="fixture"',
                 '-c','model_providers.fixture.name="Offline fixture"',
                 '-c','model_providers.fixture.base_url="http://127.0.0.1:9/v1"',
                 '-c','model_providers.fixture.wire_api="responses"']
        args,policy=prepare({'prompt':'Chrome 탭 목록을 확인하세요'},command,str(work),env,base_args=offline,state_root=root)
        assert policy['chrome']['repairs']==[{'provider':'cua_repl','change':'stable_cwd'}]
        inv=Inventory(command,str(work),env,[*offline,*args])
        try:
            thread=inv.call('thread/start',{'cwd':str(work),'sandbox':'workspace-write','approvalPolicy':'on-request','approvalsReviewer':'user'})
            result,tool=inspect_catalog(inv.call,thread['thread']['id'],'cua_repl')
            assert result['status']=='TOOLS_READY',result
            result=state_call(inv.call,thread['thread']['id'],result,tool)
            assert result['status']=='CHROME_CONNECTED',result
            assert 'fixture-secret' not in json.dumps(result)
        finally:inv.close()
        assert (home/'config.toml').read_bytes()==original
        return {'inference_executed':False,'real_chrome_used':False,'fixture_state_call_verified':result['tool_call_verified'],
                'live_thread_catalog_verified':True,'broken_cwd_repaired_per_invocation':True,'global_config_unchanged':True}


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--codex',required=True);args=parser.parse_args()
    print(json.dumps(probe([args.codex])))
