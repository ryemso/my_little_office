"""Carry only Windows sandbox implementation settings into isolated CLI runs."""
import json
import os
from pathlib import Path


def windows_settings(config_root=None,windows=None):
    if windows is None:windows=os.name=='nt'
    if not windows:return [],{'windows_sandbox':'not-windows'}
    root=Path(config_root or os.getenv('CODEX_HOME') or Path.home()/'.codex').expanduser()
    path=root/'config.toml'
    info={'windows_sandbox':'Codex default','windows_config':'not configured'}
    if not path.is_file():return [],info
    try:
        try:import tomllib
        except ImportError:import tomli as tomllib
        if path.stat().st_size>1_000_000:raise ValueError('oversized config')
        with path.open('rb') as stream:data=tomllib.load(stream)
        settings=data.get('windows',{})
        features=data.get('features',{})
        if not isinstance(settings,dict) or not isinstance(features,dict):raise ValueError('invalid tables')
        mode=settings.get('sandbox')
        if mode is not None and mode not in ('mxc','elevated','unelevated'):raise ValueError('unknown Windows sandbox')
        prefer=features.get('prefer_mxc')
        if prefer is not None and not isinstance(prefer,bool):raise ValueError('invalid prefer_mxc')
    except (OSError,ValueError,ImportError):
        raise RuntimeError('Codex config.toml의 Windows 샌드박스 설정을 읽지 못했습니다. 파일 형식과 접근 권한을 확인하세요.') from None
    arguments=[]
    if mode:
        arguments+=['-c','windows.sandbox='+json.dumps(mode)]
        info.update(windows_sandbox=mode,windows_config='user selection preserved')
    if prefer is not None:
        arguments+=['-c','features.prefer_mxc='+str(prefer).lower()]
        info['prefer_mxc']=prefer
    return arguments,info
