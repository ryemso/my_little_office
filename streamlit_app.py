"""Local office: direct commands, persistent queue and subscription Codex worker."""
import atexit
import json
from pathlib import Path
import uuid
from datetime import datetime
import streamlit as st
import streamlit.components.v1 as components
from office.engine import Worker, require_login
from office.store import Store
from office import knowledge
from office.sync import publish
from office.workspaces import Workspace
from scripts.local_office import ROLES, STATE, KST

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
store.company_project()
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
    columns[2].metric('검토 대기', sum(t['status'] == 'review' and t['kind'] in ('single', 'plan') for t in tasks))
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
st.caption('총괄이 개발·수정·테스트·문서·홍보·배포 업무를 배정합니다. 선택한 프로젝트에서 실제 파일을 만들고 명령을 실행하며, 게시·배포는 연결된 실행 작업을 사용합니다.')
projects={p['id']:p for p in store.projects()}
project_id=st.selectbox('업무 프로젝트', list(projects), format_func=lambda value:projects[value]['name'], key='project_choice')
if st.session_state.parent_task:
    original = store.get(st.session_state.parent_task)
    st.info('이전 업무를 이어서 지시합니다: ' + original['prompt'][:100])
    if st.button('새 업무로 전환'):
        st.session_state.parent_task = None
        st.rerun()
with st.expander('회사 지식실 · 대표 정보와 공통 자료'):
    st.caption('모든 직원의 초기 기반입니다. 개인 프로필과 원본은 PC에 보관하며, 업무 실행 때 Codex에 전달합니다. 기존 ChatGPT 대화가 자동 연결되지는 않습니다.')
    with st.form('owner-profile'):
        owner_text=st.text_area('대표의 경험·기술·업무 방식',value=knowledge.profile(store),max_chars=20000,height=220)
        owner_import=st.file_uploader('대표 초기프로필 가져오기',type=['json'])
        if st.form_submit_button('대표 프로필 저장'):
            try:
                if owner_import:knowledge.import_profile(store,owner_import.getvalue())
                else:knowledge.save_profile(store,owner_text)
                st.success('다음에 접수하는 업무부터 모든 직원에게 전달합니다.')
            except (ValueError,TypeError) as error:st.error(str(error))
    with st.form('company-sources'):
        shared_files=st.file_uploader('회사 공통 자료',accept_multiple_files=True,max_upload_size=10)
        shared_url=st.text_input('공통 자료 링크',placeholder='https://...')
        if st.form_submit_button('공통 자료 등록'):
            try:
                for file in shared_files:knowledge.upload(store,file.name,file.getvalue(),scope='company')
                if shared_url.strip():knowledge.link(store,shared_url.strip(),scope='company')
                st.success('공통 자료 등록 처리 완료. 아래에서 읽기 결과를 확인하세요.')
            except Exception as error:st.error(str(error))
    for source in knowledge.sources(store,project_id):
        st.caption(('읽음' if source['status']=='ready' else '읽기 실패')+' · '+source['title']+' · '+source['note'])
        if source['text']:
            with st.expander('미리보기 · '+source['title'][:60]):st.text(source['text'][:6000])
available_sources=knowledge.sources(store,project_id)
source_labels={item['id']:('✓ ' if item['status']=='ready' else '⚠ ')+item['title'] for item in available_sources}
with st.form('new_task', clear_on_submit=False):
    role = st.selectbox('담당 직원', list(ROLES), format_func=lambda value: ROLES[value], key='selected_role')
    prompt = st.text_area('업무 지시', placeholder='예: 모바일 게임의 첫 1분 이탈을 줄일 기능을 구체적으로 설계해줘.', max_chars=5000, height=130)
    attachments=st.file_uploader('이번 업무에 첨부할 파일',accept_multiple_files=True,max_upload_size=10)
    urls=st.text_area('참고 링크 · 한 줄에 하나',height=70)
    selected_sources=st.multiselect('기존 자료 선택',list(source_labels),format_func=lambda value:source_labels[value],max_selections=20)
    st.caption('공통 자료는 자동 포함합니다. 파일당 10MB · 이미지 직접 입력은 최대 5개 · 로그인·동적 페이지는 파일로 올려주세요.')
    delegate = st.checkbox('총괄에게 지시하면 하부 직원에게 자동 배정', value=True, help='총괄 선택 시에만 적용합니다. 최대 6개 업무를 순서대로 실행하고 최종 보고합니다.')
    submitted = st.form_submit_button('업무 지시', type='primary', use_container_width=True)
