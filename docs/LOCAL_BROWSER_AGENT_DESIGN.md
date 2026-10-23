# My Little Office — Windows Local Browser Agent 설계 (v0.18 제안)

작성일: 2026-10-23
상태: 설계 완료 / 구현·Windows 실사용 검증 전
기준: 기존 v0.17, docs/AUTOMATION.md, docs/WEB_OFFICE.md
참고 설계: pickle-com/credential-enclave (권한 최소화·비밀정보 분리·감사 로그의 원칙만 참조, Nitro Enclave 자체 미도입)

## 1. 목표와 기존 기능 보존

사용자 Windows PC만 실행 환경으로 사용한다. AI 직원이 브라우저 기반 업무를 수행하며 로그인 세션 만료 시 일반 로그인 재시도를 수행한다. MFA·CAPTCHA·신규 기기 확인은 사용자 개입으로 전환하며, 자동 우회는 하지 않는다.
- 유지: site/ 픽셀 사무실, office.web_server(127.0.0.1:8501), SQLite 업무 DB, Codex CLI, 직원별 대화, 대표 아바타 승인함, 예약/반복, 네이버 초안·발행·중복 검증.
- 확장: 네이버 전용 수동 로그인 기능을 공통 브라우저 서비스로 일반화. 기존 연결/승인 프로토콜과 네이버 발행 코드를 재사용.
- 비목표: 외부 서버 상시 운영, 비밀번호를 LLM 프롬프트에 넣기, MFA/CAPTCHA 우회, 사이트 정책 우회, 브라우저의 완전한 보안 격리 보장.

## 2. 논리적 구조

site/ 동일 웹 UI (GitHub Pages 또는 로컬)
  -> office.web_server 로컬 인증 API (loopback + 기존 연결 코드 + Origin 제한)
  -> SQLite Task/Run/Approval/Schedule
  -> Office Orchestrator (Codex 직원 판단; 허용된 구조화 명령만)
  -> Browser Policy Gate (대상 호스트, 계정, 동작, 승인 검증)
  -> Browser Worker (Playwright, 사이트별 adapter)
  -> Browser Session Manager (전용 profile, 비밀번호/쿠키 보안)
  -> 외부 웹사이트
  -> Audit Writer / Artifact Validator -> 기존 승인함·대화·결과

Node.js 브라우저 워커를 추가할 수도 있지만 현재 requirements.txt에 playwright==1.64.0이 있으므로 Python Playwright를 우선 재사용해 중복 런타임을 피한다.
Codex CLI는 판단과 업무 파일 작성에 사용; 브라우저/인증정보에 대한 임의 셸 접근 권한을 주지 않는다. 전용 툴 호출 브리지에서는 허용된 action schema만 수행한다. 기존 workspace-write와 비밀정보 파일 경계는 별도 프로세스·OS ACL로 강제할 필요가 있다.

## 3. 로그인 상태 기계

NEW -> PROFILE_CHECK -> AUTHENTICATED -> READY
PROFILE_CHECK -> LOGIN_REQUIRED -> CREDENTIAL_LOOKUP
CREDENTIAL_LOOKUP -> AUTO_LOGIN (동의한 사이트/계정만) -> AUTH_CHECK -> READY
CREDENTIAL_LOOKUP -> NEEDS_USER (자격증명 없음)
AUTO_LOGIN -> NEEDS_USER (MFA/CAPTCHA/기기확인)
AUTO_LOGIN -> AUTH_FAILED (최대 2회, 계정별 지수 백오프·쿨다운)
READY -> TASK_RUNNING -> VERIFY_RESULT -> COMPLETE
TASK_RUNNING -> SESSION_EXPIRED -> LOGIN_REQUIRED (쓰기 전 단계만 재개)
UNKNOWN_POST_RESULT -> RECONCILE_ONLY (자동 재게시 금지)

규칙:
1) 전용 브라우저 프로필은 사이트·계정별 분리; 업무 단위 동시 접근은 mutex 사용.
2) profile storageState/cookies/token, password, OTP seed는 로그/스크린샷/LLM 메시지/Git 커밋에 절대 포함하지 않는다.
3) 최초 로그인은 사용자 수동, 이후 자동 로그인은 사용자가 사이트·계정별 opt-in 한 경우만.
4) Windows Credential Manager/DPAPI 같은 OS 보호 저장소에 자격증명 보관; 복호화는 로그인 실행기 전용 프로세스에서만, 사용 후 메모리 최소화. 로컬 동일 사용자 권한 공격에는 완전한 격리 보장 없음.
5) 자동 로그인 실패 또는 사이트 정책에 따른 차단 시 NEEDS_USER. 비밀 입력이 필요한 페이지에서 AI가 내용을 생성하거나 임의 코드를 실행하지 않음.
6) 수동 인증 후 현재 체크포인트에서 복구. 브라우저 창 열어 사용자에게 명확히 로그인 대상 도메인 안내.
7) OS 로그인 후 start-office.bat으로 실행; PC 꺼져 있는 동안 예약은 실행되지 않음. 기존 missed-run 1건 정책 유지.

## 4. 브라우저 동작 보안

