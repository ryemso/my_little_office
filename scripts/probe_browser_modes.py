"""Real pinned Codex config/catalog test, offline, without login or inference."""
import json
import os
from pathlib import Path
import tempfile
from office.browser_modes import Inventory,overrides


def probe(command):
    with tempfile.TemporaryDirectory(prefix='office-mode-contract-') as folder:
        root=Path(folder);home=root/'codex';home.mkdir();work=root/'work';work.mkdir()
        skill=home/'skills/ego-browser';skill.mkdir(parents=True)
        (skill/'SKILL.md').write_text('---\nname: ego-browser\ndescription: Offline fixture; no actual browser.\n---\nFixture.\n')
        (home/'config.toml').write_text('[mcp_servers.ego_fixture]\ncommand="'+os.sys.executable.replace('\\','\\\\')+'"\nargs=["-c","raise SystemExit(1)"]\nenabled=true\n')
        env=dict(os.environ,CODEX_HOME=str(home))
        initial=Inventory(command,str(work),env)
        try:config,skills=initial.read(str(work))
        finally:initial.close()
        assert any(s['name']=='ego-browser' and s['enabled'] for s in skills)
        results={}
        for mode in ('standard','ego'):
            args,_,servers=overrides(config,skills,mode)
            inv=Inventory(command,str(work),env,args)
            try:
                effective,listing=inv.read(str(work))
                enabled=[s['enabled'] for s in listing if s['name']=='ego-browser']
                assert enabled==[mode=='ego'],(mode,enabled,args)
                assert effective['mcp_servers']['ego_fixture']['enabled']==(mode=='ego')
                results[mode]={'skill_enabled':enabled[0],'mcp_enabled':effective['mcp_servers']['ego_fixture']['enabled']}
            finally:inv.close()
        return {'version':'0.163.0','inference_executed':False,'real_browser_used':False,'catalog_contract':results,'host_shell_isolated':False}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--codex',required=True);args=p.parse_args()
    print(json.dumps(probe([args.codex])))
