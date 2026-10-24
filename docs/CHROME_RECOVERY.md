# 기존 Chrome 연결 복구와 ego 설치 이후 장애 분석

2026-10-24 · v0.20.1. 대표의 update-office.bat 적용 지시에 따라 검증된 수정본을 main 업데이트 대상으로 배포한다. Windows 실사용 확인과 OS 격리 미완료 상태는 유지한다.

## 결론과 증거 범위

확인된 장애는 로그인 실패/사이트 접근 거절이 아니라, 직원이 읽은 Browser 스킬이 요구한 `mcp__node_repl__js`를 찾지 못한 것이다. 사용자가 제공한 실무 기록은 single/workspace-write이며 PowerShell과 파일 작성은 성공했다. 따라서 총괄 계획 단계의 shell_tool=false만으로는 이 실무 장애를 설명할 수 없다.

이전에 제공한 성공 기록은 mcp__cua_repl을 통해 기존 Chrome 탭·본문·스크린샷을 확인했다. 현재 장애 기록은 26.1021.31345 Browser 패키지의 control-in-app-browser 지침을 읽었으며 node_repl을 요구한다. **현재 지침의 실행 의존성과 이전 성공 도구가 다르다는 사실은 확인되지만, 사용자 PC의 설치 전후 config/MCP 상태가 없으므로 도구가 사라진 원인은 확정하지 않는다.** 두 스킬 패키지의 종류가 다른 경우 버전 숫자만 비교해 업데이트를 단정하지 않는다.

직전 설명에서 내장 Browser의 CLI 지원 제한을 기존 외부 Chrome/CUA 연결 전체로 일반화한 것은 부정확했다. 실제 기존 연결이 작동했던 증거를 우선한다. Playwright MCP/새 확장 설치를 필수 해결책으로 도입하지 않는다.

## 원인별 판단

| 후보 | 확인된 근거 | 판단 |
|---|---|---|
| ego가 Chrome 제어 MCP를 삭제/비활성화 | 설치 전후 MCP 설정 증거 없음 | 직접 원인 미입증 |
| ego 스킬의 우선 사용 지침 | 공식 스킬은 ego 우선 사용을 안내하고, 사용자는 ego 경로 수행·지연을 보고함 | 경로 선택 변화의 설명은 가능. cua/node 도구 미제공 원인과는 구분 |
| 플러그인/실행 환경 의존성 불일치 | 이전은 cua_repl 성공, 현재 문서는 node_repl 요구·검색 실패 | 증상상 확인됨. 실제 설치 변경/서버 시작 실패 여부는 PC 진단 필요 |
| 오래된 플러그인 cwd 또는 선택적 MCP의 지연 시작 | 공식 MCP는 cwd/required를 지원. 비슷한 공개 보고가 있으나 사용자 PC의 해당 오류는 없음 | 조건부 복구 대상, 이번 장애 원인으로 단정하지 않음 |
| 작은 회사 PR의 ego 차단 코드 | main=f2eb991(v0.19.3), 모드 선택 PR은 미병합. 제시된 로그에 browser_mode/새 진단 정보 없음 | 일반 main 업데이트에는 PR 코드가 포함되지 않음. PC 코드의 별도 수정 여부는 미확인 |
| Windows 기본 URL 앱 선택 | 사용자가 ego 설치 후 앱 선택창을 보고함 | 사무실 URL을 어느 앱에서 여는지와 직원 MCP 도구 제공을 구분해야 함 |

외부 글 https://windowshyun.tistory.com/123 (2026-07-25)의 충돌 방지는 사용자 탭/에이전트 Space 분리다. 기존 Chrome MCP 소실을 증명하지 않는다. 동작 배치/세션 재사용은 성능 참고 사항이며, 당시 macOS 설치법과 오래된 API를 현재 Windows 설치본에 그대로 적용하지 않는다.

## 구현한 복구 경로

- 기존 계정·브라우저·ego 설치·전역 Codex 설정은 유지한다. 새 MCP나 확장은 설치하지 않는다. 앱은 전역 MCP 설정을 쓰지 않는다. Codex 자체가 스레드 시작 시 프로젝트 등의 메타데이터를 갱신할 수 있으므로, 계약 검사는 전체 파일의 바이트 동일성 대신 MCP 등록 내용의 동일성을 검사한다.
- `mcpServerStatus/list`로 실제 직원 스레드의 기존 cua_repl/node_repl 카탈로그를 첫 모델 턴 전에 확인한다. 실패/권한 거절이면 후속 문서 제작·게시를 시작하지 않는다. 실제 브라우저가 필요한 계획 단계에는 browser_required를 표시하도록 했다.
- **이미 설정되고 활성화된** 기존 브리지만 실행 단위로 required=true로 준비한다. 비활성화된 서버를 자동 활성화하지 않고 없는 command/env를 추측·재구성하지 않는다.
- cwd가 없거나 버전별 plugins/cache 아래에 있고 런처 인자가 절대 경로인 경우에만 같은 브리지의 cwd를 사무실 데이터의 안정된 위치로 지정한다. 상대 런처 파일이 있으면 바꾸지 않는다. 새 프로그램을 찾거나 내부 포트를 추측하지 않는다.
- 기존 cua_repl이 명시적으로 설정된 경우, node_repl만을 요구하는 Browser 스킬은 해당 업무에 한해 비활성화하여 현재 도구와 충돌하는 지침을 선택하지 않게 한다. 실제 도구 확인 실패는 중단하며 ego/다른 도구로 재시도하지 않는다.
- 기존 승인함을 그대로 사용한다. 브라우저 진단의 권한 요청도 임의 승인하지 않는다.

