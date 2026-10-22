## 네이버·예약·실행 복구

[실제 업무 실행·게시·예약 안내](AUTOMATION.md)를 확인하세요. 연결 관리에서 전용 브라우저 준비·로그인과 네이버 저장/발행 action을 등록할 수 있습니다. 예약·반복 업무는 PC 서버가 켜져 있고 출근 중일 때만 접수합니다. 실패 단계 재개는 대표 느낌표 팝업에서 처리합니다.

## GitHub 결과 반영

프로젝트·배포·홍보 연결 관리에서 `결과를 받을 GitHub 저장소`에 `owner/repository`를 입력하고 **GitHub 결과 반영 기능 연결**을 누르세요. 해당 PC에 GitHub CLI를 설치하고 `gh auth login`으로 저장소 쓰기 권한을 연결해야 합니다. ChatGPT의 GitHub 연결과 별개입니다.

총괄에게 산출물을 만든 뒤 GitHub에 반영하도록 지시하면 등록된 action을 배정할 수 있습니다. 대표 느낌표 승인함에서 변경을 확인하고 승인하면 `office/` 전용 브랜치에 반영합니다. 결과의 커밋 URL을 확인하세요. 기본 브랜치 병합이나 Pages 배포까지 자동 수행하지 않습니다. 원격과 원본이 다르면 충돌로 중단하므로 실제 저장소를 내려받은 폴더를 프로젝트로 등록하는 것이 좋습니다.

> 작업 경로 진단 보완: environment.stage=plan은 첫 총괄 배정으로 read-only가 정상입니다. 직원 실무·최종 보고는 해당 실행의 environment를 확인하세요. project.registered=true와 file_count=0은 등록된 빈 작업실입니다. 작업 사본은 .git을 복사하지 않아 원본 Git 연결 여부와 구분해야 합니다. exec에 --cd로 실제 절대 경로를 명시하고 등록 정보를 증거로 남깁니다. 267은 실제 실패한 직원의 cwd·실행 로그로 확인해야 합니다.

> v0.12: 대표 아바타의 느낌표를 클릭해 검토·승인 팝업을 여세요. 결과 확인·실행 승인·거절·추가 지시를 한곳에서 처리합니다. [대표 검토함](OWNER_INBOX.md).

> v0.11: 직원과 총괄 검토가 파일을 제작·검증하고, 실시간 웹 검색과 PC의 Codex 연결 도구·GitHub 인증을 사용합니다. 사용자 설정 제외를 해제하되 앱의 작업 사본 범위·ChatGPT 인증을 명시합니다. 업데이트 후 연결 관리의 상태 확인을 사용하세요. [제작·접근 권한](ACCESS.md). 아래 사용자 설정 제외에 관한 설명은 이전 버전 기록입니다.

> 2026-10-22 Windows 설정 전달: 터미널의 `/status`는 해당 대화형 세션 상태이며 앱 실행 프로세스의 실제 설정과 다를 수 있습니다. 앱은 사용자 설정 중 Windows 샌드박스 구현 선택(`windows.sandbox`, `features.prefer_mxc`)만 전달하고, 실제 작업 범위·작업 폴더·선택된 Windows 설정을 업무 대화와 실행 증거 및 로컬 `.environment.json`에 기록합니다. 사용자 설정의 토큰·MCP·모델·Full Access 선택을 통째로 가져오지 않습니다. Windows 구현 선택이 없는 PC는 Codex 기본 선택을 유지합니다. 이 보완이 정책 차단 원인을 확정하거나 승인을 대신하는 것은 아닙니다.

> 2026-10-22 정책 차단 오류 보완: 총괄의 계획·보고 단계는 앱이 확인한 파일 목록과 전달 자료로 수행하고 셸 실행 도구를 사용하지 않습니다. 실제 개발·테스트는 직원 단계에서 기존 작업공간 권한으로 실행합니다. `blocked by policy`는 로그인 오류가 아니며, 정책에 막힌 실행을 완료로 처리하거나 자동 재시도하지 않습니다. 출력 파일이 비어 있으면 완료 이벤트의 최종 메시지를 확인하고, 실패한 경우에도 나온 결과는 보존합니다. 업데이트 후 같은 업무를 추가 지시로 다시 접수하세요. 직원 실행까지 정책에 막히면 해당 차단 내용으로 별도 확인이 필요합니다.

> v0.10: 업무 과정은 이제 **업무 대화**에 직무별 채팅으로 남습니다. 대화창에서 후속 지시를 보내고, 기존 제어는 **업무 상세 관리**에서 사용하세요. [대화방 안내](CONVERSATIONS.md).

