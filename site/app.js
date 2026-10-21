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
function sprite(a,i){return `<svg viewBox="0 0 40 56" width="40" height="56" aria-hidden="true" shape-rendering="crispEdges"><ellipse cx="20" cy="51" rx="14" ry="4" fill="#344944" opacity=".2"/><g class="person"><path d="M12 37h7v13h-8v-4h1z" fill="#354354"/><path d="M21 37h7v13h1v3h-9V43z" fill="#283646"/><path d="M11 50h8v4H9v-3zM21 50h9v4h-9z" fill="#23303b"/><path d="M10 25h20v16H10z" fill="${a.shirt}"/><path d="M6 27h5v12H6zM29 27h5v12h-5z" fill="${a.skin}"/><path d="M16 24h8v5h-8z" fill="${a.skin}"/><path d="M9 7h23v16H9z" fill="${a.hair}"/>${a.style==='long'?`<path d="M7 13h6v19H7zM28 13h6v19h-6z" fill="${a.hair}"/>`:''}<path d="M11 12h19v12h-4v3H15v-3h-4z" fill="${a.skin}"/><path d="M8 9h5V5h15v3h5v8h-6v-5h-5v4h-9v3H8z" fill="${a.hair}"/><path d="M14 18h3v3h-3zM24 18h3v3h-3z" fill="#263445"/><path d="M18 24h5v1h-5z" fill="#b97867"/>${i===3||i===6?'<path d="M12 17h7v6h-7zM22 17h7v6h-7z" fill="none" stroke="#334152" stroke-width="1.5"/><path d="M19 19h3" stroke="#334152"/>':''}${i===0?'<path d="M16 29h8l-2 10h-4z" fill="#f2f1dc"/>':''}</g></svg>`;}
const positions=[[128,169],[354,169],[128,348],[354,348],[128,514],[354,514],[590,514]];
const people=roles.map((r,i)=>({...r,x:positions[i][0],y:positions[i][1],home:positions[i],motion:'자리 대기'}));
document.querySelector('#furniture').innerHTML=people.map((p,i)=>`<div class="workdesk" style="left:${p.x-55}px;top:${p.y-76}px"><span class="monitor"><i></i></span><span class="keyboard"></span><span class="mug"></span><small>${p.name}</small></div><div class="chair" style="left:${p.x-17}px;top:${p.y+7}px"></div>`).join('');
desks.innerHTML=people.map((p,i)=>`<button class="employee" data-role="${p.id}" style="left:${p.x}px;top:${p.y}px;--accent:${appearances[i].shirt}" aria-label="${p.name} 아바타 선택"><span class="bubble" aria-hidden="true">···</span>${sprite(appearances[i],i)}<span class="nameplate">${p.name}</span></button>`).join('');
let selected='lead',demo=false,timers=[];
function showRole(id){selected=id;const r=people.find(r=>r.id===id);document.querySelectorAll('.employee').forEach(b=>b.classList.toggle('active',b.dataset.role===id));detail.innerHTML='<span class="tag">직원 프로필 · '+(demo?'이동 시연':'자리 대기')+'</span><div class="profile-avatar">'+sprite(appearances[people.indexOf(r)],people.indexOf(r))+'</div><h2>'+r.name+'</h2><p>'+r.goal+'</p><h3>담당 업무</h3><ul>'+r.jobs.map(j=>'<li>'+j+'</li>').join('')+'</ul><h3>제출할 결과물</h3><p>'+r.out+'</p><h3>실제 업무 상태</h3><p>실행 서버 미연결 · 배정된 업무 없음</p><div class="profile-actions"><button id="go-meeting">회의실로 이동</button><button id="go-home">자리로 이동</button></div><p class="hint">이동은 공간 연출 시연이며 실제 업무 실행이 아닙니다.</p><a class="doc" href="'+base+r.doc+'.md">상세 설계 보기 ↗</a>';document.querySelector('#go-meeting').onclick=()=>moveMeeting(r);document.querySelector('#go-home').onclick=()=>walk(r,[...r.home]);}
const movement=new Map();
function walk(p,target){const old=movement.get(p.id);if(old)cancelAnimationFrame(old);const el=document.querySelector('[data-role="'+p.id+'"]');el.classList.add('walking');p.motion='이동 시연';const path=[[p.x,p.y+48],[target[0],p.y+48],[target[0],target[1]]];let last=performance.now();function step(now){const dt=Math.min((now-last)/1000,.05);last=now;const t=path[0],dx=t[0]-p.x,dy=t[1]-p.y,d=Math.hypot(dx,dy),speed=100*dt;if(d<=speed){p.x=t[0];p.y=t[1];path.shift();}else{p.x+=dx/d*speed;p.y+=dy/d*speed;}el.style.left=p.x+'px';el.style.top=p.y+'px';el.style.zIndex=String(Math.round(p.y)+10);if(path.length){movement.set(p.id,requestAnimationFrame(step));}else{el.classList.remove('walking');movement.delete(p.id);p.motion='도착';}}movement.set(p.id,requestAnimationFrame(step));}
function moveMeeting(p){const i=people.indexOf(p);walk(p,[730+(i%3)*57,237+Math.floor(i/3)*69]);}
function stopDemo(){demo=false;timers.forEach(clearTimeout);timers=[];document.querySelector('#demo-toggle').textContent='이동 시연 시작';document.querySelector('#demo-toggle').setAttribute('aria-pressed','false');document.querySelector('#scene-status').textContent='이동 시연 꺼짐 · 실제 업무 미연결';}
document.querySelector('#demo-toggle').onclick=()=>{if(demo){stopDemo();people.forEach(p=>walk(p,p.home));return;}demo=true;document.querySelector('#demo-toggle').textContent='이동 시연 중지';document.querySelector('#demo-toggle').setAttribute('aria-pressed','true');document.querySelector('#scene-status').textContent='회의실 이동 시연 · 실제 업무 실행 아님';people.forEach((p,i)=>timers.push(setTimeout(()=>moveMeeting(p),i*450)));};
document.querySelector('#return-desks').onclick=()=>{stopDemo();people.forEach(p=>walk(p,p.home));};
desks.addEventListener('click',e=>{const b=e.target.closest('[data-role]');if(b)showRole(b.dataset.role);});
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{if(b.dataset.view==='workflow')detail.innerHTML='<span class="tag">WORKFLOW</span><h2>업무 보드</h2><p>실제 등록된 업무가 없습니다.</p><div class="flow">'+['할 일','진행 중','검토 중','필요 시 승인','완료'].map(s=>'<span>'+s+'</span>').join('')+'</div><a class="doc" href="'+base+'COMPANY.md">업무 규칙 ↗</a>';else if(b.dataset.view==='decisions')detail.innerHTML='<span class="tag">DECISIONS</span><h2>회의실</h2><p>직원을 선택한 뒤 회의실로 이동시킬 수 있습니다. 현재는 공간 시연입니다.</p><a class="doc" href="'+base+'DECISIONS.md">결정 기록 ↗</a>';else detail.innerHTML='<span class="tag">DOCUMENTS</span><h2>자료실</h2>'+[['COMPANY','회사 및 운영'],['ROLES','직무별 설계'],['ARCHITECTURE','시스템 설계'],['DECISIONS','결정 기록'],['ROADMAP','개발 계획'],['WORKLOG','작업 기록']].map(([id,name])=>'<a class="doc" href="'+base+id+'.md">'+name+' ↗</a>').join('');}));
showRole('lead');
