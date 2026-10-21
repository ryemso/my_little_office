"""Reuse the original pixel office as a bidirectional Streamlit component."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def build(check=False):
    page = (ROOT / 'site/index.html').read_text(encoding='utf-8')
    scene = page[page.index('<div class="workspace"'):page.index('<section class="ai-panel"')]
    css = (ROOT / 'site/style.css').read_text(encoding='utf-8')
    css = '\n'.join(line for line in css.splitlines() if not line.startswith('@import'))
    js = (ROOT / 'site/app.js').read_text(encoding='utf-8').split('// AI results are public data;')[0]
    bridge = '''
const labels={awaiting_approval:'게시·배포 승인 대기',delegating:'총괄 진행 관리',blocked:'팀 업무 중단',queued:'대기',running:'작업 중',review:'검토 대기',completed:'완료',cancel_requested:'중단 요청',interrupted:'중단',failed:'실패',quota_wait:'한도 대기',cancelled:'취소'};
function renderAIUI(){
 for(const p of people){const task=officeTasks.find(t=>t.role===p.id);const el=document.querySelector('[data-role="'+p.id+'"]');el.classList.toggle('ai-working',task?.status==='running');el.querySelector('.bubble').textContent=task?.status==='running'?'작업':task?.status==='review'?'검토':task?.status==='delegating'?'관리':'···';}
 const state=document.querySelector('#employee-task-state'),task=officeTasks.find(t=>t.role===selected);
 if(state)state.textContent=task?(labels[task.status]||task.status):'배정된 업무 없음';
}
function send(type,data){window.parent.postMessage({isStreamlitMessage:true,type,...data},'*');}
window.addEventListener('message',event=>{
 if(event.source!==window.parent||event.data?.type!=='streamlit:render')return;
 const args=event.data.args||{};officeTasks=Array.isArray(args.tasks)?args.tasks:[];
 if(roles.some(r=>r.id===args.selected))showRole(args.selected);else renderAIUI();
 send('streamlit:setFrameHeight',{height:Math.min(1150,document.body.scrollHeight+8)});
});
desks.addEventListener('click',event=>{const button=event.target.closest('[data-role]');if(button)send('streamlit:setComponentValue',{value:{role:button.dataset.role,event_id:Date.now()+':'+Math.random()},dataType:'json'});});
showRole('lead');
send('streamlit:componentReady',{apiVersion:1});
send('streamlit:setFrameHeight',{height:820});
new ResizeObserver(()=>send('streamlit:setFrameHeight',{height:Math.min(1150,document.body.scrollHeight+8)})).observe(document.body);
'''
    target = ROOT / 'office/component'
    target.mkdir(exist_ok=True)
    extra = 'body{background:transparent}.workspace{grid-template-columns:minmax(0,2fr) minmax(230px,1fr)}.floor{padding:16px}.detail{padding:20px}.scene-scroll{max-width:100%}.rooms{display:none}@media(max-width:850px){.workspace{grid-template-columns:1fr}.detail{display:none}}'
    content = '<!doctype html><html lang="ko"><meta charset="utf-8"><style>'+css+extra+'</style><body>'+scene+'<script>'+js+bridge+'</script></body></html>'
    if check:
        assert (target / 'index.html').read_text(encoding='utf-8') == content, 'Rebuild office component before committing'
    else:
        (target / 'index.html').write_text(content, encoding='utf-8')

if __name__ == '__main__':
    import sys
    build(check='--check' in sys.argv)