> Windows에서 codex.exe 직접 실행은 성공하는데 Node spawn ENOENT가 발생하면 최신 앱으로 업데이트하세요. npm 설치의 실제 네이티브 실행 파일을 우선 호출하며, Codex 재설치나 로그아웃을 반복할 필요는 없습니다. 앱과 실행 터미널을 완전히 종료한 뒤 업데이트하고 새 업무를 접수합니다.

> 로컬 실행 실패: 업무 결과에 표시되는 오류 종류·원문·진단 파일 경로를 확인하세요. 이 오류가 반드시 로그인 실패를 의미하지 않습니다. Codex 조기 종료는 종료 코드와 stderr를 표시하며, 내부 예외는 PC의 logs/worker-*.log에 traceback을 저장합니다. 해당 로그는 공개 GitHub에 자동 게시하지 않습니다.

> v0.9: 회사 지식실에서 대표 프로필을 저장하고 파일·공개 링크를 업무에 첨부하세요. `update-office.bat`으로 업데이트하면 새 문서 읽기 의존성도 설치합니다. [자료와 프로필 안내](KNOWLEDGE.md).

> v0.8: 초안 전용 제한을 제거했습니다. 회사 작업실·등록 프로젝트에서 실제 파일 작성·수정·테스트를 수행하고, 연결 작업으로 홍보·배포를 실행합니다. [프로젝트·서비스 연결 안내](EXECUTION.md).

> v0.7: 총괄에게 지시할 때 자동 배정을 선택하면 직원들이 순서대로 수행하고 총괄이 보고합니다. 이번 버전을 한 번 받은 뒤부터 `update-office.bat`으로 최신 코드를 받아 실행할 수 있습니다. [배정·업데이트 사용법](DELEGATION_AND_UPDATES.md).

# Streamlit 실행 사무실 (v0.9)

이제 사무실 안에서 직원 선택 → 업무 지시 → 실행 → 결과 검토까지 진행합니다. 명령 복사나 ChatGPT·GitHub Actions에 재입력할 필요가 없습니다.

## Windows 최초 설치

