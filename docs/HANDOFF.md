# Logistics Risk Intelligence — 세션 핸드오프

> 새 세션에서 이 문서를 첨부하면 바로 이어서 작업할 수 있다.
> 최종 갱신: 2026-08-05 작업분까지 반영 (VDI repo 최신 커밋: 5fb20ed, pytest 316개 통과)

---

## 1. 프로젝트 개요

- **목적**: SK온 Global물류팀의 물류 AI Agent 3개 과제(물류정보 이상탐지 / 물류 MI Report / B/L Tracking)를 통합한 웹앱. VDI 폐쇄망 운영.
- **1차 사용자**: 구매원 — "내 화물이 납기에 맞춰 잘 오는가, 선박이 리스크 영향권인가"
- **원칙**: HITL("AI는 추천, 사람은 결정"), 판정 로직 단일 주체(백엔드), 중앙 구독 관리 금지

## 2. repo와 배포 흐름 (필수)

- **repo**: `github.com/lws2013/logistics-risk-intel` (VDI판, 유일)
- **로컬 폴더 (이 PC)**: `C:\Users\milkg\programming\deepseek_test\logistics-risk-intel\`
  - `logistics-risk-intel-vdi/` ← 작업 대상 소스 (origin 연결됨)
  - `최초자료/` ← VDI 원본 파일, B-LAP 테이블 샘플, datalake_table_구조(컬럼 딕셔너리)
  - `mi_report_sample.html` ← MI 리포트 구성 검토용 샘플 (가상 데이터)

**배포 흐름**:
```
이 PC에서 수정 → commit/push (GitHub, 현재 자동 진행)
→ 회사 노트북 C:\Work\logistics-risk-intel: deploy/01_Git-Pull.cmd
→ VDI C:\dev\logistics-risk-intel: deploy/02_VDI-Deploy.cmd
   (\\Client\C$\Work\logistics-risk-intel 에서 robocopy 증분 복사 → npm build → pip(조걶) → 재기동)
