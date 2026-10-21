# PC에서 Codex 직원 출근시키기

현재 주 실행 방식은 **개인 PC의 ChatGPT 로그인 Codex CLI**입니다. GitHub Actions는 업무 접수만 하고 AI를 실행하지 않습니다. 기존 API 실행 스크립트는 과거 구현으로 남아 있으며 현재 워크플로에서 호출하지 않습니다.

## 최초 설정 (Windows)

1. Python 3.10 이상, Node.js LTS, GitHub CLI(gh)를 설치합니다. Python 설치 시 PATH 추가를 선택하세요.
2. 터미널에서 `npm install -g @openai/codex`로 최신 Codex CLI를 설치합니다.
3. `codex login`을 실행해 **ChatGPT 계정**으로 로그인합니다. API 키는 사용하지 않습니다.
4. `gh auth login`으로 ryemso/my_little_office에 쓰기 권한이 있는 GitHub 계정으로 로그인합니다.
5. 저장소의 Code → Download ZIP으로 최신 코드를 받아 압축을 풉니다. 또는 git clone 후 최신 main을 받습니다.
6. `start-office.bat`을 실행합니다. Mac/Linux에서는 `python3 scripts/local_office.py`를 실행합니다.

Python 실행 별칭 `py`가 없는 Windows는 터미널에서 `python scripts/local_office.py`를 사용하세요. CLI 로그인·설치는 사용자 PC에서 직접 해야 합니다. GitHub Pages 웹사이트만 열어서는 AI가 출근하지 않습니다.

## 업무 등록과 결과

사무실 아래 입력란에서 지시를 복사 → GitHub 실행 화면 → Run workflow → role/prompt 입력 → 공개 동의 → 실행합니다. 접수된 업무는 `PC 출근 대기`가 되고, 켜둔 실행기가 약 20초 간격으로 확인합니다. 한 번에 한 명이 처리하며 해당 직원 아바타에 작업 상태가 표시됩니다. 결과는 `AI 초안 · 검토 대기`로 저장됩니다.

현재는 역할별 **문서·코드 초안 제출** 단계입니다. 생성 코드를 실행하거나 제품 저장소를 수정·배포하거나 고객에게 메시지를 보내지 않습니다. 코드 작성 역할도 코드 초안을 제출합니다. 실제 제품 개발 작업공간 연결은 다음 단계입니다.

## 근무와 중단

- 한국 날짜 기준 하루 5시간 구간 최대 2회. 첫 실행 시 첫 구간 시작, 같은 구간 내 재실행은 남은 시간으로 복귀합니다. 구간이 끝난 뒤 다시 실행하면 두 번째 구간입니다. 자정에 구간이 종료됩니다.
- 이 시간은 회사의 근무 창입니다. Codex 사용 한도가 10시간을 보장하거나 5시간마다 초기화된다는 뜻이 아닙니다. 한도·로그인·모델 오류 시 중단하며 자동 반복 요청하지 않습니다.
- 작업당 최대 20분. 사용 중인 근무 구간이 끝나면 그보다 먼저 중단합니다. Ctrl+C로 퇴근합니다. PC 종료 시 AI도 멈춥니다.
- 로컬 체크포인트는 Windows `%LOCALAPPDATA%\MyLittleOffice`, Mac/Linux `~/.local/state/MyLittleOffice`에 저장됩니다. 결과 공개 실패 시 다음 출근에 먼저 재전송합니다. 중단된 업무는 자동 재실행하지 않으며 검토 후 다시 접수합니다.
- 실패 상세는 같은 폴더의 `last-error.txt`에서 확인합니다. 원문 로그는 공개 저장소에 올리지 않습니다.
- PC가 갑자기 꺼지면 웹에서 즉시 알 수 없습니다. 작업 시작 25분 후에도 종료 기록이 없으면 화면은 중단으로 표시합니다. 이것은 실시간 출퇴근 감지가 아닙니다. 대기 상태만으로 PC 온라인 여부를 판단할 수 없습니다.
- 같은 GitHub 계정의 **PC 한 대만** 실행하세요. 동일 PC의 중복 프로세스는 잠금으로 방지합니다.

## 인증과 공개 범위

Codex와 gh의 공식 로그인 저장소를 그대로 사용합니다. 인증 파일·토큰을 읽어서 복사하거나 GitHub Secret에 업로드하지 않습니다. API 키 환경변수가 있으면 출근을 거부하며 유료 API로 전환하지 않습니다. Codex는 사용자 설정을 건너뛴 임시 폴더의 읽기 전용 실행을 사용합니다.

지시와 최종 결과는 공개됩니다. 비밀·고객 개인정보를 입력하지 마세요. 키 형태 출력은 차단하지만 모든 민감 정보를 식별하는 장치는 아닙니다. 직원은 공개용 업무만 받아야 합니다. CLI 원문 로그와 체크포인트는 PC에 남습니다.

## 개발 검증

`python3 -m unittest discover -s scripts/tests -v`, `node --check site/app.js`, `python3 scripts/check_site.py`.
실제 구독 실행은 사용자 PC 로그인 후 첫 업무로 확인해야 합니다. CI는 모의 Codex 응답으로 상태 전이와 실패 처리만 검증합니다.

공식 실행 문서: https://developers.openai.com/codex/noninteractive/