if submitted:
    try:
        source_ids=list(selected_sources)
        for file in attachments:source_ids.append(knowledge.upload(store,file.name,file.getvalue(),project_id))
        cache=st.session_state.setdefault('source_link_cache',{})
        for url in knowledge.inline_links(urls+'\n'+prompt):
            cache_key=(project_id,url)
            if cache_key not in cache:cache[cache_key]=knowledge.link(store,url,project_id)
            source_ids.append(cache[cache_key])
        source_ids=sorted(set(source_ids))
        auto_team = role == 'lead' and delegate
        signature = (role, prompt.strip(), st.session_state.parent_task, auto_team, project_id, tuple(source_ids))
        previous = st.session_state.get('last_submission')
        request_id = previous[1] if previous and previous[0] == signature else st.session_state.request_id
        identifier = store.submit(role, prompt, request_id, st.session_state.parent_task, delegate=auto_team, project_id=project_id,source_ids=source_ids)
        st.session_state.last_submission = (signature, identifier)
        st.session_state.request_id = str(uuid.uuid4())
        st.session_state.chat_channel = store.thread_id(identifier)
        st.success('PC에 업무를 접수했습니다. 직원이 순서대로 처리합니다.')
    except Exception as error:
        st.error(str(error))

if st.button('같은 내용으로 새 업무 준비'):
    st.session_state.pop('last_submission', None)
    st.session_state.request_id = str(uuid.uuid4())
    st.info('다음 업무 지시는 새 업무로 접수합니다.')

LABELS = {'awaiting_approval':'게시·배포 승인 대기', 'delegating':'총괄 진행 관리', 'blocked':'팀 업무 중단', 'queued':'대기', 'running':'작업 중', 'review':'검토 대기', 'completed':'완료', 'failed':'실패', 'interrupted':'중단', 'cancelled':'취소', 'cancel_requested':'중단 요청 중', 'quota_wait':'한도 대기'}

def task_label(task):
    if task['kind'] in ('employee', 'report') and task['status'] == 'review':
        return '직원 제출 완료' if task['kind'] == 'employee' else '총괄 보고 제출'
    return LABELS[task['status']]

CHAT_NAMES={'owner':'대표', 'system':'사무실 시스템', **ROLES}
CHAT_AVATARS={'owner':'👑','lead':'🧭','plan':'💡','dev':'🛠️','design':'🎨','market':'📣','data':'📊','system':'🏡'}

@st.fragment(run_every='2s')
def work_chat():
    st.subheader('💬 업무 대화')
    channels=store.channels()
    if not channels:
        st.info('첫 업무를 지시하면 대표와 직원들의 대화가 여기에 남습니다.')
        return
    by_id={channel['id']:channel for channel in channels}
    if st.session_state.get('chat_channel') not in by_id:st.session_state.chat_channel=channels[0]['id']
    channel_id=st.selectbox('업무 대화방',list(by_id),format_func=lambda value:by_id[value]['prompt'][:65],key='chat_channel')
    channel=by_id[channel_id]
    st.caption('대표 → 총괄 배정 → 직원 실행 → 결과 보고 · 실제 접수·실행 이벤트를 2초마다 갱신합니다.')
    count_key='chat_count_'+channel_id
    count=st.session_state.get(count_key,200)
    messages=store.messages(channel_id,count)
    if messages and store.messages(channel_id,1,before=messages[0]['id']):
        if st.button('이전 대화 200개 더 보기',key='older-'+channel_id):
            st.session_state[count_key]=count+200;st.rerun()
    with st.container(height=570,border=True,key='chat-window-'+channel_id,autoscroll=True):
        for message in messages:
            name=CHAT_NAMES.get(message['actor'],message['actor'])
            with st.chat_message(name,avatar=CHAT_AVATARS.get(message['actor'],'💬')):
                timestamp=datetime.fromtimestamp(message['created'],KST).strftime('%m/%d %H:%M:%S')
                st.caption(name+' · '+timestamp+' KST'+(' · 기존 기록에서 복원' if message['historical'] else ''))
                if message['kind']=='error':st.error(message['body'])
                elif message['kind']=='progress' and message['body'].startswith('명령 실행'):st.code(message['body'],language='text')
                else:st.markdown(message['body'])
    reply=st.chat_input('이 대화에 추가 업무 지시',max_chars=5000,key='chat-input-'+channel_id)
    if reply:
        try:
            value=reply
            selected=st.session_state.get('selected_role','lead')
            store.submit(selected,value,parent=channel_id,delegate=selected=='lead',project_id=channel['project_id'])
            st.rerun()
        except ValueError as error:st.error(str(error))
    st.caption('추가 지시는 현재 선택한 직원에게 전달합니다. 파일·링크 첨부는 위 업무 지시 입력란을 사용하세요. 승인·중단·결과 파일은 아래 상세 관리에서 확인합니다.')
    transcript=store.transcript(channel_id)
    st.download_button('대화 기록 다운로드',json.dumps(transcript,ensure_ascii=False,indent=2),file_name='office-chat.json',mime='application/json',key='chat-export-'+channel_id)