- 사이트별 allowlist hostname, path prefix, browser profile name, 작업 action 종류(read/draft/publish/delete/upload).
- 웹페이지 텍스트는 신뢰하지 않는 데이터: 페이지 내 “기존 지시 무시” 같은 내용은 실행하지 않음.
- 범용 AI 클릭은 읽기·탐색에 한정; 게시/삭제/결제/외부 전송은 사이트별 검증된 adapter와 정책 검사·승인 스냅샷 필요.
- 모든 변경 요청에 target URL, account alias, operation, content SHA-256, idempotency key, 승인 ID를 연결.
- 인증 화면·세션 파일·쿠키·입력값·개인정보 영역은 진단 캡처에서 가림/캡처 금지.
- 프롬프트나 사이트 HTML에 비밀번호 노출 금지; 원본 파일 접근 권한이 있는 Codex subprocess에는 credential store 경로 접근 금지(프로세스/ACL 격리 별도 설계).
- GitHub Pages는 UI만; 실행기는 loopback만 바인딩. 연결 코드 재시작 회전, origin whitelist 유지. 인증 코드가 비밀번호 금고 열기 권한을 직접 주지 않도록 별도 승인과 정책 필요.

## 5. DB 확장(기존 SQLite에 migration)

browser_accounts(id, provider, alias, allowed_hosts_json, profile_ref, login_method, auto_login_opt_in, status, last_verified_at)
browser_sessions(account_id, state, last_check_at, last_login_attempt_at, failures, cooldown_until)
browser_actions(id, task_id, account_id, op, target_url, payload_digest, approval_id, idempotency_key UNIQUE, state, checkpoint, created_at, updated_at)
browser_audit(id, action_id, event_type, timestamp, actor, before_state, after_state, result_ref, prev_hash, entry_hash)
user_attention(id, action_id, reason, site_origin, requested_at, resolved_at)

credential secrets는 DB에 저장하지 않으며 vault key reference만 저장한다. log hash chain은 위변조 감지 보조 수단이지 동일 PC 소유자의 기록 삭제/변조를 원천 차단하지 못한다. 강한 불변성은 별도 append-only 보관 필요.

## 6. 내부 인터페이스 제안

BrowserAction = {task_id, account_id, provider, action, target_url, payload_ref, payload_sha256, approval_id, idempotency_key}
BrowserResult = {action_id, status, confirmed_url?, validation?, screenshot_ref?, error_code?, requires_user?}
허용 action = open/read/extract/draft/save_draft/publish/upload/verify_existing (delete는 기본 거절)
에러 = LOGIN_REQUIRED, MFA_REQUIRED, CAPTCHA_REQUIRED, SESSION_EXPIRED, POLICY_BLOCKED, PAGE_CHANGED, TIMEOUT, UNKNOWN_OUTCOME, VERIFICATION_FAILED

## 7. 단계별 구현 순서와 인수 조건

P0 베이스라인: 현재 v0.17 회귀 테스트+로컬 웹 UI+Codex+기존 네이버 모형 테스트 통과, 백업.
P1 BrowserSessionManager: account별 프로필/잠금/세션 상태 감지/로그인 사용자 요청. 비밀정보 로그에 없음.
P2 Windows SecretStore: Credential Manager 또는 DPAPI wrapper, 계정별 opt-in, 등록/삭제/회전/실패 제한. 비밀번호 AI 입력 경로 없음.
P3 BrowserWorker adapter: 기존 네이버 임시저장/발행 기능 통합, read/draft/publish 권한 분리, HTML 변경 오류 분류.
P4 Policy+Approvals: 기존 대표 느낌표, 콘텐츠 해시 승인, 승인 후 수정 시 강제 재승인, 민감 작업 기본 거절.
P5 Audit+Recovery: 사전 로그, after-result 검사, idempotency, UNKNOWN_OUTCOME 재실행 금지, 재로그인 시 안전한 체크포인트만 이어가기.
P6 Office UI: 직원 작업 상태(접속 중/로그인 필요/대표 확인/작업 중/검증 중/완료), 연결 관리, 로그인 요청 알림.
P7 통합 테스트: 가짜 로그인 사이트 세션 만료·MFA·CAPTCHA·페이지 변경·지연·중복클릭·Windows 재시작·권한 거절; 네이버 실제 작업은 대표 계정에서 비공개/임시저장 테스트 후 승인 발행.
P8 추가 사이트: 도메인·기능·정책을 사이트별 adapter로 추가. 범용 사이트 자동 로그인 성공을 보장하지 않음.

## 8. 완료 정의

- 기존 사무실/DB/업무 승인/반복 업무 동작 훼손 없음.
- 단일 PC에서 전용 브라우저 기동, 만료 감지, 허용된 자동 로그인, 추가 인증 사용자 호출 가능.
- LLM 또는 공개 Pages에 비밀번호/쿠키/OTP 등 비밀값이 표시되거나 커밋되지 않음.
- 콘텐츠 승인 없이 외부 공개 발행 불가, 승인 후 본문 변경은 차단.
- 발행 후 결과 불명은 UNKNOWN_OUTCOME으로 안전 중단, 결과 조회를 통해서만 완료/재시도 결정.
- Playwright 모형 테스트 통과 후 Windows 실사용 검증 별도 보고.

## 9. 현재 사실과 미구현 구분

기존 docs/AUTOMATION.md는 네이버 전용 브라우저 수동 로그인·세션 재사용·임시저장/발행·중복방지·결과 검증을 기술한다. 단, 사용자 PC 로그인 및 실게시 검증은 완료된 것으로 보지 않는다. 이 문서의 비밀번호 자동 입력, 공통 사이트 계정 금고, generic BrowserWorker, 세밀한 정책 게이트는 신규 설계이며 현재 구현 완료를 의미하지 않는다.
