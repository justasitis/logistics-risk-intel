# CLAUDE.md — 매 세션 준수 규칙

Logistics Risk Intelligence (SK온 Global물류팀 물류 AI Agent 통합 웹앱, VDI 폐쇄망 운영).
FastAPI(`api_server.py` + `services/` + `backend/app/`) + Vue3/Vite/TS(`frontend/`).

전체 맥락(프로젝트 개요, 현재 상태, 배포 흐름, 미해결/다음 작업 후보)은 **`docs/HANDOFF.md`** 참조.
이 문서는 매 세션 로드되므로, 자주 바뀌는 내용은 넣지 않는다.

---

## 1. 환경 제약 (위반 시 빌드/배포 사고)

- **searoute==1.4.3 고정**. 1.5+는 인자 불일치(`algorithm` 인자 없음). 버전 올리지 말 것
- 한글 Windows에서 pip 설치 시 `set PYTHONUTF8=1` 선행
- **사내 Nexus 경유**: pip `pypi-group-internal`, npm `10.242.199.4:8987`.
  신규 의존성은 Nexus 존재 확인이 필요하므로 **함부로 추가하지 말 것**
- **인코딩**: PS1은 **UTF-8 BOM + CRLF**, CMD는 **BOM 없는 UTF-8 + CRLF** + `chcp 65001`.
  스크립트 수정 후 BOM 유무를 반드시 재확인 (과거 Build-Package.ps1 인코딩 사고)
- Denodo/Actify는 VDI에서만 접근 가능. 그 외 환경에서는 mock 테스트로만 검증하고,
  실호출 확인은 VDI 몫으로 남긴다
- **`.env`는 읽지 말 것** (실제 사내 자격증명). 구조는 `.env.example` 참조

## 2. 프런트엔드 규칙

- `as any` 금지
- 색상·간격은 **`--li-*` 테마 토큰만** 사용
- `!important` 금지
- **최소 폰트 11px** (수치 표기는 12px)
- **신규 npm 의존성 금지**
- **시작 시 자동 조회 금지** — 명시 조회(사용자 액션)만. 설정·권한 조회는 예외로 허용

## 3. 백엔드 규칙

- 외부 호출 실패 시 **내부 예외 문자열을 응답에 노출 금지**. 500은 로그만 남기고
  사용자에게는 한국어 일반 메시지
- 파일 쓰기는 **atomic** (tmp 파일 작성 → `os.replace`)
- 판정 로직의 단일 주체는 백엔드. 프런트에서 판정 재구현 금지

## 4. 핵심 데이터 함정 (자주 재발)

- **`bl_info` 날짜 컬럼은 `YYYYMMDDHHMMSS` 14자리 문자열** → `$filter`는 `%Y%m%d` 접두 형식.
  단, 변경이력 뷰의 `ins_datetime`은 ISO
- **법인 매핑의 단일 소스는 `companies` 설정(companies.json)**: SKO→S000, SKOH→S210,
  SKBM→S220, SKBA→S330, SKOJ→S930, SKOY→S950. 프런트는 `useCompanies` 공유
- **`trpr_mode`: 100(해상)만** 리드타임·지연 추이 집계 대상 (공란·200·300 제외)
- **선박명 canonical**: trim + 끝의 항차 토큰 제거 (`\s+\d{3,5}[A-Z]{1,2}$`). 예: `... 2639W`
- **날짜변경선**: searoute가 180° 초과 연속 경도를 반환하므로 `services/geo_antimeridian.py`
  공용 정규화(±180 분할 MultiLineString)를 overview·stopby 양쪽에 적용할 것
- Denodo 0건 응답은 `{"elements":[]}` — 파싱 시 주의
- FastAPI `list[str]` Query는 **반복 파라미터**(`?dims=a&dims=b`)만 인식
- 설정 파일 우선순위: **사용자 지정(SharePoint `config\`) > repo 기본 JSON**
- 국가 구분/출발국가 행 구성은 사용자 지시로 확정된 값 — **임의 추가·삭제 금지**

## 5. 협업 스타일

- 사용자는 Global물류팀 기획자(수급 권한 없음). **코드 수정 지시면 바로 작업, 검토 요청이면 답변만**
- 작업 시작 전 **TodoList로 계획·추적**
- 완료 시 **검증(pytest + npm run build) 후 논리 단위로 커밋**
- **출력은 한국어**, 용어는 '통찰'(insight)
- **문서·산출물·커밋 메시지에 이모지 금지**
- 삭제/리네임 커밋은 메시지에 `VDI 수동 삭제: <경로>` 명기
  (증분 robocopy라 VDI에서 자동 삭제되지 않음)