1. Python 3.10 이상과 Node.js LTS를 설치합니다. Python 설치 시 PATH 추가를 선택합니다.
2. [저장소](https://github.com/ryemso/my_little_office)의 Code → Download ZIP으로 최신 코드를 받아 압축을 풉니다. 기존 clone을 쓰면 최신 main을 받습니다.
3. `install-office.bat`을 실행해 전용 Python 환경과 Streamlit을 설치합니다.
4. 터미널에서 `npm install -g @openai/codex`를 실행합니다.
5. `codex login`으로 **ChatGPT 계정**에 로그인합니다. API 키는 필요하지 않습니다.
6. `start-office.bat`을 실행합니다. 브라우저가 열리지 않으면 `http://127.0.0.1:8501`로 접속합니다.
7. 사무실에서 **출근 / 근무 재개** → 직원 아바타 선택 → 업무 입력 → **업무 지시**를 누릅니다.

매일 사용하는 것은 `start-office.bat`과 사무실 화면뿐입니다. 이미 Codex CLI에 ChatGPT로 로그인되어 있으면 다시 로그인하지 않아도 됩니다. 세션이 만료되면 PC 터미널에서 재로그인합니다.

`py` 명령이 없다면 Python 설치를 확인하거나 다음 명령을 사용합니다.

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run streamlit_app.py --server.address=127.0.0.1 --server.port=8501
```

Mac/Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run streamlit_app.py --server.address=127.0.0.1 --server.port=8501
```

## GitHub Pages와 실행 앱의 관계

[공개 사무실](https://ryemso.github.io/my_little_office/)에서 **이 PC의 실행 사무실 열기**를 누르면 로컬 Streamlit 사무실로 들어갑니다. 이때 주소가 localhost로 바뀝니다. Pages는 Python을 실행하지 않으며 PC 앱이 켜져 있어야 접속됩니다.

이번 구현은 기존 설계의 **동일 출처 로컬 사무실 경로**를 기본으로 채택했습니다. Pages 페이지에서 로컬 API를 직접 호출하는 연결·페어링은 구현하지 않았습니다. Streamlit의 로컬 화면과 서버가 함께 동작하므로 일상 업무에서 명령 복사는 없어집니다. 모바일에서 사용자 PC로 원격 명령을 보내는 기능은 아직 없습니다.

## 지금 할 수 있는 것

- 기존 오리지널 픽셀 아바타 선택으로 담당 직원 지정. 드롭다운으로도 변경 가능.
- 자연어 명령 직접 접수, SQLite 영구 대기열, 한 번에 한 업무 실행.
- 작업 상태·검토 대기 말풍선, 2초 주기 상태 갱신.
- 초안 결과 확인·다운로드·검토 완료·이전 결과를 포함한 추가 지시.
- 대기 업무 취소, 실행 업무 중단, 퇴근, 오류·한도 대기.
- 브라우저를 닫아도 PC 서버가 켜져 있으면 접수 업무 계속 실행.
- PC 강제 종료 후 앱을 다시 켜면 기존 실행 업무를 중단으로 복구. 자동 중복 실행하지 않음.

실행 프로젝트를 선택하면 직원이 작업 사본의 실제 파일을 작성·수정하고 테스트·빌드·분석 명령을 실행합니다. 배포·홍보 게시에는 해당 프로젝트의 실행 명령과 계정을 연결합니다. 변경 결과를 확인한 뒤 원본에 반영할 수 있습니다.

## 근무 시간

앱의 **5시간 × 2회 제한을 폐지**했습니다. 출근하면 직접 퇴근하거나 PC 실행기를 종료할 때까지 업무를 처리합니다. 자정에도 근무를 강제로 종료하지 않습니다. 화면의 오늘 근무 구간·남은 시간 표시는 제거했습니다.

작업당 최대 20분의 개별 실행 제한은 유지합니다. Codex 자체 사용 한도·실행 오류 시 자동 반복하지 않고 근무를 멈춥니다. 원인을 확인한 뒤 출근하고 중단된 업무는 추가 지시로 다시 진행합니다. 사용 한도 복구 시각은 추정하지 않습니다. 유료 API로 전환하지 않습니다.

## 저장과 GitHub 공개

원본 DB와 Codex 진단 로그는 Windows `%LOCALAPPDATA%\MyLittleOffice`, Mac/Linux `~/.local/state/MyLittleOffice`에 있습니다. 원문 로그에는 로컬 경로 등이 포함될 수 있으므로 공개하지 마세요. 인증 파일은 공식 Codex 저장소에 유지하며 웹에 전달하지 않습니다.

기존 DB에 남은 과거 근무 구간·종료 시각은 새 근무 제한으로 사용하지 않습니다. 업무 기록은 유지합니다. 이전 GitHub 대기열의 업무는 새 앱으로 자동 가져오지 않습니다. 두 실행기는 같은 잠금을 사용하므로 동시에 켤 수 없습니다.

개발 코드·설계·작업 이력은 GitHub에 저장합니다. 실제 업무의 지시·결과도 공개 보관하려면 앱 아래 **GitHub에 공개 기록 저장**에서 공개 동의를 선택하고 **종료된 업무 기록 동기화**를 누릅니다. PC에서 GitHub CLI 설치와 `gh auth login`이 필요합니다. 이 선택 기능은 종료된 기록만 올리며 AI 실행에는 gh가 필요하지 않습니다. 원문 로그·DB·인증 파일을 업로드하지 않습니다. 실패해도 로컬 결과는 유지됩니다.

## 실행 오류

- Codex 없음: `npm install -g @openai/codex` 후 실행기를 다시 켭니다.
- 로그인 오류: `codex login status`로 상태 확인, 필요 시 `codex login`.
- API 키 환경변수: `OPENAI_API_KEY`, `CODEX_API_KEY`를 해제하고 실행합니다.
- 포트 충돌: 이미 켜둔 사무실이 있는지 확인합니다. 기본 주소는 8501입니다.
- 다른 실행기 사용 중: 예전 출근 터미널·다른 Streamlit 실행기를 종료합니다.
- Windows 설치·프로세스 중단은 사용자 PC의 실제 환경에서 최종 확인해야 합니다.

## 검증 범위

백엔드·Codex 어댑터·Streamlit AppTest 총 44개 테스트, JS 문법, 정적 링크, 로컬 서버 health와 HTML 응답을 검증했습니다. UI 테스트의 Codex 응답은 모의 응답입니다. 실제 ChatGPT 구독 인증과 모델 실행, Windows 브라우저에서의 아바타 선택·프로세스 트리 중단은 사용자 PC에서 최종 검증해야 합니다.

공식 참고: https://docs.streamlit.io/develop/concepts/custom-components/intro , https://docs.streamlit.io/develop/api-reference/execution-flow/st.fragment , https://developers.openai.com/codex/noninteractive/
