"""Real Codex + Google Chrome DevTools MCP catalog contract, no browser actions.

Uses an empty temporary Codex home and offline model URL; no inference or account.
"""
import json
import errno
import shutil
from contextlib import contextmanager
import os
from pathlib import Path
import tempfile
import time
from office.app_server import Transport,AppServerRun
from office.browser_tools import prepare,catalog
from office.store import Store


@contextmanager
def diagnostic_directory():
    directory=tempfile.mkdtemp(prefix='office-devtools-',dir=Path.cwd())
    try:yield directory
    finally:
        # npm/Codex children may finish local cache metadata just after transport
        # shutdown. Retry ENOTEMPTY only; never suppress a persistent cleanup error.
        for attempt in range(10):
            try:
                shutil.rmtree(directory)
                break
            except FileNotFoundError:break
            except OSError as error:
                if error.errno!=errno.ENOTEMPTY or attempt==9:raise
                time.sleep(.1)


def probe(codex):
    with diagnostic_directory() as directory:
        root=Path(directory);home=root/'home';home.mkdir();work=root/'work';work.mkdir()
        config='[mcp_servers.chrome-devtools]\ncommand="npx"\nargs=["-y","chrome-devtools-mcp@1.12.0","--autoConnect","--no-usage-statistics"]\n'
        (home/'config.toml').write_text(config)
        env={k:v for k,v in os.environ.items() if k in ('PATH','SystemRoot','WINDIR','TEMP','TMP','TMPDIR','LANG','LC_ALL')}
        env.update(CODEX_HOME=str(home),HOME=str(root),USERPROFILE=str(root))
        task={'prompt':'chrome-devtools 탭 목록 확인'}
        args,enabled=prepare([codex],str(work),env,task);assert enabled
        offline=['-c','model="fixture"','-c','model_provider="fixture"','-c','model_providers.fixture.name="Offline"','-c','model_providers.fixture.base_url="http://127.0.0.1:9/v1"','-c','model_providers.fixture.wire_api="responses"']
        store=Store(root/'state');store.clock_in();store.submit('dev',task['prompt']);task=store.claim()
        transport=Transport([codex,'app-server','--listen','stdio://',*offline,*args],str(work),env)
        runner=AppServerRun(store,task,transport,time.time()+100)
        try:
            runner.rpc('initialize',{'clientInfo':{'name':'my_little_office','version':'0.19.5'},'capabilities':{'experimentalApi':True}})
            transport.send({'method':'initialized'})
            result=runner.rpc('thread/start',{'cwd':str(work),'sandbox':'read-only','approvalPolicy':'on-request','approvalsReviewer':'user'},timeout=70)
            runner.thread=result['thread']['id'];store.runtime.bind(runner.session,runner.thread)
            evidence,_=catalog(runner.rpc,runner.thread)
            assert 'list_pages' in evidence['tool_names']
            assert 'take_snapshot' in evidence['tool_names']
            assert (home/'config.toml').read_text().startswith(config)
            print(json.dumps({'real_codex':'0.163.0','real_mcp':'chrome-devtools-mcp@1.12.0','tool_count':evidence['tool_count'],'thread_catalog_verified':True,'browser_actions':0,'inference_executed':False}))
        finally:
            store.runtime.end(runner.session,'disconnected');transport.close()

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--codex',required=True)
    probe(parser.parse_args().codex)
