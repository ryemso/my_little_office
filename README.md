# My Little Office
직무별 AI 직원과 함께 제품·서비스 사업을 진행하기 위한 작은 사무실.

## 사무실
GitHub Pages 공개 화면: https://ryemso.github.io/my_little_office/

현재 버전은 **설계 확인용 인터랙티브 사무실**입니다. 실제 에이전트 실행·외부 발송·매출 발생 기능은 연결 전입니다.

## 목적
대표가 목표를 정하면 총괄이 실행 업무로 구체화하고, 직무별 담당자가 결과물을 만들고 검토하는 회사를 설계합니다. 게임뿐 아니라 웹 도구, 자동화, 데이터 분석 서비스, 디지털 상품을 사업 대상으로 합니다. 수익은 실제 고객·거래 증거로 확인하며 가상 수치와 구분합니다.

## 프로젝트 기록
- [회사 및 운영 설계](docs/COMPANY.md)
- [직무별 설계](docs/ROLES.md)
- [시스템 및 데이터 설계](docs/ARCHITECTURE.md)
- [결정 기록](docs/DECISIONS.md)
- [개발 계획](docs/ROADMAP.md)
- [작업 기록](docs/WORKLOG.md)

설계·결정·구현·검증 결과는 이 저장소에 기록합니다. 비밀 키, 비밀번호, 개인정보, 고객 비공개 자료와 실행 원본 로그는 공개 저장소에 올리지 않습니다. 이를 제외한 작업 경과를 비식별화해 남깁니다.

## 배포
main 변경 → GitHub Actions 검사 → GitHub Pages 배포.
처음에는 Settings → Pages → Source를 GitHub Actions로 설정해야 합니다.
Pages는 공개 정적 화면입니다. 서버 비밀 키와 실행 권한을 보관하거나 지속 에이전트를 실행하는 용도로 사용하지 않습니다.

## 로컬 확인
`python3 -m http.server 8000 --directory site` 실행 후 http://localhost:8000 에 접속합니다.
