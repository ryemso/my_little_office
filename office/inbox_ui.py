"""Owner decision dialog shared by the avatar and accessible toolbar button."""
import json
from datetime import datetime
import streamlit as st
from office.inbox import approve_decision
from office.workspaces import Workspace
from scripts.local_office import ROLES,KST


def close_inbox():
    st.session_state.inbox_open=False


def notice(message):
    st.session_state.inbox_notice=message
    st.rerun()


@st.dialog('대표 검토·승인함',width='large',on_dismiss=close_inbox)
def decision_dialog(store):
    entries=store.pending_decisions()
    if st.session_state.get('inbox_notice'):st.success(st.session_state.pop('inbox_notice'))
    counts={kind:sum(item['decision_type']==kind for item in entries) for kind in ('approval','review','attention')}
    st.caption(f"승인 {counts['approval']} · 검토 {counts['review']} · 문제 확인 {counts['attention']} · 모든 프로젝트")
    if not entries:st.info('지금 대표가 처리할 사안이 없습니다.')
    kind=st.radio('처리할 사안',['전체','승인','검토','문제 확인'],horizontal=True,key='inbox_filter')
    selected={'승인':'approval','검토':'review','문제 확인':'attention'}.get(kind)
    visible=[entry for entry in entries if not selected or entry['decision_type']==selected]
    with st.expander('일괄검토 · 문제 일괄 확인',expanded=True):
        st.caption('검토 완료와 실패·차단 문제 확인을 구분합니다. 원본 반영·외부 실행 승인은 포함하지 않습니다.')
        for category,label,method in [('review','결과 검토',store.complete_many),('attention','문제 확인',store.acknowledge_many)]:
            candidates=[row for row in visible if row['decision_type']==category]
            selected_ids=st.multiselect(label+' 대상',options=[row['id'] for row in candidates],format_func=lambda identifier:next(row['prompt'][:70] for row in candidates if row['id']==identifier),key='batch-'+category)
            if st.button('선택 '+label+' 일괄 처리',key='batch-submit-'+category,disabled=not selected_ids):
                try:
                    count=method([{'id':row['id'],'version':row['updated']} for row in candidates if row['id'] in selected_ids])
                    notice(str(count)+'건 '+label+' 처리했습니다.')
                except ValueError as error:st.error(str(error))
    maximum=st.session_state.get('inbox_limit',20)
    projects={project['id']:project['name'] for project in store.projects()}
    for index,item in enumerate(visible[:maximum]):
        identifier=item['id'];category={'approval':'승인 필요','review':'결과 검토','attention':'문제 확인'}[item['decision_type']]
        with st.expander(category+' · '+ROLES[item['role']]+' · '+item['prompt'][:50],expanded=index==0):
            project=projects.get(item['project_id'],'이전 업무')
            st.caption(project+' · '+datetime.fromtimestamp(item['updated'],KST).strftime('%m/%d %H:%M KST'))
            st.write(item['prompt'])
            if item['error']:st.warning(item['error'])
            if item['output']:
                st.markdown(item['output'][:16000])
                st.download_button('전체 결과 다운로드',item['output'],file_name='office-result.md',key='inbox-download-'+identifier)
            evidence=json.loads(item.get('evidence_json') or '{}')
            if evidence:
                with st.expander('실행 증거 확인'):
                    st.json(evidence)
                    screenshot=evidence.get('action',{}).get('screenshot')
                    if screenshot:
                        from pathlib import Path
                        path=Path(screenshot).resolve()
                        if path.is_relative_to((store.root/'publishing').resolve()) and path.is_file() and path.suffix=='.png':
                            st.image(str(path),caption='네이버 저장·발행 검증 화면')
            if item['decision_type']=='approval':
                action=json.loads(item['action_json'])
                st.write('작업: '+action['name'])
                st.write('실제 대상: '+action['target'])
                st.code(json.dumps(json.loads(action['argv']),ensure_ascii=False,indent=2),language='json')
                snapshot_key='inbox-snapshot-'+identifier
                try:
                    workspace=Workspace(store,item);workspace.prepare()
                    fingerprint=workspace.fingerprint()
                    if snapshot_key not in st.session_state:
                        st.session_state[snapshot_key]={'version':item['updated'],'fingerprint':fingerprint}
                    snapshot=st.session_state[snapshot_key]
                    changed=snapshot['fingerprint']!=fingerprint or snapshot['version']!=item['updated']
                    preview=workspace.preview()
                    if preview:
                        with st.expander('현재 작업 사본의 변경 내용'):st.code(preview,language='diff')
                    if changed:
                        st.warning('처음 연 뒤 변경 내용이 바뀌었습니다. 새 내용을 확인해야 승인할 수 있습니다.')
                        if st.button('새 변경 내용 확인',key='inbox-refresh-snapshot-'+identifier):
                            st.session_state[snapshot_key]={'version':item['updated'],'fingerprint':fingerprint}
                            st.rerun()
                    if item['waiting_for_previous']:st.info('앞 직원의 작업이 끝난 뒤 승인할 수 있습니다.')
                    if st.button('이 내용으로 실행 승인',key='inbox-approve-'+identifier,type='primary',disabled=changed or bool(item['waiting_for_previous'])):
                        approve_decision(store,identifier,snapshot['version'],snapshot['fingerprint'])
                        notice('승인했습니다. 출근 상태에서 실행 순서에 따라 처리합니다.')
                except (ValueError,OSError) as error:st.error(str(error))
                if st.button('실행 거절 · 팀 업무 중단',key='inbox-reject-'+identifier):
                    store.cancel(identifier);notice('실행을 거절하고 해당 팀 업무를 중단했습니다.')
            elif item['decision_type']=='review':
                st.caption('검토 완료는 원본 반영이나 게시·배포를 실행하지 않습니다.')
                if st.button('검토 완료',key='inbox-complete-'+identifier,type='primary'):
                    store.complete(identifier);notice('검토 완료로 처리했습니다.')
            else:
                if st.button('실패한 단계부터 다시 진행',key='inbox-retry-'+identifier):
                    try:store.retry_task(identifier);notice('실패 단계부터 대기열에 넣었습니다. 출근하면 재개하며 필요한 외부 승인은 다시 요청합니다.')
                    except ValueError as error:st.error(str(error))
                if st.button('문제 확인했음',key='inbox-ack-'+identifier):
                    try:store.acknowledge_decision(identifier,item['updated']);notice('확인했습니다. 완료 처리나 자동 재실행은 하지 않았습니다.')
                    except ValueError as error:st.error(str(error))
            if st.button('대화에서 확인·추가 지시',key='inbox-follow-'+identifier):
                st.session_state.chat_channel=store.thread_id(identifier)
                st.session_state.parent_task=identifier
                st.session_state.pending_role=item['role']
                st.session_state.pending_project_id=item['project_id']
                close_inbox();st.rerun()
    if len(visible)>maximum and st.button('사안 20개 더 보기'):
        st.session_state.inbox_limit=maximum+20;st.rerun()
    left,right=st.columns(2)
    if left.button('목록 새로고침'):st.rerun()
    if right.button('검토함 닫기'):close_inbox();st.rerun()