`TOOLS_READY`는 MCP 클라이언트의 도구 목록 확인이다. 모델의 최종 지연 도구 목록에 노출됐다는 증명이나 사이트 접근 성공과는 다르다. 별도 검사 없이 성공으로 합치지 않는다.

## 사용자 PC에서 실행되는 구체적 점검

사무실의 **기존 Chrome 연결 복구 → 기존 Chrome 연결 진단·복구**를 누르면 개발 직원의 전용 진단 업무가 접수된다. 모델 추론 없이 공식 app-server API로 기존 도구를 조회하고, 실제 cua_repl js가 있으면 `await cua.getState();` 한 번을 호출한다. 계정 로그인, URL 이동, 게시, 세션 삭제는 수행하지 않는다. 추가 승인은 기존 승인함에서 처리한다.

| 결과 | 의미 |
|---|---|
| BRIDGE_NOT_PROVIDED | 기존 브리지 자체가 실행 목록에 없음. 설치 문서만 있는 상태와 구분 |
| TOOL_MISSING / CONNECTION_FAILED / LAUNCH_PATH_ERROR | 등록은 있지만 js 미제공 또는 시작/경로 실패 |
| AUTH_REQUIRED / POLICY_BLOCKED | 인증·정책 문제. 다른 엔진으로 우회하지 않음 |
| LEGACY_CUA_MISSING | 새 node_repl은 보이지만 이전 cua 경로는 복구되지 않음 |
| STATE_CALL_OK | 실제 도구 호출 성공. Chrome 연결을 구조적으로 확인하지 못함 |
| CHROME_CONNECTED | 실제 도구 응답의 browsers 목록에서 Chrome 연결 확인. 사이트 본문/게시 성공은 별도 |

호출 응답의 탭 제목·주소·본문·인증 값은 저장하지 않는다. 저장하는 것은 상태, 도구 이름, 스킬 버전/해시, CLI/앱 버전, 복구 조치 종류 및 연결 확인 여부뿐이다. 이후 성공 스냅샷과 변경을 비교할 수 있지만 상관관계를 ego의 인과관계로 단정하지 않는다. 현재 업무와 다른 이전 성공 결과를 실행 증거로 재사용하지 않는다.

## 검증과 남은 한계

- 단위/회귀: `python -m unittest discover -s scripts/tests -v`
- 실제 고정 Codex + 합성 MCP: `python -m scripts.probe_chrome_connection --codex <0.163.0 실행파일>`
- UI: `python -m scripts.test_web_office`

합성 MCP는 진짜 Chrome이 아니다. 이 테스트로 사용자 Windows에서 기존 Chrome 재접속이 완료됐다고 주장하지 않는다. 사용자 PC의 비공개 config, 설치 기록, 실제 도구 상태에는 이 개발 환경이 접근할 수 없다. 현재 브리지가 등록돼 있지 않거나 데스크톱 호스트가 제공하지 않는 경우, 앱 코드만으로 비공개 호스트 서비스를 만들어낼 수 없다. 진단 결과로 해당 경우를 분리한다. 임의 셸 실행까지 포함하는 P2의 OS 격리 미완료 사항도 그대로 남는다.

## 공식 참고

- https://learn.chatgpt.com/docs/app-server — thread-scoped mcpServerStatus/list, mcpServer/tool/call, config/mcpServer/reload.
- https://learn.chatgpt.com/docs/extend/mcp — enabled, required, cwd와 서버 연결 설정.
- https://learn.chatgpt.com/docs/browser — 내장 Browser와 외부 브라우저 확장 표면 구분.

실제 0.163.0 기능 목록에서 js_repl은 removed/false였다. 따라서 그 플래그를 켜면 mcp__node_repl__js가 새로 생긴다는 복구 방법은 사용하지 않았다.

## v0.20.4: Windows launch-path evidence and batch review

Owner PC v0.20.3 returned thread/start -32603: required node_repl failed to initialize, Windows os error 3. This confirms a launch path failure, not an origin approval rejection. The missing path itself is not present in that response. Diagnostics now inspect the registered executable and script file existence, without logging environment variables or raw arguments. A missing absolute node/node.exe registration may use the same executable name resolved on PATH for this invocation only. Missing plugin scripts are not reconstructed, installed or redirected to a different browser. The owner PC must run the updated probe to determine the remaining missing component. Ego causing the path change remains unproven.

The review inbox now supports selecting multiple submitted results and completing review in one transaction, with displayed-version checks. Stale, running, approval and child tasks are rejected. This does not apply files, publish content or grant runtime permissions.
