# 기본 / ego 업무별 브라우저 모드 (v0.20.1, 실험 기능 포함)

## P0 — 확인한 기준

- main: f2eb991 (v0.19.3). PR #1의 최초 작업 기준은 3b738b8이며 main을 포함하고 있어 충돌은 없었다.
- 기존 PR은 site/runtime.js → /api/submit → SQLite context_json.browser_mode → 직원 프롬프트 전달까지 구현했다. 실행기 도구 제한은 없었다.
- runtime_mode=exec/appserver는 Codex 프로토콜과 승인 왕복 방식이다. browser_mode=standard/ego는 업무에 고정한 브라우저 선택이며 두 값은 독립적이다.
- 실제 설치한 Codex 0.163.0의 생성 JSON schema에서 config/read, skills/list, ThreadStartParams.config를 확인했다.

## P1 — 저장·상속

새 업무는 항상 standard가 기본이다. 선택값은 SQLite tasks.context_json에 저장하며 하위 직원·최종 검토 업무는 동일 스냅샷을 상속한다. 누락된 이전 업무는 standard, 잘못된 값은 접수/실행 전에 거절한다. 동일 요청 ID의 모드 변경도 거절한다. 후속 대화는 새 업무이므로 새 선택을 적용하며 기존 업무는 바꾸지 않는다.

예약에는 browser_mode 컬럼을 추가했다. 기존 예약은 standard이고 예약 회차는 저장한 모드를 전달한다. 기존 승인함·작업 사본·네이버 Python 자동화는 유지한다. ego 업무에서 등록 Playwright/유형 불명 외부 명령 action으로 자동 전환하는 것은 중단한다. 명시적으로 등록한 office:github 반영은 브라우저 전환이 아니므로 기존 경로를 유지한다. 해당 연결 작업은 기본 모드의 새 지시로 실행한다.

## P2 — 구현한 제한과 남는 경계

1. 공식 app-server config/read·skills/list로 현재 작업 디렉터리의 설정/스킬을 조사한다. 원본 설정은 메모리에서만 다룬다.
2. 실제 스킬 경로를 skills.config의 enabled=false/true로 업무 실행 인자에 전달한다. 관련 MCP는 이름·실행 명령·인자·URL 및 스킬의 MCP 의존성에서 찾고 기본 모드에서 enabled=false를 전달한다. 관계없는 설정은 유지한다. ego 모드라도 사용자가 비활성화한 MCP를 자동 활성화하지 않는다.
3. 새 Codex 프로세스의 실효 설정과 스킬 목록을 다시 확인한다. 적용 실패는 추론 시작 전에 중단한다. exec와 appserver 모두 같은 -c 설정을 전달한다. 전역 config.toml이나 CODEX_HOME/auth 파일을 수정·복사하지 않는다.
4. 검증 버전 이외에는 브라우저 정책을 검증했다고 실행하지 않는다.

**이것은 스킬/MCP 카탈로그 제한이다. 호스트 셸·임의 Python/Node 코드의 OS 격리는 아니다.** ego는 MCP만 쓰는 제품이 아니라 로컬 ego-browser CLI도 제공한다. 셸 도구를 유지한 상태에서 절대 경로 실행, 임의 코드가 직접 여는 브라우저 통신까지 이 설정으로 막았다고 주장하지 않는다. ego 모드에서 다른 브라우저에 대한 모든 셸 접근을 막았다는 의미도 아니다. 해당 강한 실행 격리 완료 전에는 P2 전체 완료 또는 두 엔진의 완전한 상호 격리를 선언할 수 없다. 대표가 PC에서 복구 결과를 확인할 수 있도록 v0.20.1에 배포하지만, 이 강한 격리 조건이 완료됐다는 의미는 아니다.

스킬 숨김만으로 Windows의 CLI 실행까지 차단됐다고 보고하지 않는다. 사용자 PC에서 검증된 OS 제어 또는 공식 실행 허용 목록이 추가로 필요하다. 단순 PATH 삭제, 이름 변경, 프롬프트, 사후 로그 검사로 대체하지 않았다. 승인 거절 뒤 다른 도구로 전환하는 로직도 추가하지 않았다.

## P3 — 진단

