const base='https://github.com/ryemso/my_little_office/blob/main/docs/';
const roles=[
{id:'ceo',name:'대표',icon:'👑',goal:'회사 목표와 중요한 결정을 맡습니다.',jobs:['사업·목표·예산 결정','검토된 제안에 피드백','필요한 외부 행동 승인'],out:'결정과 이유, 적용 범위',doc:'COMPANY'},
{id:'lead',name:'총괄',icon:'🧭',goal:'대표의 지시를 실행 가능한 업무로 만듭니다.',jobs:['자원·제약·고객 문제 확인','담당·선행 작업·완료 기준 정의','결과 증거 확인과 막힘 해소'],out:'실행 계획과 진행 보고',doc:'ROLES'},
{id:'plan',name:'기획·사업개발',icon:'💡',goal:'고객 문제를 찾아 판매 가능한 상품과 기능을 정의합니다.',jobs:['고객·문제·대안 조사','상품·가격 가설과 요구사항','검증 지표·중단 기준 정의'],out:'사업 제안과 기능 명세',doc:'ROLES'},
{id:'dev',name:'개발',icon:'💻',goal:'게임을 포함한 다양한 제품과 기능을 실제로 구현합니다.',jobs:['웹·앱·게임·자동화 도구 제작','API·DB·관리자 화면·분석 기능','오류 수정·테스트·유지보수'],out:'작동 코드, 테스트 결과, 사용 안내',doc:'ROLES'},
{id:'design',name:'디자인·콘텐츠',icon:'🎨',goal:'고객이 이해하고 사용할 수 있는 화면과 콘텐츠를 만듭니다.',jobs:['화면·시각 자산 설계','제품 설명과 사용 안내','모바일·접근성 확인'],out:'화면과 콘텐츠 자산',doc:'ROLES'},
{id:'market',name:'마케팅·영업',icon:'📣',goal:'고객 접점과 판매 실험을 설계합니다.',jobs:['고객 채널 조사','홍보 문안·판매 페이지 준비','유입·문의·구매 실험 설계'],out:'홍보 소재와 판매 실험 계획',doc:'ROLES'},
{id:'data',name:'데이터·운영',icon:'📊',goal:'실제 기록으로 성과와 비용을 확인합니다.',jobs:['지표 정의·데이터 검증','사용·매출·비용 분석','문의·운영 문제 정리'],out:'원천과 한계를 설명하는 분석 보고',doc:'ROLES'}
];

