# Logistics Risk Intelligence — 세션 핸드오프

> 새 세션에서 이 문서를 첨부하면 바로 이어서 작업할 수 있다.
> 최종 갱신: 2026-08-19 인계 반영 (직전 코드 커밋: 9470bc9, pytest 419개 중 416 통과·3 skip, npm build 통과)
> 매 세션 자동 적용되는 규칙 요약은 레포 루트 `CLAUDE.md` 참조 (이 문서 4·5·8장의 압축본)

---

## 1. 프로젝트 개요

- **목적**: SK온 Global물류팀의 물류 AI Agent 3개 과제(물류정보 이상탐지 / 물류 MI Report / B/L Tracking)를 통합한 웹앱. VDI 폐쇄망 운영.
- **1차 사용자**: 구매원 — "내 화물이 납기에 맞춰 잘 오는가, 선박이 리스크 영향권인가"
- **원칙**: HITL("AI는 추천, 사람은 결정"), 판정 로직 단일 주체(백엔드), 중앙 구독 관리 금지

## 2. repo와 배포 흐름 (필수)

- **repo (정본)**: `github.com/justasitis/logistics-risk-intel` (VDI판, 유일)
  - **인계 이력**: 원래 팀원 `lws2013` 계정에서 진행하던 과제를 인계받음. 이전 주소
    `github.com/lws2013/logistics-risk-intel`는 더 이상 정본이 아니다. 문서·스크립트에
    옛 주소가 남아 있으면 위 주소로 교체할 것
  - 커밋 author: 이 PC에서 직접 작업한 분은 `justasitis`. 단 클라우드 세션(Claude Code on the web)에서
    만들어진 커밋은 서명 검증 때문에 author가 `Claude <noreply@anthropic.com>`으로 남는다 —
    작성 주체 구분용이며 정상이다
- **로컬 폴더 (이 PC = 회사 PC)**: `C:\dev\logistics-risk-intel\` (repo 루트가 곧 작업 대상 소스, origin 연결됨)
  - 전임자 PC에 있던 참고자료 사이드 폴더(`최초자료/`, `mi_report_sample.html`,
    `old_json.txt`/`new_json.txt`, `delay_report.html`)는 이관하지 않았고 현재 불필요 판단.
    필요해지면 전임자에게 별도 요청

**배포 흐름**:
```
이 PC(회사 PC) C:\dev\logistics-risk-intel 에서 수정 → commit/push (GitHub, 현재 자동 진행)
→ 중계 PC C:\Work\logistics-risk-intel: deploy/01_Git-Pull.cmd
→ VDI C:\dev\logistics-risk-intel: deploy/02_VDI-Deploy.cmd
   (\\Client\C$\Work\logistics-risk-intel 에서 robocopy 증분 복사 → npm build → pip(조건부) → 재기동)