work_chat()

@st.fragment(run_every='2s')
def task_board():
    st.subheader('업무 보드 · 결과함')
    tasks = store.tasks()
    if not tasks:
        st.info('아직 접수한 업무가 없습니다. 출근 후 위에서 첫 업무를 지시하세요.')
    for task in tasks:
        with st.expander(f"{ROLES[task['role']]} · {task_label(task)} · {task['prompt'][:48]}", expanded=task['status'] in ('running', 'delegating', 'review', 'failed', 'blocked', 'quota_wait', 'awaiting_approval')):
            st.text(task['prompt'])
            st.caption('업무 ID: ' + task['id'])
            context=json.loads(task.get('context_json') or '{}')
            if context.get('profile'):st.caption('접수 당시 대표 프로필 전달됨')
            for source in context.get('sources',[]):st.caption('참고 자료: '+source['title']+' · '+source['status']+' · '+source['note'])
            if task['kind'] == 'plan':
                steps = store.children(task['id'])
                if steps:
                    st.caption(' → '.join(ROLES[t['role']] + ' [' + task_label(t) + ']' for t in steps))
            elif task.get('root_id'):
                st.caption('총괄 배정 업무 · ' + ('최종 보고' if task['kind'] == 'report' else str(task['ordinal']) + '번째 직원 작업'))
            if task['error']:
                st.warning(task['error'])
            evidence=json.loads(task.get('evidence_json') or '{}')
            if evidence:
                st.json(evidence, expanded=False)
            if task.get('action_json'):
                action=json.loads(task['action_json'])
                st.write('연결 작업: '+action['name']+' · 대상: '+action['target'])
                st.code(action['argv'],language='json')
                if task['status']=='awaiting_approval' and st.button('이 내용으로 실행 승인',key='approve-'+task['id']):
                    try:
                        workspace=Workspace(store,task);workspace.prepare()
                        store.approve(task['id'],workspace.fingerprint())
                        st.rerun(scope='fragment')
                    except ValueError as error:st.error(str(error))
            if task.get('project_id') and not task.get('root_id'):
                workspace=Workspace(store,task)
                if workspace.meta.exists():
                    st.caption('실제 작업 폴더: '+str(workspace.work))
                    changes=workspace.changes()
                    if changes:st.dataframe(changes,hide_index=True,use_container_width=True)
                    if task['status'] in ('review','completed','blocked','failed','interrupted'):
                        st.download_button('프로젝트 결과 ZIP',workspace.archive(),file_name='office-project.zip',key='zip-'+task['id'])
                        if changes:
                            st.code(workspace.preview(),language='diff')
                            if task['status'] in ('review','completed') and st.button('변경 파일을 원본에 반영',key='apply-'+task['id']):
                                try:
                                    count=workspace.apply();st.success(f'{count}개 파일을 반영했습니다. 실행 중인 앱 코드라면 재시작하세요.')
                                except (ValueError,OSError) as error:st.error(str(error))

            if task['output']:
                st.text(task['output'])
                st.download_button('결과 다운로드', task['output'], file_name=f"office-{task['id']}.md", key='download-'+task['id'])
            if task['status'] in ('queued', 'running', 'delegating', 'awaiting_approval'):
                if st.button('업무 중단', key='cancel-'+task['id']):
                    store.cancel(task['id']); st.rerun(scope='fragment')
            elif task['status'] != 'cancel_requested':
                col1, col2 = st.columns(2)
                if task['status'] == 'review' and task['kind'] in ('single', 'plan') and col1.button('검토 완료', key='complete-'+task['id']):
                    store.complete(task['id']); st.rerun(scope='fragment')
                if col2.button('추가 지시 / 다시 진행', key='follow-'+task['id']):
                    st.session_state.parent_task = task['id']
                    st.session_state.pending_role = task['role']
                    st.rerun()
    export = {'version': 1, 'tasks': tasks}
    st.download_button('업무 기록 JSON 다운로드', json.dumps(export, ensure_ascii=False, indent=2), file_name='office-records.json', mime='application/json')
    st.caption('원본 업무 DB와 실행 로그는 PC에 남습니다. 이 앱은 업무 내용을 자동으로 공개하지 않습니다.')