let officeTasks=[];
const detail=document.querySelector('#detail'),desks=document.querySelector('#desks');
const appearances=[
 {hair:'#4b3932',shirt:'#456f60',style:'short',skin:'#f1c5a8'},
 {hair:'#24354c',shirt:'#d3a04e',style:'short',skin:'#e8b38c'},
 {hair:'#9b6550',shirt:'#be7685',style:'long',skin:'#f5ccb0'},
 {hair:'#496aa0',shirt:'#607baf',style:'short',skin:'#f1c5a8'},
 {hair:'#5c3d56',shirt:'#9b83b8',style:'long',skin:'#dca480'},
 {hair:'#dfae65',shirt:'#ce8254',style:'short',skin:'#f5ccb0'},
 {hair:'#343e3d',shirt:'#579a92',style:'short',skin:'#bb8867'}
];
// Original 16 x 24 pixel characters; no third-party avatar assets.
function sprite(a,i){
const palette={H:a.hair,S:a.skin,C:a.shirt,D:'#26384a',E:'#24303d',W:'#fff5db',B:'#e99396',A:['#efc657','#f0da8a','#ed9cae','#9cd4e2','#c6a2dd','#f3bd7d','#99cebe'][i]};
const front=[
'.....HHHHHH.....','....HHHHHHHH....','...HHHHHHHHHH...','...HHHHHHHHHH...',
'...HHSSHHSSHH...','...HSSSSSSSSH...','...SSSESSSESS...', '...SSSWSSSWSS...',
'...SSBSSSSBSS...','....SSSEESSS....','.....SSSSSS.....','......SSSS......',
'....CCCCCCCC....','...CCCCAACCCC...','...SCCCCCCCCS...','...SCCCCCCCCS...',
'...SCCCCACCCS...','....CCCCCCCC....','.....DDDDDD.....','.....DDDDDD.....',
'.....DD..DD.....','.....DD..DD.....','....DDD..DDD....','....DDD..DDD....'];
const back=front.map((line,y)=>y<11?line.replace(/[SEWB]/g,'H'):y<18?line.replace(/A/g,'C'):line);
const side=[
'.....HHHHHH.....','....HHHHHHHH....','....HHHHHHHHH...','....HHHHHHHHH...',
'....HHHHSSSSH...','....HHHSSSSSS...','....HHHSSSESSS..','....HHHSSSWSSS..',
'....HHSSSBSSS...','.....SSSSSSS....','......SSSSS.....','......SSSS......',
'.....CCCCCC.....','.....CCACCCC....','.....CCCSCCC....','.....CCCSCCC....',
'.....CCCSCCC....','.....CCCCCCC....','......DDDDD.....','......DDDDD.....',
'......DD.DD.....','......DD.DD.....','.....DDD.DDD....','.....DDD.DDD....'];
function draw(rows,kind){let out='';rows.forEach((row,y)=>[...row].forEach((c,x)=>{if(palette[c])out+=`<rect x="${x}" y="${y}" width="1" height="1" fill="${palette[c]}"/>`;}));return `<g class="pose pose-${kind}">${out}</g>`;}
let accessory='';if(i===0)accessory='<path d="M5 1V0l2 1 1-1 1 1 2-1v3H5z" fill="#f5ce59"/>';
if(i===2)accessory='<path d="M11 3h3v3h-3zM10 4h1v1h-1zM13 2h2v2h-2z" fill="#f1a5b9"/>';
if(i===4)accessory='<path d="M12 2h2v4h-2zM11 3h4v2h-4z" fill="#dcafea"/><rect x="12" y="3" width="1" height="1" fill="#fff1b0"/>';
if(i===3||i===6)accessory+='<path d="M4 6h4v3H4zM9 6h4v3H9zM8 7h1" fill="none" stroke="#425364" stroke-width=".6"/>';
return `<svg class="pixel-avatar" viewBox="0 0 16 25" width="48" height="75" aria-hidden="true" shape-rendering="crispEdges"><path d="M3 24h10v1H3z" fill="#304b39" opacity=".25"/><g class="person">${draw(front,'front')}${draw(back,'back')}${draw(side,'side')}<g class="accessory">${accessory}</g></g></svg>`;
}