```
- 삭제/리네임 커밋에는 메시지에 `VDI 수동 삭제: <경로>` 명기 규칙. (그래서 미사용 파일은 디스크에 보존 중: AisUploadPanel.vue, GapPanel.vue)
- exe 패키징: `build/Build-Package.ps1` (PyInstaller, 팀원 무설치 배포용, 트레이 exe 포함). 시작 래퍼 `LogisticsRisk-시작.cmd`는 포트 8000 점유 프로세스 자동 종료 후 기동.

## 3. 현재 상태 (코드 커밋 9470bc9 기준)

- **백엔드**: FastAPI (`api_server.py` + `services/` + `backend/app/`),
  pytest **419개 수집 / 416 통과 / 3 skip / 0 실패** (2026-08-19 새 클론 재검증)
  - skip 3개는 재고(L2 수급 영향) API 테스트: `test_inventory_sim.py::test_api_items`,
    `::test_api_simulate_ok`, `test_inventory_arrivals.py::test_api_fallback_to_sample_on_blap_failure`
  - **사유**: 샘플 품목 마스터 `backend/data/inventory_items.json`이 git 미추적
    (`.gitignore`의 `backend/data/*.json`, `*.sample.json` 대응본 없음)이라 새 클론에서
    라우터가 항상 404를 반환한다. 코드 회귀가 아니라 데이터 파일 부재 문제이며,
    **재고 기능을 사용하지 않기로 해 skip 처리**했다. 기능 재개 시 샘플본을
    `inventory_items.sample.json`으로 추가하고 skip 마커를 해제할 것
  - 같은 파일의 `inventory_sim.simulate()` 순수 함수 테스트는 외부 파일 의존이 없어 그대로 통과
- **프런트엔드**: Vue3+Vite+TS, `npm run build`(vue-tsc 타입체크 + vite build) 통과 —
  149 모듈, 타입 오류 0. 타이틀 "Logistics Risk Intelligence", Edge `--app=` 앱 모드 실행
- **워크스페이스 탭**: 운송 이상·AIS / 외부 MI 정제(권한자만) / MMSI 관리 / 재고 영향(비활성화, 사용하지 않음) / MI 리포트 / 지연 추이 / 경로 조회 / 기준정보(권한자만)
- **권한**: `GET /api/me` → can_manage_mi (REPORT_PUBLISH_USERS env, 기본 so23132,so23364). 외부 MI 정제·기준정보 탭 비노출 + MI 리포트 게시 권한에 공통 사용
- **대시보드 (운송 이상·AIS)**: 법인 기본값은 '전체 법인', 명시 조회만. 지도(항로+AIS+승인 MI 영향권+레지스트리 영향권 토글), HBL 마스터-디테일(PO 번호 검색 지원, 요약은 PO·Item이 ETD 앞), HBL 선택 시 연결 선박으로 지도 이동(zoom 3). Timeline/MI 영향/원인 후보 탭. MI 영향 카드에 '연관기사 클릭' 링크
- **MI 리포트 탭**: 게시본(스냅샷) 중심 — 일반 사용자는 게시본 열. 관리자 흐름: 새로고침(라이브 재집계, 미게시 배너) → 셀 편집 → 인사이트 초안 생성·편집·저장 → 게시본 갱신(서버가 게시 시점 재집계해 저장). 금월 핵심 변동은 유럽/미주/아시아 권역별 카드. 이벤트 지도는 **승인 이벤트** 기반(`GET /api/mi/approved/map-zones`, valid_to 경과 제외), 팝업 기본 표시+드래그 이동+연관기사 링크. 시황 3그래프
- **지연 추이 탭**: 도착지연 분해 & 선사 정시성 (주차 Gap 탭 대체됨, GapPanel은 파일만 보존). 항로 그룹 드롭다운(`GET /api/anomaly/delay-decomposition/groups` 경량 엔드포인트로 마운트 시 목록만 조회) + 명시 조회. 블록 A(항등식+분할 막대) / 블록 B(선사별 탄착군, P50/IQR/P90 설명 상단, 범례 위). 최초ETD/ETA는 이력 테이블 ins_datetime 최소 행 기준. 선사 통계는 항해 증감 분포. 판정문 임계값은 설정 파일
- **MMSI 관리 탭**: 법인 구분 없음. 대시보드 무관 독립 조회(`GET /api/vessels/inventory`, 전 법인). 선박명 항차번호 접미(2639W 등)는 canonical 정규화로 매칭·집계
- **기준정보 탭** (신규): SharePoint `config\` 폴더 기반 설정 저장소(config_store.py). 7개 키: route_groups / location_master / delay_thresholds / gap_thresholds / anomaly_thresholds / companies / carrier_inference. GET 전원·PUT/reset 권한자만, 검증 400 한국어, 저장 시 캐시 클리어, 기본값 되돌리기
- **트레이**: watchlist 알림 폼링(기본 600초), '지금 확인'=즉시 폼링, '앱 열기'=Edge 앱 모드

## 4. 환경 제약/규칙 (중요 — 재발 방지)

- **searoute==1.4.3 고정** (algorithm 인자 없음). 한글 Windows pip 설치 시 `set PYTHONUTF8=1`
- **사내 Nexus**: pip `pypi-group-internal`, npm도 Nexus (`10.242.199.4:8987`). 새 의존성은 Nexus 존재 확인 필요
- **PS1은 UTF-8 BOM+CRLF**, **CMD는 BOM 없는 UTF-8+CRLF** + `chcp 65001` (Build-Package.ps1 인코딩 사고로 BOM 재확인 완료)
- **SharePoint 루트**: `C:\Users\{username}\SK on\M365_TtNUJmLE - 데이터_접근금지` — 하위: AIS\Marinesia\Current, MI\current(일자별 후보), MI\mi_runs, MI\mi_event_registry.json, MI\map_labels.json, MI\report_snapshot.json, MI\freight_indices\, MI\insight_drafts, watchlist\, **`config\`(기준정보 사용자 지정 설정 — VDI 재배포에도 유지됨)**
  - `{username}` 자동 치환 (user_path.py). 마커(`logisticsrisk`, `데이터_접근금지`)로 자동 탐색
  - **VDI의 실제 `.env`도 새 경로로 갱신 필요** (env가 기본값에 우선)
- **AIS Marinesia**: 신 포맷(2026-08~)은 company 필드 없음(관리자 1인 단일 파일). 법인 필터 제거됨, `registered_mmsi_no`→조회 MMSI. 구 포맷은 하위호환
- **날짜변경선**: searoute는 180° 초과 연속 경도 반환 → `services/geo_antimeridian.py` 공용 정규화(±180 분할 MultiLineString)를 overview(dashboard_geo_service)와 stopby(stopby_route_builder) 양쪽에 적용
- **프런트 규칙**: `as any` 금지, `--li-*` 테마 토큰만, `!important` 금지, 최소 폰트 11px(수치 12px — 전체 일괄 적용 완료), 신규 npm 의존성 금지, 시작 시 자동 조회 금지(명시 조회만; 설정·권한 조회는 허용)
- **백엔드 규칙**: 외부 호출 실패 시 내부 예외 문자열 노출 금지, 파일 쓰기는 atomic(tmp→os.replace), 500은 로그만
- **git**: 코드 수정·검증 완료 시 **커밋+push 자동 진행(사용자 승인 지침)**, 논리 단위 커밋.
  author는 로컬 git config에 설정되어 있으므로 `-c user.name=...` 오버라이드를 붙이지 말 것
  (전임자 기준의 `milkg` 지정은 폐기)
- 한국어 출력, 용어는 '통찰'. 문서/산출물에 이모지 금지

## 5. 핵심 데이터/매핑

- 법인 매핑: companies 설정(companies.json)이 단일 소스 — SKO→S000, SKOH→S210, SKBM→S220, SKBA→S330, SKOJ→S930, SKOY→S950. 프런트는 useCompanies 공유
- **bl_info 날짜 컬럼은 YYYYMMDDHHMMSS 14자리 문자열** → `$filter`는 `%Y%m%d` 접두 형식. 변경이력 뷰의 ins_datetime은 ISO
- trpr_mode: 100 해상만 리드타임·지연 추이 집계(공란·200·300 제외). 내륙 그룹은 row_groups가 자체 판별
- **유럽향(아드리아 도착) 추론** (carrier_inference 설정): stopby 우선 → 없으면 선박명 규칙(LSP 무관): CMA 포함 → CMAU/CMA CGM·수에즈, MAERSK 포함 → MAEU/Maersk Line·희망봉. 그 외는 어느 경유 그룹에도 미매칭(자연 제외)
- 리드타임 항로 그룹(route_groups 설정): ADRIA_SUEZ/ADRIA_CAPE(아드리아, HRRJK 포함), EU_NORTH(DEHAM/DEBRV/FRLEH/GRPIR), EU_INLAND, US_EAST/US_WEST, US_INLAND, CHINA_TO_KOREA(훼리=KRIFT 실측, 컨테이너 행은 exclude로 분리). 지연 추이 대상은 delay_target 플래그
- 국가 구분(첫 열): KR/CN/JP + ID/PL (사용자 지시로 원복됨 — 임의 추가 금지)
- 미주 출발국가 행: 한국/일본/인도네시아/북유럽(DE*+PL*+FI*) — 동남아 행은 사용자 지시로 제거됨
- 선박명 canonical: trim + 끝의 항차 토큰 제거 (`\s+\d{3,5}[A-Z]{1,2}$`)
- Denodo 0건 응답 `{"elements":[]}` 파싱 주의
- FastAPI list[str] Query는 반복 파라미터(`?dims=a&dims=b`)만 인식
- 환경변수는 루트 `.env` 통합 (`.env.example` 참고). 설정 파일 우선순위: 사용자 지정(SharePoint config\) > repo 기본 JSON

## 6. 미해결/다음 작업 후보

1. **VDI 실데이터 검증** (최우선): 지연 추이(최초ETD/ETA 이력 커버리지, 선사 코드 분포, UNMAPPED 비율), 리드타임 재집계 수치 vs 수기 월간 리포트 대조, KRPTK(평택) 훼리 여부 확인(현재 컨테이너 행으로 집계 중), 추론 규칙 적용 결과
2. **Actify 실호출 검증 (VDI에서만)**: 인사이트 신규 필드, 지도 라벨, 레지스트리 종합 정제, 정제 프롬프트(중국 연안 북/남 구분 지시)
3. **MMSI 마스터 저장소 이전 검토**: 현재 브라우저 localStorage — 사용자/PC 간 공유 안 됨. SharePoint 파일 이전 제안 상태(기존 저장분 마이그레이션 필요)
4. **소진 확정 알람**: shortage = (dlvy_eta − dlvy_req_date) − Item별 최저 재고 보유일 ≥ 5일. Item 샘플은 사용자가 전달 예정 — inventory_stock_params.json 구조 확장 + feed 타입 추가
5. **AD-07 메일 통보** (임원/팀장 월간 리포트 메일), SCM Orchestrator 시나리오(회의록 대기), 과거 사례 기반 지연 예측(데이터 축적 후)
6. 기준정보 3단계(프롬프트·판정문 문구 편집) — 보류 중
7. 기술 부채: App.vue 4000행+/api_server.py 2000행 분할, 미사용 파일(AisUploadPanel.vue, GapPanel.vue) 삭제(VDI 수동 삭제 명기 필요), 프런트 코드 스플릿, exe 패키징은 매번 Build-Package.ps1 재실행 필요(launcher/tray 변경분 포함)
8. 외부 Gemini 프롬프트의 위치 표기를 위치 마스터 코드로 제한하는 안내 (자유 형식 지명 누수 방지)
9. MI 이벤트 지도 아이콘: 도입했다가 위치 어긋남으로 원복(0c86b24) — 재도입 시 위치 정합성부터 검증할 것

### 인계 관련 (2026-08-19 추가)

10. **재고(L2 수급 영향) 기능 정리 범위 결정**: 기능을 쓰지 않기로 해 테스트 3개는 skip 처리했으나
    라우터·프런트 패널은 되살릴 여지를 남겨 그대로 보존 중. 완전 제거를 택할 경우의 범위는
    `backend/app/api/routes/inventory.py` + `backend/app/services/inventory_sim.py`·`inventory_arrivals.py`
    + `api_server.py`의 라우터 등록 + 프런트 재고 패널/탭 + `tests/test_inventory_*.py`
    + `backend/data/inventory_stock_params.sample.json` + `.gitignore`의 재고 항목.
    삭제 시 `VDI 수동 삭제: <경로>` 명기 필요. **미결정 상태 — 사용자 판단 대기**
11. **전임자 자산 인계 확인**: 옛 remote(`lws2013`)에 이 repo에 없는 브랜치·이슈·미푸시 작업분이
    남아 있는지, 참고자료(최초자료/ 등)가 다시 필요해지는지 확인 필요
12. **VDI·중계 PC의 origin 주소 갱신**: `deploy/01_Git-Pull.cmd`의 하드코딩된 `REPO_URL`은
    새 주소로 수정 완료. 다만 **이미 clone된 작업 폴더는 스크립트가 기존 origin을 그대로 쓰므로**
    중계 PC(`C:\Work\logistics-risk-intel`)와 VDI(`C:\dev\logistics-risk-intel`)에서 각각
    `git remote set-url origin https://github.com/justasitis/logistics-risk-intel.git` 실행 필요.
    (혹은 폴더를 지우고 스크립트가 새로 clone하게 둔다)
13. **PAT 만료 관리**: 이 PC는 PAT로 push하므로 만료 시 push 실패. 만료일과 갱신 주체를 정해둘 것

## 7. 이 PC 환경 (회사 PC)

- Windows + Git Bash, Python 3.12, Node 22
- repo 루트: `C:\dev\logistics-risk-intel` (전임자 PC의 `logistics-risk-intel-vdi/` 중첩 구조 없음)
- venv: repo 루트의 `.venv` → `.venv\Scripts\python`
  - 최초 구성: `set PYTHONUTF8=1` → `python -m venv .venv` →
    `.venv\Scripts\python -m pip install -r backend/requirements.txt`
    (한글 Windows이므로 `PYTHONUTF8=1` 선행 필수. numpy 2.5.1이 Python 3.12+ 요구)
- 테스트: `.venv\Scripts\python -m pytest tests -q`
- 빌드: `cd frontend && npm install && npm run build`
  - `package-lock.json`의 `resolved` URL이 사내 Nexus(`10.242.199.4:8987`)를 가리키므로
    **사내망에서만 설치된다**. 외부망에서는 Nexus 도달 불가로 실패
- Denodo/Actify는 VDI에서만 접근 가능 — 이 PC에서는 mock 테스트로 검증하고 실호출 확인은 VDI에서
- gh CLI 없음 — push는 https remote, **PAT(Personal Access Token)로 인증**
  (전임자 PC의 credential manager 등록 방식과 다름)

## 8. 협업 스타일

- 사용자: Global물류팀 기획자(수급 권한 없음). 코드 수정 지시 시 바로 작업, 검토 요청 시 답변만
- 작업 시작 전 TodoList로 추적, 완료 시 검증(테스트/빌드) 후 커밋+push (자동)
- 에이전트 활용 가능 (큰 작업은 coder subagent에 상세 브리핑으로 위임)
- 사용 설명서: `docs/사용설명서_v1.md` (스크린샷 삽입 가이드 포함, 사용자가 이미지 추가 중)
