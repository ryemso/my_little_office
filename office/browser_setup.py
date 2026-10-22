"""Start optional local browser setup without blocking Streamlit."""
import json
from pathlib import Path
import subprocess
import sys
import time


def start_setup(root,blog=None):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    if blog is not None:
        from office.naver import blog_id,write_receipt
        blog=blog_id(blog)
        write_receipt(root/'naver-login.json',{'status':'starting','message':'로그인 창을 여는 중입니다.','updated':time.time()})
        args=[sys.executable,'-m','office.naver','login','--root',str(root),'--blog',blog]
        filename='naver-login.log'
    else:
        args=[sys.executable,'-m','playwright','install','chromium'];filename='browser-install.log'
    with (root/filename).open('w',encoding='utf-8') as stream:
        return subprocess.Popen(args,cwd=Path(__file__).resolve().parents[1],stdout=stream,stderr=subprocess.STDOUT)