프로젝트 화면의 ego 진단은 설치(ego-browser 탐색), 설치본의 공식 skill 가이드, Codex 스킬 인식, 연결(listTabs), 명시적 공개 페이지 읽기(example.com)를 구분한다. 설치 가이드에 API가 없으면 추측하지 않고 미지원으로 중단한다. 연결만 됐으면 CONNECTED, 실제 공개 페이지 본문까지 읽었으면 READY다. AUTH_REQUIRED/POLICY_BLOCKED/CONNECTION_FAILED를 분리한다. 프로세스 목록으로 실행 상태를 추정하지 않으며 연결 성공 시만 running=true, 나머지는 unknown(null)이다. 호출 실패 원문, 탭 목록, 쿠키·토큰은 저장하지 않는다. 마지막 결과만 SQLite 메타데이터에 저장한다.

진단은 대표가 버튼으로 요청한 로컬 검사다. 직원 업무 중 실제 사이트 추가 승인은 기존 실행기 정책을 그대로 따른다. exec 방식의 대화형 입력 한계는 바뀌지 않았다.

## P4 — 직원·승인

업무별 모드와 카탈로그 검증 결과를 실행 증거에 기록한다. app-server 승인함, 거절 시 중단, 대기·만료·연결 실패 처리 구조는 유지했다. 사용자 지시의 게시 승인과 실행기 접근 승인은 서로 대체하지 않는다. ego 연결 실패는 다른 도구로 폴백하지 않는다.

## P5 — 관측 시간

browser_timing은 전체 실행 경과와 도구 시작/완료 이벤트 사이의 관측 시간을 기록한다. MCP 브라우저/ego-browser CLI 호출 수를 기록하며 앱서버와 exec JSONL 양쪽을 지원한다. 취소·실패에서도 확보한 요약을 남긴다. app-server 승인 대기 시간은 따로 관측해 approval_wait_ms에 기록하며 도구 왕복 시간에도 포함될 수 있다. 준비 시간은 browser_policy.preparation_ms에 기록한다.

개별 페이지 이동·스냅샷·클릭·사이트 대기·AI 추론 시간은 설치본이 제공하지 않으면 null이다. CLI 한 번 안의 여러 조작을 호출 한 번으로 집계한다. reasoning 아이템 경과는 모델 내부 추론 시간으로 이름 붙이지 않는다. 병렬 호출 시간 합계는 전체 시간보다 클 수 있다. 실제 병목은 관측값을 모은 뒤 판단해야 하며 체감 속도 개선을 검증했다고 주장하지 않는다.

불필요한 Task Space 재생성과 중복 스냅샷을 줄이라는 직원 지침을 추가했다. 엔진 자동 전환이나 사용자 세션 삭제·재시작은 추가하지 않았다.

## P6 — 재현·남은 Windows 실사용 검사

- 단위/회귀: `python -m unittest discover -s scripts/tests -v`
- 정적: `python scripts/build_release_manifest.py --check`, `node --check site/runtime.js`
- 실제 Codex 카탈로그 계약: `python -m scripts.probe_browser_modes --codex <0.163.0 실행파일>`
- 브라우저 UI 모형: `python -m scripts.test_web_office`

카탈로그 계약 검사는 임시 CODEX_HOME에 만든 가짜 ego 스킬/MCP 설정을 실제 CLI로 읽어 양 모드의 enabled 상태를 비교한다. 사용자 인증·모델 추론·실제 ego는 사용하지 않는다. 이 테스트는 실제 ego CLI 실행 차단 또는 실제 페이지 접근의 성공 증거가 아니다.

Windows에서 아직 확인할 사항:

- 실제 설치 스킬 경로, Windows CLI shim 실행, 연결 성공 및 공개 페이지 READY.
- Codex app-server에서 ego 실제 탐색과 승인 왕복; 거절 후 중단.
- ego 설치 상태의 기본 업무·기존 네이버 연결 회귀.
- 셸/임의 코드에서도 ego CLI가 실행되지 않는 강한 격리.
- 실제 클릭/입력·이동 병목 측정. 게시·삭제 같은 외부 변경은 별도 업무 범위에서 시험한다.

## 공식 근거

- https://learn.chatgpt.com/docs/config-file/config-reference — skills.config, mcp_servers.enabled, -c 설정.
- https://learn.chatgpt.com/docs/build-skills — 스킬 비활성화.
- https://lite.ego.app/document/en/docs/custom-agent-harness — 로컬 ego-browser와 공유 스킬 경로.
- https://lite.ego.app/document/en/docs/ego-browser — nodejs, listTabs, Task Space, 공개 페이지/스냅샷 API. 실행 시 설치본 skill 가이드를 우선한다.
