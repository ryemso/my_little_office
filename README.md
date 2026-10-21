# My Little Office

직무별 AI 직원과 함께 제품·서비스 사업을 진행하는 작은 픽셀 사무실.

**v0.10: 대표·직원들의 업무 과정을 채팅으로 기록.** 직원 선택 → 업무 지시 → PC의 Codex 실행 → 결과 확인까지 앱 안에서 진행합니다. 명령을 복사하거나 ChatGPT·GitHub Actions에 다시 입력하지 않습니다.

## 시작

Windows에서 최신 코드를 받은 뒤:

1. `install-office.bat` 실행 (최초 1회).
2. `npm install -g @openai/codex` → `codex login`으로 ChatGPT 로그인.
3. `start-office.bat` 실행 → 사무실에서 **출근** → **업무 지시**.

Python 3.10 이상과 Node.js가 필요합니다. [설치·운영·오류 해결 안내](docs/AI_SETUP.md).

[GitHub Pages 공개 사무실](https://ryemso.github.io/my_little_office/)은 PC 실행 사무실로 들어가는 입구입니다. 실제 앱은 `http://127.0.0.1:8501`에서 열립니다. Pages에서 Python을 실행하지 않습니다.

## 업무 대화

대표의 지시부터 총괄 배정, 직원별 시작·실행·결과·오류·최종 보고까지 시간순 대화로 확인합니다. 업무별 대화방에서 추가 지시를 보내고, 재시작해도 기록을 유지합니다. 기존 기록도 표시 가능한 지시·결과를 복원합니다. 승인·중단·파일 관리는 접힌 상세 관리에 있습니다. [대화방 안내](docs/CONVERSATIONS.md).

## 회사 지식 기반

회사 지식실에서 대표의 경험·기술·업무 방식을 저장하고 공통 자료를 등록합니다. 업무에 파일과 링크를 첨부하면 총괄·담당 직원·최종 보고가 접수 당시 자료를 함께 참고합니다. 개인 프로필과 첨부 원본은 공개 코드와 분리해 PC에 보관합니다. ChatGPT의 기존 대화를 자동으로 읽지는 않습니다. [지원 형식과 사용법](docs/KNOWLEDGE.md).

## 현재 기능

총괄에게 목표 한 번을 지시하면 최대 6개 업무를 직원에게 배정하고, 앞 직원의 결과를 넘겨 순차 실행한 뒤 총괄이 최종 보고합니다. 선택한 프로젝트에서 실제 파일 작성·수정·테스트를 수행하고, 등록된 연결 작업으로 배포·홍보를 실행합니다.

이번 버전을 한 번 받은 이후에는 사무실 실행 터미널을 종료하고 `update-office.bat`을 더블클릭하면 최신 코드를 받아 실행합니다. `.venv`와 업무 DB는 보존하고 직접 수정한 코드는 덮어쓰지 않습니다. [자동 배정·업데이트 상세](docs/DELEGATION_AND_UPDATES.md).

- 오리지널 2D 픽셀 아바타와 직무별 명령 입력.
- SQLite 영구 대기열, 단일 작업 실행, 결과·추가 지시·검토 완료.
- 출퇴근, 일일 시간·횟수 제한 없는 근무, 중단·오류·한도 대기·재시작 복구.
- 업무 기록 다운로드, 선택한 공개 기록의 GitHub 동기화.

프로젝트 작업 사본에서 실제 결과물을 만들고 실행 증거와 변경 파일을 제출합니다. 원본 반영은 충돌을 확인하고 백업한 뒤 수행합니다. 배포·홍보 게시에는 실제 CLI·스크립트와 서비스 계정 연결이 필요합니다. [실행과 연결 방법](docs/EXECUTION.md). 실제 Codex 로그인과 Windows·외부 서비스 환경은 사용자 PC에서 최종 확인해야 합니다.

## 목적과 기록

게임뿐 아니라 웹 도구, 자동화, 데이터 분석 서비스, 디지털 상품을 사업 대상으로 합니다. 대표의 목표를 직무별 업무로 구체화하고 실제 결과를 검토합니다. 수익은 실제 고객·거래 증거로 확인합니다.

- [회사 및 운영](docs/COMPANY.md) · [직무](docs/ROLES.md)
- [직접 명령 설계](docs/DIRECT_OFFICE_DESIGN.md) · [시스템](docs/ARCHITECTURE.md)
- [결정 기록](docs/DECISIONS.md) · [개발 계획](docs/ROADMAP.md) · [작업 기록](docs/WORKLOG.md)

코드·설계·개발 이력은 이 저장소에 보관합니다. 인증 정보·원문 실행 로그·고객 비공개 자료는 공개하지 않습니다.

## 검증과 배포

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s scripts/tests -v
node --check site/app.js
python scripts/check_site.py
```

main 변경 → GitHub Actions 검사 → GitHub Pages 공개 사무실 배포. Streamlit 앱은 PC에서 실행합니다. 실제 Codex 호출 없이 모의 응답으로 UI·상태 전이를 테스트합니다.