const positions=[[128,169],[354,169],[128,348],[354,348],[128,514],[354,514],[590,514]];
const people=roles.map((r,i)=>({...r,x:positions[i][0],y:positions[i][1],home:positions[i],motion:'자리 대기'}));
document.querySelector('#furniture').innerHTML=people.map((p,i)=>`<div class="workdesk" style="left:${p.x-55}px;top:${p.y-76}px"><span class="monitor"><i></i></span><span class="keyboard"></span><span class="mug"></span><small>${p.name}</small></div><div class="chair" style="left:${p.x-17}px;top:${p.y+7}px"></div>`).join('');
desks.innerHTML=people.map((p,i)=>`<button class="employee" data-role="${p.id}" data-facing="down" style="left:${p.x}px;top:${p.y}px;--accent:${appearances[i].shirt}" aria-label="${p.name} 아바타 선택"><span class="bubble" aria-hidden="true">···</span>${p.id==='ceo'?'<span class="owner-alert" hidden aria-hidden="true">!<span class="owner-count"></span></span>':''}${sprite(appearances[i],i)}<span class="nameplate">${p.name}</span></button>`).join('');
let selected='lead',demo=false,timers=[];
function showRole(id){selected=id;const r=people.find(r=>r.id===id);document.querySelectorAll('.employee').forEach(b=>b.classList.toggle('active',b.dataset.role===id));detail.innerHTML='<span class="tag">직원 프로필 · '+(demo?'이동 시연':'자리 대기')+'</span><div class="profile-avatar">'+sprite(appearances[people.indexOf(r)],people.indexOf(r))+'</div><h2>'+r.name+'</h2><p>'+r.goal+'</p><h3>담당 업무</h3><ul>'+r.jobs.map(j=>'<li>'+j+'</li>').join('')+'</ul><h3>제출할 결과물</h3><p>'+r.out+'</p><h3>실제 업무 상태</h3><p id="employee-task-state">업무 기록 확인 중</p><div class="profile-actions"><button id="go-meeting">회의실로 이동</button><button id="go-home">자리로 이동</button></div><p class="hint">이동은 공간 연출 시연이며 실제 업무 실행이 아닙니다.</p><a class="doc" href="'+base+r.doc+'.md">상세 설계 보기 ↗</a>';document.querySelector('#go-meeting').onclick=()=>moveMeeting(r);document.querySelector('#go-home').onclick=()=>walk(r,[...r.home]);renderAIUI();}
const movement=new Map();
function walk(p,target){const old=movement.get(p.id);if(old)cancelAnimationFrame(old);const el=document.querySelector('[data-role="'+p.id+'"]');el.classList.add('walking');p.motion='이동 시연';const path=[[p.x,p.y+48],[target[0],p.y+48],[target[0],target[1]]];let last=performance.now();function step(now){const dt=Math.min((now-last)/1000,.05);last=now;const t=path[0],dx=t[0]-p.x,dy=t[1]-p.y,d=Math.hypot(dx,dy),speed=100*dt;if(d>0){el.dataset.facing=Math.abs(dx)>Math.abs(dy)?(dx>0?'right':'left'):(dy>0?'down':'up');el.dataset.frame=String(Math.floor(now/150)%2);}if(d<=speed){p.x=t[0];p.y=t[1];path.shift();}else{p.x+=dx/d*speed;p.y+=dy/d*speed;}el.style.left=p.x+'px';el.style.top=p.y+'px';el.style.zIndex=String(Math.round(p.y)+10);if(path.length){movement.set(p.id,requestAnimationFrame(step));}else{el.classList.remove('walking');el.dataset.frame='0';el.dataset.facing='down';movement.delete(p.id);p.motion='도착';}}movement.set(p.id,requestAnimationFrame(step));}
function moveMeeting(p){const i=people.indexOf(p);walk(p,[730+(i%3)*57,237+Math.floor(i/3)*69]);}
function stopDemo(){demo=false;timers.forEach(clearTimeout);timers=[];document.querySelector('#demo-toggle').textContent='이동 시연 시작';document.querySelector('#demo-toggle').setAttribute('aria-pressed','false');document.querySelector('#scene-status').textContent='이동 시연 꺼짐 · 업무는 아래 기록 확인';}
document.querySelector('#demo-toggle').onclick=()=>{if(demo){stopDemo();people.forEach(p=>walk(p,p.home));return;}demo=true;document.querySelector('#demo-toggle').textContent='이동 시연 중지';document.querySelector('#demo-toggle').setAttribute('aria-pressed','true');document.querySelector('#scene-status').textContent='회의실 이동 시연 · 실제 업무 실행 아님';people.forEach((p,i)=>timers.push(setTimeout(()=>moveMeeting(p),i*450)));};
document.querySelector('#return-desks').onclick=()=>{stopDemo();people.forEach(p=>walk(p,p.home));};
desks.addEventListener('click',e=>{const b=e.target.closest('[data-role]');if(b)showRole(b.dataset.role);});
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{if(b.dataset.view==='workflow')detail.innerHTML='<span class="tag">WORKFLOW</span><h2>업무 보드</h2><p>아래 AI 업무 기록에서 접수·진행·검토 상태를 확인하세요.</p><div class="flow">'+['할 일','진행 중','검토 중','필요 시 승인','완료'].map(s=>'<span>'+s+'</span>').join('')+'</div><a class="doc" href="'+base+'COMPANY.md">업무 규칙 ↗</a>';else if(b.dataset.view==='decisions')detail.innerHTML='<span class="tag">DECISIONS</span><h2>회의실</h2><p>직원을 선택한 뒤 회의실로 이동시킬 수 있습니다. 현재는 공간 시연입니다.</p><a class="doc" href="'+base+'DECISIONS.md">결정 기록 ↗</a>';else detail.innerHTML='<span class="tag">DOCUMENTS</span><h2>자료실</h2>'+[['COMPANY','회사 및 운영'],['ROLES','직무별 설계'],['ARCHITECTURE','시스템 설계'],['DECISIONS','결정 기록'],['ROADMAP','개발 계획'],['WORKLOG','작업 기록']].map(([id,name])=>'<a class="doc" href="'+base+id+'.md">'+name+' ↗</a>').join('');}));