```
- 삭제/리네임 커밋에는 메시지에 `VDI 수동 삭제: <경로>` 명기 규칙.
- exe 패키징: `build/Build-Package.ps1` (PyInstaller, 팀원 무설치 배포용, 트레이 exe 포함).

## 3. 현재 상태 (커밋 5fb20ed 기준)

- **백엔드**: FastAPI (`api_server.py` + `services/` + `backend/app/`), pytest **316개 전부 통과**
- **프런트엔드**: Vue3+Vite+TS, `npm run build` 통과.
- **워크스페이스 탭**: 대시보드 / 외부 MI 정제 / 선박 MMSI 관리 / 재고 영향(비활성화됨) / MI 리포트 / 지연 추이 / 경로 조회
- **MI 리포트 탭**:
  - 프리미엄 디자인(그라디언트 히어로 + KPI 카드 4개 + 금월 핵심 변동 카드)
  - **게시본(스냅샷)**: 지정 사용자(so23132, so23364)만 "게시본 갱신"으로 SharePoint `MI\report_snapshot.json`에 리드타임+인사이트+Gap 저장. 다른 사용자는 집계 없이 게시본 열람 (권한 목록은 `REPORT_PUBLISH_USERS` env)
  - 권역별 리드타임 표: 유럽(아드리아 수에즈/희망봉 + 유럽 내륙 운송방식) / 미주(동안·서안 + 미주 내륙 동부/서부항만) / 아시아(선적구분: 북중국 컨테이너·훼리 고정값·남중국). 첫 열 구분자는 그룹별 상이(국가/운송방식/출발항만/선적구분)
  - 물류 이벤트 지도: 오프라인 세계 폴리곤 + 레지스트리 영향권, 권역 포커스 탭(전체/유럽·수에즈/지중해/미주 동안/미주 서안/아시아), **동그라미 클릭 → 팝업** (X·일괄 닫기)
  - 인사이트 초안(Actify): key_changes(핵심변화 3개) + 유럽/미주/아시아/주요 이벤트/리드타임 동향 + 항공 MI 있으면 [항공] 섹션 + 익월 체크 포인트. 초안 생성 성공 시 지도 라벨(간결 문구)도 Actify로 생성해 `MI\map_labels.json`에 저장
  - 시황: SCFI+KCCI 종합 / KCCI 북미 동안 / KCCI 지중해 3그래프(주차 눈금선) + 지표별 최신값·MoM·YoY 카드
  - 그룹 헤더에 ETA-ATA Gap 배지, HTML 출력/인쇄 (게시본 그대로보내기)
- **지연 추이 탭 (협의체장 요구)**: ETA−ATA Gap 주차 집계(완료 주 ISO), 평균 Gap·지연 건수 비율, 추세(연속 증가/기울기), 경고 룰(최근 주 평균 > 5일 → 경고, 3주 연속 증가 → 주의)
- **경로 조회 탭**: 구분조건(법인명/사업장/물류사/사업구분/운송모드 + 쌍 묶음 출발지/최종사이트 — 미선택 시 열 제외·재집계), 기간 달력, 열별 멀티선택 필터, 엑셀(CSV, BOM 포함) 다운로드
- **외부 MI 정제 탭**: SharePoint 후보 반입 → Actify 정제 → 검토·승인(위치/Lane 드롭다운 편집, 미해결 위치 멀티선택 매칭, 위치 마스터 API) → 레지스트리(일자별 파일 종합 생명주기, 상태 수동 변경 드롭다운, 종합 정제 Actify 제안→수락) → 영향권 지도
- **대시보드**: 지도(AIS+항로+MI 영향권), HBL 마스터-디테일, 납기 초과 신호, Timeline, watchlist+알림센터+트레이

## 4. 환경 제약/규칙 (중요 — 재발 방지)

- **searoute==1.4.3 고정** (algorithm 인자 없음). 한글 Windows pip 설치 시 `set PYTHONUTF8=1`
- **사내 Nexus**: pip `pypi-group-internal`, npm도 Nexus (`10.242.199.4:8987`). 새 의존성은 Nexus 존재 확인 필요
- **PS1은 UTF-8 BOM+CRLF**, **CMD는 BOM 없는 UTF-8+CRLF** + `chcp 65001`
- **SharePoint 루트**: `C:\Users\{username}\SK on\M365_TtNUJmLE - 데이터_접근금지` — 하위: AIS\Marinesia\Current, MI\current(일자별 후보), MI\mi_runs, MI\mi_event_registry.json, MI\map_labels.json, MI\report_snapshot.json, MI\freight_indices\, MI\insight_drafts, watchlist\
  - `{username}` 자동 치환 (user_path.py). 동기화 폴터명이 PC마다 다를 수 있어 마커(`logisticsrisk`, `데이터_접근금지`)로 자동 탐색 + Repair-SharePointPath.ps1이 junction 생성
  - **VDI의 실제 `.env`도 새 경로로 갱신 필요** (env가 기본값에 우선)
- **프런트 규칙**: `as any` 금지, `--li-*` 테마 토큰만, `!important` 금지, 최소 폰트 11px(수치 12px), 신규 npm 의존성 금지, 시작 시 자동 조회 금지(명시 조회만)
- **백엔드 규칙**: 외부 호출 실패 시 내부 예외 문자열 노출 금지, 파일 쓰기는 atomic(tmp→os.replace), 500은 로그만
- **git**: 코드 수정·검증 완료 시 **커밋+push 자동 진행(사용자 승인 지침)**, author `-c user.name="milkg" -c user.email="milkg@users.noreply.github.com"`, 논리 단위 커밋
- 한국어 출력, 용어는 '통찰'. 문서/산출물에 이모지 금지

## 5. 핵심 데이터/매핑

- 법인 매핑: SKO→S000, SKOH→S210, SKBM→S220, SKBA→S330, SKOJ→S930, SKOY→S950
- **bl_info 날짜 컬럼(etd/atd/eta/ata/onboard_date 등)은 YYYYMMDDHHMMSS 14자리 문자열** → `$filter`는 `%Y%m%d` 접두 형식 필수 (`YYYY-MM-DD`는 하한 묵과·상한 0건 버그였음). 변경이력 뷰의 ins_datetime은 ISO라 기존 형식 유지
- trpr_mode: 100 해상(확인), 200 육상/Direct Truck(추정), 300 Rail+Truck(확인). 항공 코드 미확인
- 리드타임 집계: cargo_type3 == 'FCL' + 해상 그룹은 trpr_mode 100만. 아웃라이어는 월별 버킷 IQR 방식(표본 4건 미만 미적용). 내륙 L/T = dlvy_ata − ata (예상: dlvy_eta − eta)
- 미주 항로(사용자 제공 표): 동안 USSAV/USCHS/USATL/USNYC, 서안 USLAX/USLGB, 출발국가 한국/일본/인도네시아/북유럽(DE*+PL*)
- Denodo 0건 응답 `{"elements":[]}` 파싱 주의
- FastAPI list[str] Query는 반복 파라미터(`?dims=a&dims=b`)만 인식 — 쉼표 결합 금지
- 환경변수는 루트 `.env` 통합 (`.env.example` 참고 — DATALAKE_*, ACTIFY_*, REPORT_PUBLISH_USERS 등)

## 6. 미해결/다음 작업 후보

1. **Actify 실호출 검증 (VDI에서만 가능)**: 인사이트 신규 필드(key_changes·아시아·항공 섹션), 지도 라벨 생성, 레지스트리 종합 정제, 정제 v2.1 프롬프트
2. **VDI 실데이터 확인**: 경로 조회(etd 필터 수정 후), 미주 서안/북유럽 매칭, 유럽 내륙 Direct Truck(200 추정) 수치, 지연 추이 탭 경고 판정
3. **수치 대조**: MI 리포트 리드타임 vs 수기 월간 리포트 — 권역 재구성 반영 후 잔여 차이 확인 (`Monthly 물류 Lead Time 리포트.txt`)
4. **소진 확정 알람**: shortage = (dlvy_eta − dlvy_req_date) − Item별 최저 재고 보유일 ≥ 5일. Item 샘플은 사용자가 전달 예정 — inventory_stock_params.json 구조 확장 + feed 타입 추가
5. **게시본 운영**: VDI에서 so23132로 첫 "게시본 갱신" 실행 필요
6. 포트 코드: 대풍항 CNDFG(타리프 기준) — CNDAF와 병기 필요
7. AD-07 메일 통보(임원/팀장 소수 수신 월간 리포트 메일만), SCM Orchestrator 시나리오(회의록 대기), 과거 사례 기반 지연 예측(데이터 축적 후)

## 7. 이 PC 환경

- Windows + Git Bash, Python 3.12, Node 22
- venv: `logistics-risk-intel-vdi/.venv` (`.venv/Scripts/python`)
- 테스트: `cd logistics-risk-intel-vdi && .venv/Scripts/python -m pytest tests -q`
- 빌드: `cd logistics-risk-intel-vdi/frontend && npm run build`
- Denodo/Actify는 VDI에서만 접근 가능 — 이 PC에서는 mock 테스트로 검증하고 실호출 확인은 VDI에서
- gh CLI 없음 — push는 https remote (credential manager 등록됨)

## 8. 협업 스타일

- 사용자: Global물류팀 기획자(수급 권한 없음). 코드 수정 지시 시 바로 작업, 검토 요청 시 답변만
- 작업 시작 전 TodoList로 추적, 완료 시 검증(테스트/빌드) 후 커밋+push (자동)
- 에이전트 활용 가능 (큰 작업은 coder subagent에 상세 브리핑으로 위임)
