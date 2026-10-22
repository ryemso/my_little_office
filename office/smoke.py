"""A reproducible worker acceptance task, verified independently of its prose."""
import json

PREFIX='[OFFICE_EXECUTION_ACCEPTANCE_V1]'
PROMPT=PREFIX+'''
실제 실행 검증 업무입니다. 제안이나 보고서만 작성하지 마세요.
acceptance/input.csv를 만들고 내용은 다음과 같이 저장하세요:
category,value
A,10
A,20
B,5
acceptance/analyze.py를 작성하세요. 표준 csv/json 라이브러리로 위 CSV를 읽어 category별 value 합계를 구하고 acceptance/summary.json에 {"A":30,"B":5}를 저장해야 합니다. 이 분석 결과를 나타내는 막대그래프를 acceptance/chart.svg에 저장하세요. Python 명령으로 스크립트를 실제 실행하세요. 결과 파일을 다시 읽어 값과 그래프를 확인하세요. 임의로 summary.json만 만들어 분석 실행을 대체하지 마세요. 외부 게시나 설치는 필요 없습니다. 생성 파일과 실제 명령 실행 결과를 제출하세요.
'''


def verify(work, commands):
    required=['acceptance/input.csv','acceptance/analyze.py','acceptance/summary.json','acceptance/chart.svg']
    missing=[name for name in required if not (work/name).is_file()]
    if missing:return {'passed':False,'reason':'필수 파일 없음: '+', '.join(missing)}
    try:
        values=json.loads((work/'acceptance/summary.json').read_text(encoding='utf-8'))
        chart=(work/'acceptance/chart.svg').read_text(encoding='utf-8')
    except (OSError,ValueError) as error:return {'passed':False,'reason':str(error)}
    ran=any('analyze.py' in str(c.get('command','')) and c.get('exit_code')==0 for c in commands)
    passed=values=={'A':30,'B':5} and '<svg' in chart and ran
    return {'passed':passed,'files':required,'analysis_command_succeeded':ran,
            'reason':'' if passed else '분석 값·SVG 또는 분석 스크립트 실행 증거 불충족'}
