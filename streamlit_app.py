"""Local office: direct commands, persistent queue and subscription Codex worker."""
import atexit
import json
from pathlib import Path
import uuid
import streamlit as st
import streamlit.components.v1 as components
from office.engine import Worker, require_login
from office.store import Store
from office.sync import publish
from scripts.local_office import ROLES, STATE

st.set_page_config(page_title='My Little Office · 출근 사무실', page_icon='🏡', layout='wide')

@st.cache_resource
def office():
    store = Store(STATE)
    worker = Worker(store)
    atexit.register(worker.close)
    return store, worker

try:
    store, worker = office()
except (RuntimeError, OSError) as error:
    st.error(str(error))
    st.stop()

scene = components.declare_component('pixel_office', path=str(Path(__file__).parent / 'office/component'))
st.session_state.setdefault('selected_role', 'lead')
st.session_state.setdefault('request_id', str(uuid.uuid4()))
st.session_state.setdefault('parent_task', None)
pending_role = st.session_state.pop('pending_role', None)
if pending_role in ROLES:
    st.session_state.selected_role = pending_role
st.title('🏡 My Little Office')
st.caption('내 PC에서 출근하는 작은 AI 회사 · 직원에게 직접 지시하고 같은 사무실에서 결과를 받으세요.')

@st.fragment(run_every='2s')
def live_office():
    status, _ = store.status()
    tasks = store.tasks()
    columns = st.columns(3)
    columns[0].metric('근무 상태', status.get('message', '출근 전'))
    columns[1].metric('실행 대기', sum(t['status'] == 'queued' for t in tasks))
    columns[2].metric('검토 대기', sum(t['status'] == 'review' for t in tasks))
    left, right = st.columns(2)
    if left.button('출근 / 근무 재개', disabled=status.get('on_duty', False), use_container_width=True):
        try:
            require_login()
            store.clock_in()
            st.rerun()
        except (RuntimeError, ValueError) as error:
            st.error(str(error))
    if right.button('퇴근 · 현재 작업 중단', disabled=not status.get('on_duty', False), use_container_width=True):
        store.pause()
        st.rerun()
    event = scene(tasks=[{'role': t['role'], 'status': t['status']} for t in tasks], selected=st.session_state.selected_role, key='office_scene', default=None)
    if isinstance(event, dict) and event.get('event_id') != st.session_state.get('scene_event'):
        role = 'lead' if event.get('role') == 'ceo' else event.get('role')
        if role in ROLES:
            st.session_state.scene_event = event['event_id']
            st.session_state.pending_role = role
            st.rerun()

live_office()
st.subheader('직원에게 업무 지시')
st.caption('현재 실행 범위: 문서·코드 초안 작성. 프로젝트 파일 수정·테스트 실행은 다음 단계입니다. 업무와 결과는 PC에 저장됩니다.')
if st.session_state.parent_task:
    original = store.get(st.session_state.parent_task)
    st.info('이전 업무를 이어서 지시합니다: ' + original['prompt'][:100])
    if st.button('새 업무로 전환'):
        st.session_state.parent_task = None
        st.rerun()
with st.form('new_task', clear_on_submit=False):
    role = st.selectbox('담당 직원', list(ROLES), format_func=lambda value: ROLES[value], key='selected_role')
    prompt = st.text_area('업무 지시', placeholder='예: 모바일 게임의 첫 1분 이탈을 줄일 기능을 구체적으로 설계해줘.', max_chars=5000, height=130)
    submitted = st.form_submit_button('업무 지시', type='primary', use_container_width=True)
if submitted:
    try:
        signature = (role, prompt.strip(), st.session_state.parent_task)
        previous = st.session_state.get('last_submission')
        request_id = previous[1] if previous and previous[0] == signature else st.session_state.request_id
        identifier = store.submit(role, prompt, request_id, st.session_state.parent_task)
        st.session_state.last_submission = (signature, identifier)
        st.session_state.request_id = str(uuid.uuid4())
        st.success('PC에 업무를 접수했습니다. 직원이 순서대로 처리합니다.')
    except ValueError as error:
        st.error(str(error))

if st.button('같은 내용으로 새 업무 준비'):
    st.session_state.pop('last_submission', None)
    st.session_state.request_id = str(uuid.uuid4())
    st.info('다음 업무 지시는 새 업무로 접수합니다.')

LABELS = {'queued':'대기', 'running':'작업 중', 'review':'검토 대기', 'completed':'완료', 'failed':'실패', 'interrupted':'중단', 'cancelled':'취소', 'cancel_requested':'중단 요청 중', 'quota_wait':'한도 대기'}

@st.fragment(run_every='2s')
def task_board():
    st.subheader('업무 보드 · 결과함')
    tasks = store.tasks()
    if not tasks:
        st.info('아직 접수한 업무가 없습니다. 출근 후 위에서 첫 업무를 지시하세요.')
    for task in tasks:
        with st.expander(f"{ROLES[task['role']]} · {LABELS[task['status']]} · {task['prompt'][:48]}", expanded=task['status'] in ('running', 'review', 'failed', 'quota_wait')):
            st.text(task['prompt'])
            st.caption('업무 ID: ' + task['id'])
            if task['error']:
                st.warning(task['error'])
            if task['output']:
                st.text(task['output'])
                st.download_button('결과 다운로드', task['output'], file_name=f"office-{task['id']}.md", key='download-'+task['id'])
            if task['status'] in ('queued', 'running'):
                if st.button('업무 중단', key='cancel-'+task['id']):
                    store.cancel(task['id']); st.rerun(scope='fragment')
            elif task['status'] != 'cancel_requested':
                col1, col2 = st.columns(2)
                if task['status'] == 'review' and col1.button('검토 완료', key='complete-'+task['id']):
                    store.complete(task['id']); st.rerun(scope='fragment')
                if col2.button('추가 지시 / 다시 진행', key='follow-'+task['id']):
                    st.session_state.parent_task = task['id']
                    st.session_state.pending_role = task['role']
                    st.rerun()
    export = {'version': 1, 'tasks': tasks}
    st.download_button('업무 기록 JSON 다운로드', json.dumps(export, ensure_ascii=False, indent=2), file_name='office-records.json', mime='application/json')
    st.caption('원본 업무 DB와 실행 로그는 PC에 남습니다. 이 앱은 업무 내용을 자동으로 공개하지 않습니다.')

task_board()
with st.expander('GitHub에 공개 기록 저장'):
    consent = st.checkbox('종료된 업무의 지시·결과를 공개 저장소와 Pages에 공개합니다.')
    if st.button('종료된 업무 기록 동기화', disabled=not consent):
        try:
            count = publish(store.tasks())
            st.success(f'{count}개 기록을 GitHub에 저장했습니다.')
        except Exception:
            st.error('GitHub 저장 실패. PC에서 gh auth login으로 저장소 쓰기 권한을 확인하세요. 로컬 결과는 유지됩니다.')
with st.expander('최초 설정 · 사용 안내'):
    st.markdown('1. `npm install -g @openai/codex`\n2. 터미널에서 `codex login` → ChatGPT 로그인\n3. 이 화면에서 **출근** → 직원 선택 → **업무 지시**')
    st.caption('GitHub CLI·API 키는 직접 업무 실행에 필요하지 않습니다. 창을 닫아도 PC 서버가 켜져 있으면 작업이 계속됩니다. PC 종료 시 멈춥니다. 앱의 일일 근무 시간·횟수 제한은 없습니다. 퇴근할 때까지 업무를 처리하며 Codex 자체 사용 한도는 적용됩니다.')