// AI results are public data; API credentials are never accepted by this page.
const taskSource='https://raw.githubusercontent.com/ryemso/my_little_office/main/site/data/tasks.json';
const workflowURL='https://github.com/ryemso/my_little_office/actions/workflows/ai-task.yml';
function safeText(value){return String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
const taskLabels={awaiting_approval:'게시·배포 승인 대기',delegating:'총괄 진행 관리',blocked:'팀 업무 중단',completed:'완료',cancelled:'취소',quota_wait:'한도 대기',queued:'PC 출근 대기',running:'작업 중',review:'AI 초안 · 검토 대기',failed:'실패',incomplete:'부분 결과 · 확인 필요',interrupted:'실행 중단'};
let taskReadError='',draftPrompt='',draftRole='lead';
function renderAIUI(){
 if(window.officeRuntimeManaged)return;
 const panel=document.querySelector('#work-panel');if(!panel)return;
 const selectedTask=officeTasks.find(t=>t.role===selected),stateEl=document.querySelector('#employee-task-state');
 if(stateEl)stateEl.textContent=selectedTask?(taskLabels[selectedTask.status]||selectedTask.status):'실행 사무실에서 직접 지시하세요';
 for(const p of people){const task=officeTasks.find(t=>t.role===p.id),el=document.querySelector('[data-role="'+p.id+'"]');el.classList.toggle('ai-working',task?.status==='running');el.querySelector('.bubble').textContent=task?.status==='running'?'작업':task?.status==='review'?'검토':'···';}
 panel.innerHTML='<h2>출근 사무실 · 직접 업무 지시</h2><p>PC에서 start-office.bat을 실행한 뒤 사무실을 여세요. 총괄에게 목표를 지시하면 직원들에게 순서대로 배정하고 최종 보고합니다. 프로젝트 파일 수정·테스트와 연결된 배포·홍보 작업을 수행합니다. 업데이트 후 실행은 update-office.bat을 사용하세요.</p><a class="doc" href="http://127.0.0.1:8501" target="_blank" rel="noopener">이 PC의 실행 사무실 열기 ↗</a><a class="doc" href="'+base+'AI_SETUP.md">최초 설치 안내 ↗</a><p class="hint">이곳은 GitHub Pages의 공개 사무실입니다. 실제 실행 앱은 PC에서 열립니다. PC 실행기를 켜야 접속할 수 있습니다. 휴대전화에서는 내 PC로 연결되지 않습니다.</p><h3>공개 동기화된 업무 기록</h3><button id="refresh-tasks">기록 새로고침</button><p class="hint">'+safeText(taskReadError||'PC 앱에서 공개 저장한 기록만 표시합니다. 실시간 업무는 실행 사무실에서 확인하세요.')+'</p>'+(officeTasks.length?officeTasks.map(t=>'<article class="task-result"><h3>'+safeText(t.role_name)+' · '+safeText(taskLabels[t.status]||t.status)+'</h3><h4>지시</h4><pre>'+safeText(t.prompt)+'</pre>'+(t.output?'<h4>결과</h4><pre>'+safeText(t.output)+'</pre>':'')+'</article>').join(''):'<p>아직 공개 저장된 업무가 없습니다.</p>');
 document.querySelector('#refresh-tasks').onclick=()=>refreshTasks();
}
async function refreshTasks(){try{const response=await fetch(taskSource,{cache:'no-store'});if(!response.ok)throw Error();const data=await response.json();if(data.version!==1||!Array.isArray(data.tasks))throw Error();officeTasks=data.tasks.slice(0,20);for(const t of officeTasks.filter(t=>t.status==='running')){if(t.engine==='local-codex'){if(Date.now()-Date.parse(t.started_at)>25*60*1000)t.status='interrupted';continue;}if(!/^\d+$/.test(t.run_id))continue;try{const r=await fetch('https://api.github.com/repos/ryemso/my_little_office/actions/runs/'+t.run_id);if(r.ok){const run=await r.json();if(run.status==='completed')t.status='interrupted';}}catch{}}taskReadError='';document.querySelector('#ai-connection').textContent=officeTasks.some(t=>t.output)?'실행 기록 있음':'실행 기록 없음';}catch{taskReadError='업무 기록을 읽지 못했습니다. 마지막 표시값이 오래되었을 수 있습니다.';}if(!document.querySelector('#task-prompt')?.matches(':focus'))renderAIUI();}
renderAIUI();refreshTasks();setInterval(()=>{if(!document.hidden)refreshTasks();},20000);

showRole('lead');
