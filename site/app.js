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
desks.innerHTML=roles.map(r=>'<button class="desk" data-role="'+r.id+'"><span class="avatar">'+r.icon+'</span><strong>'+r.name+'</strong><small>역할 설계 · 실행 미연결</small></button>').join('');
function showRole(id){const r=roles.find(r=>r.id===id);document.querySelectorAll('.desk').forEach(b=>b.classList.toggle('active',b.dataset.role===id));detail.innerHTML='<span class="tag">ROLE / 설계 확인</span><h2>'+r.icon+' '+r.name+'</h2><p>'+r.goal+'</p><h3>담당 업무</h3><ul>'+r.jobs.map(j=>'<li>'+j+'</li>').join('')+'</ul><h3>제출할 결과물</h3><p>'+r.out+'</p><h3>현재 상태</h3><p>실행 서버 미연결. 실제 업무 배정과 자동 실행은 이후 연결합니다.</p><a class="doc" href="'+base+r.doc+'.md">상세 설계 보기 ↗</a>';}
desks.addEventListener('click',e=>{const b=e.target.closest('[data-role]');if(b)showRole(b.dataset.role);});
document.querySelectorAll('[data-view]').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.desk').forEach(d=>d.classList.remove('active'));if(b.dataset.view==='workflow')detail.innerHTML='<span class="tag">WORKFLOW</span><h2>업무 보드</h2><p>업무가 등록되지 않았습니다. 다음은 설계된 상태 흐름입니다.</p><div class="flow">'+['할 일','진행 중','검토 중','필요 시 승인','완료'].map(s=>'<span>'+s+'</span>').join('')+'</div><h3>완료 조건</h3><p>결과물과 검증 증거를 확인해야 완료합니다. 막힘·실패·취소를 별도로 기록합니다.</p><a class="doc" href="'+base+'COMPANY.md">업무 규칙 ↗</a>';else if(b.dataset.view==='decisions')detail.innerHTML='<span class="tag">DECISIONS</span><h2>회의실</h2><p>사업 하나에 집중하고, 개발은 여러 제품과 기능을 담당합니다. 사무실은 Pages, 과정은 GitHub에 기록합니다.</p><a class="doc" href="'+base+'DECISIONS.md">결정 기록 ↗</a><a class="doc" href="'+base+'ROADMAP.md">다음 설계와 개발 계획 ↗</a>';else detail.innerHTML='<span class="tag">DOCUMENTS</span><h2>자료실</h2>'+[['COMPANY','회사 및 운영'],['ROLES','직무별 설계'],['ARCHITECTURE','시스템 설계'],['DECISIONS','결정 기록'],['ROADMAP','개발 계획'],['WORKLOG','작업 기록']].map(([id,name])=>'<a class="doc" href="'+base+id+'.md">'+name+' ↗</a>').join('');}));
showRole('lead');