with st.expander('업무 상세 관리 · 승인·중단·파일·검토'):
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

with st.expander('업데이트 후 실행'):
    st.write('사무실 실행 터미널을 종료한 뒤 프로젝트 폴더의 update-office.bat을 실행하세요. 최신 코드를 받고 사무실을 엽니다. 가상환경과 업무 DB는 유지됩니다.')
    st.caption('이번 버전을 한 번 받은 뒤부터 사용 가능합니다. 직접 수정한 코드가 있으면 덮어쓰지 않고 중단합니다.')

with st.expander('프로젝트·배포·홍보 연결 관리'):
    st.write('직원과 총괄 검토는 작업 사본에 파일을 쓰고 검증합니다. 공개 웹·GitHub 원문 조사와 PC의 Codex에 등록된 연결 도구를 사용할 수 있습니다.')
    st.caption('ChatGPT 웹의 연결 계정은 로컬 Codex로 자동 이전되지 않습니다. 비공개 저장소·외부 계정은 해당 PC에서 로그인하거나 MCP를 연결해야 합니다.')
    if st.button('GitHub·연결 도구 상태 확인'):
        from office.connections import connection_status
        st.session_state.connection_health=connection_status()
    if st.session_state.get('connection_health'):
        health=st.session_state.connection_health
        st.write(health['github'])
        st.caption(health['mcp_status'])
        if health['mcp']:st.write(' · '.join(health['mcp']))
        else:st.caption('활성 MCP가 없으면 공개 웹 검색과 설치된 CLI를 사용합니다.')
    st.write('새 결과물은 회사 작업실에 만듭니다. 기존 코드나 자료를 다루려면 해당 프로젝트 폴더를 등록하세요.')
    with st.form('register-project'):
        project_name=st.text_input('프로젝트 이름')
        project_path=st.text_input('PC 프로젝트 폴더 경로')
        network=st.checkbox('이 프로젝트의 네트워크 사용 허용 (패키지 설치·외부 자료 접근)',value=True)
        if st.form_submit_button('프로젝트 등록'):
            try:
                store.register_project(project_name,project_path,network=network);st.rerun()
            except (ValueError,OSError) as error:st.error(str(error))
    st.write('배포·홍보 게시 등 외부 실행은 이미 PC에서 로그인한 도구나 프로젝트 스크립트를 연결합니다. 명령 인자는 JSON 배열로 등록하며 비밀 키를 넣지 마세요.')
    with st.form('register-action'):
        action_project=st.selectbox('연결할 프로젝트',list(projects),format_func=lambda value:projects[value]['name'])
        action_name=st.text_input('작업 이름',placeholder='예: 미리보기 배포, 공식 채널 게시')
        action_target=st.text_input('실제 배포·게시 대상',placeholder='예: 내 서비스의 미리보기 환경 / 운영 중인 채널 이름')
        action_args=st.text_area('실행 인자 JSON',placeholder='["npm", "run", "deploy:preview"]')
        automatic=st.checkbox('이 작업의 자동 실행을 미리 허용 (총괄 배정 후 별도 승인 생략)')
        if st.form_submit_button('실행 작업 연결'):
            try:
                store.register_action(action_project,action_name,action_target,json.loads(action_args),automatic=automatic);st.rerun()
            except (ValueError,TypeError) as error:st.error(str(error))
    with st.form('project-network'):
        network_enabled=st.checkbox('선택한 프로젝트의 네트워크 사용',value=bool(projects[project_id]['network']))
        if st.form_submit_button('네트워크 설정 저장'):
            store.set_project_network(project_id,network_enabled);st.rerun()
    selected_actions=store.actions(project_id)
    for action in selected_actions:
        st.caption(action['name']+' → '+action['target']+(' · 자동 실행 허용' if action['automatic'] else ' · 실행 전 승인'))
