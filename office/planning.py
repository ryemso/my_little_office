"""Bounded delegation protocol: one plan, up to six workers, one report."""
import json
from scripts.local_office import ROLES

MAX_STEPS = 6


def parse_plan(text):
    text = text.strip()
    if text.startswith('```json') and text.endswith('```'):
        text = text[7:-3].strip()
    value = json.loads(text)
    if not isinstance(value, dict) or set(value) != {'tasks'}:
        raise ValueError('총괄 계획은 tasks 배열을 가진 JSON이어야 합니다.')
    steps = value['tasks']
    if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
        raise ValueError('총괄은 1~6개 업무만 배정할 수 있습니다.')
    for step in steps:
        if not isinstance(step, dict) or not {'role', 'prompt'} <= set(step) or not set(step) <= {'role','prompt','action'}:
            raise ValueError('배정 업무에는 role과 prompt만 필요합니다.')
        if 'action' in step and (not isinstance(step['action'],str) or not step['action']):
            raise ValueError('등록된 action ID가 필요합니다.')
        if step['role'] not in ROLES or step['role'] == 'lead':
            raise ValueError('하부 직원에게만 배정할 수 있습니다.')
        if not isinstance(step['prompt'], str) or not 5 <= len(step['prompt'].strip()) <= 3000:
            raise ValueError('배정 지시는 5~3000자여야 합니다.')
        step['prompt'] = step['prompt'].strip()
    return steps


def instructions(store, task):
    kind = task.get('kind', 'single')
    if kind == 'plan':
        actions=store.actions(task.get('project_id')) if task.get('project_id') else []
        available=json.dumps([{'id':a['id'],'name':a['name'],'target':a['target']} for a in actions],ensure_ascii=False)
        return ('등록된 외부 작업: '+available+'\n외부 작업을 배정할 때는 role/prompt에 action 필드로 등록 ID를 추가하세요. 등록되지 않은 action은 만들지 마세요.\n' + '당신은 총괄입니다. 대표 지시를 실제 하부 직원들이 순서대로 수행할 1~6개 업무로 나누세요. '
                '앞 업무 결과가 다음 직원에게 전달됩니다. 연결된 프로젝트에서 파일 작성·수정·테스트·분석·홍보물 제작을 실제로 수행할 수 있습니다. 게시·배포는 아래 등록된 action ID로만 배정하세요. 연결되지 않은 계정의 외부 실행을 약속하지 마세요. '
                '총괄 자신에게 배정하거나 재귀적인 업무 배정을 요청하지 마세요. '
                '출력은 설명 없이 JSON 하나만: {"tasks":[{"role":"plan","prompt":"구체적인 업무 지시"}]}. '
                '가능한 role은 plan, dev, design, market, data입니다. 각 prompt는 5~3000자입니다.\n')
    if task.get('root_id'):
        root = store.get(task['root_id'])
        prior = [t for t in store.children(root['id']) if t['ordinal'] < task['ordinal'] and t['status'] in ('review', 'completed')]
        context = '\n대표 지시:\n' + root['prompt']
        for item in prior:
            context += f'\n{ROLES[item["role"]]}의 제출물:\n{item["output"][:8000]}\n실행 증거: {item.get("evidence_json", "{}")[:8000]}\n'
        if kind == 'report':
            return ('당신은 총괄입니다. 아래 직원 제출물을 검토하고 대표에게 최종 보고하세요. '
                    '담당별 결과, 서로 맞지 않는 부분, 남은 문제, 실제 실행하지 않은 부분을 명확하게 적으세요. '
                    '추가 업무 배정이나 외부 행동은 실행하지 마세요. 명령 접수와 원격 게시·배포 완료는 구분하고, 원격 완료 증거가 없으면 확인 필요로 보고하세요. 완료 여부를 과장하지 마세요.\n' + context)
        return '배정받은 담당 업무를 수행하고 앞 직원의 제출물을 활용하세요.\n' + context
    return ''
