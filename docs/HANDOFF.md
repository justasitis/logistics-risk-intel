# Logistics Risk Intelligence — 세션 핸드오프

> 새 세션에서 이 문서를 첨부하면 바로 이어서 작업할 수 있다.
> 최종 갱신: 2026-07-28 작업분까지 반영 (VDI repo 최신 커밋: 61c3553)

---

## 1. 프로젝트 개요

- **목적**: SK온 Global물류팀의 물류 AI Agent 3개 과제(물류정보 이상탐지 / 물류 MI Report / B/L Tracking)를 통합한 웹앱. VDI 폐쇄망 운영.
- **1차 사용자**: 구매원 — "내 화물이 납기에 맞춰 잘 오는가, 선박이 리스크 영향권인가"
- **원칙**: HITL("AI는 추천, 사람은 결정"), 판정 로직 단일 주체(백엔드), 메일 주소록 같은 중앙 구독 관리 금지

## 2. 두 개의 repo와 작업 흐름

| repo | 용도 |
|---|---|
| `github.com/lws2013/logistics-risk-intel` | **VDI판 (메인)** — 이 문서 기준 작업 대상 |
| `github.com/lws2013/logistics-risk-intel-v2` | 주말 샌드박스(Deepseek 검증용, 참고 자산) |

**로컬 폴터** (이 PC): `C:\Users\milkg\programming\deepseek_test\logistics-risk-intel\`
- `logistics-risk-intel-vdi/` ← VDI판 소스 (git init 상태, origin 연결됨)
- `logistics-risk-intel-v2/` ← 샌드박스
- `최초자료/` ← VDI에서 가져온 원본 파일들, B-LAP_all_tables/ (테이블 샘플)

**배포 흐름**:
```
이 PC에서 수정 → commit/push (GitHub)
→ 회사 노트북 C:\Work\logistics-risk-intel: deploy/01_Git-Pull.cmd
→ VDI C:\dev\logistics-risk-intel: deploy/02_VDI-Deploy.cmd
   (\\Client\C$\Work\logistics-risk-intel 에서 robocopy 증분 복사 → npm build → pip(조걶) → 재기동)
```
- 삭제/리네임 커밋에는 메시지에 `VDI 수동 삭제: <경로>` 명기 규칙.

## 3. 현재 상태 (커밋 61c3553 기준)

- **백엔드**: FastAPI (api_server.py + services/ + backend/app/), pytest **288개 전부 통과**
- **프런트엔드**: Vue3+Vite+TS (Pinia 없음), `npm run build` 통과. 워크스페이스 탭: 대시보드 / 외부 MI 정제 / 선박관리 / 재고 영향 / MI 리포트 / 경로 조회
- **주요 기능**: 지도(AIS+항로+MI 영향권), HBL 마스터-디테일, 납기 초과 신호(dlvy_eta vs dlvy_req_date만 비교), L2 재고 시뮬레이션(B-LAP 품목라인 연동), MI 이벤트 레지스트리(일자별 파일 종합+생명주기), 레지스트리 영향권 지도 표시+종합 정제(Actify 제안→수락), 리드타임 리포트(FCL 전용, arvl 포함 필수!), 시황 KCCI 주차 차트, 경로 마스터 조회, watchlist+알림센터+트레이 exe
- **exe 패키징**: build/Build-Package.ps1 (PyInstaller, 86MB, 팀원 무설치 배포용). 트레이 exe 포함.

## 4. 환경 제약/규칙 (중요 — 재발 방지)

- **searoute==1.4.3 고정** (algorithm 인자 없음). 한글 Windows pip 설치 시 `set PYTHONUTF8=1`
- **사내 Nexus**: pip `pypi-group-internal`, npm도 Nexus (`10.242.199.4:8987`). 새 의존성은 Nexus 존재 확인 필요
- **PS1은 UTF-8 BOM+CRLF**, **CMD는 BOM 없는 UTF-8+CRLF** + `chcp 65001` (한글 깨짐/파싱 오류 방지)
- **SharePoint 경로**: `{username}` 플레이스홀더 자동 치환 (user_path.py). 동기화 폴터명이 PC마다 다름("Global물류팀 - LogisticsRisk" / "SK on - LogisticsRisk") → resolve_synced_path가 자동 탐색 + Repair-SharePointPath.ps1이 junction 생성
- **SharePoint 루트**: `C:\Users\{username}\SK on\Global물류팀 - LogisticsRisk` — 하위: AIS\Marinesia\Current, MI\current(일자별 external_mi_candidates_YYMMDD.json), MI\mi_runs, MI\mi_event_registry.json, MI\freight_indices\freight_indices.json, MI\insight_drafts, watchlist\
- **프런트 규칙**: `as any` 금지, `--li-*` 테마 토큰만, `!important` 금지, 최소 폰트 11px(수치 12px), 신규 npm 의존성 금지, 시작 시 자동 조회 금지(명시 조회만)
- **백엔드 규칙**: 외부 호출 실패 시 남부 예외 문자열 노출 금지, 파일 쓰기는 atomic(tmp→os.replace), 500은 로그만
- **git 작업은 사용자 승인 후**, 커밋 author: `-c user.name="milkg" -c user.email="milkg@users.noreply.github.com"`
- 한국어 출력, 용어는 '통찰'. 문서/산출물에 이모지 금지

## 5. 핵심 데이터/매핑

- 법인 매핑: SKO→S000, SKOH→S210, SKBM→S220, SKBA→S330, SKOJ→S930, SKOY→S950 (datalake_schedule_client.COMPANY_NAME_TO_CODE)
- bl_info 주요 컬럼: cmpy_cd/nm, plnt_cd/nm, lsp_nm, sppl_nm, po_no, item_cd/nm, trpr_no, hbl_no, dprt/dprt_nm, arvl/arvl_nm, to_stlc_cd/nm, etd/atd/eta/eta_date/ata, dlvy_eta/dlvy_ata/dlvy_req_date, onboard_date, cargo_type3(FCL/LCL만), stopby, lf_date, dg_yn
- 변경이력(his): trpr_no, his_type(ETA/ETD), fr_date, to_date, ins_datetime, ins_person_id(IF_*=인터페이스). fr==to는 변경 아님. 최초등록행(fr_date 공란) 유지
- Denodo 0건 응답 `{"elements":[]}` 파싱 주의(이미 수정됨)
- 환경변수는 루트 `.env` 통합 (.env.example 참고, DATALAKE_USERNAME/PASSWORD, ACTIFY_* 등)

## 6. 미해결/다음 작업 후보

1. **수치 대조** (사용자 진행 중): MI 리포트 리드타임 vs 수기 월간 리포트 — 그룹핑/정의 조정 예상 (리포트 전문: `Monthly 물류 Lead Time 리포트.txt`, 마커 [[ROW]][[COL]][[BR]])
2. **Actify 실호출 검증**: MI 정제 v2.1 프롬프트, 인사이트 초안, 레지스트리 종합 정제 — VDI에서만 가능
3. **소진 확정 알람**: `shortage = (dlvy_eta − dlvy_req_date) − Item별 최저 재고 보유일` ≥ 임계일(5일). **Item 샘플은 사용자가 전달 예정** — 기준정보는 inventory_stock_params.json 구조 확장, feed에 타입 추가
4. **포트 코드**: 대풍항은 CNDFG(타리프 기준) — CNDAF와 병기 필요
5. **AD-07 메일 통보**: 임원/팀장 고정 소수 수신자용 월간 리포트 메일만 해당(운영 알림은 풀 모델 확정)
6. **경로 마스터 캐시 외 후속**: 행 상한 초과 시 안내
7. **SCM Orchestrator 시나리오** (본부장 요구) — 회의록 텍스트 대기 중
8. 과거 사례 기반 지연 예측(팀장 비전): MI 레지스트리×지연이력 상관 — 데이터 축적 후

## 7. 이 PC 환경

- Windows + Git Bash, Python 3.12, Node 22
- vdi venv: `logistics-risk-intel-vdi/.venv` (`.venv/Scripts/python`)
- 테스트: `cd logistics-risk-intel-vdi && .venv/Scripts/python -m pytest tests -q`
- 빌드: `cd logistics-risk-intel-vdi/frontend && npm run build`
- gh CLI 없음 — push는 https remote로 동작 (credential manager 등록됨)

## 8. 협업 스타일

- 사용자: Global물류팀 기획자(수급 권한 없음). 코드 수정 지시 시 바로 작업, 검토 요청 시 답변만
- 작업 시작 전 TodoList로 추적, 완료 시 검증(테스트/빌드) 후 커밋
- 에이전트 활용 가능 (큰 작업은 coder subagent에 상세 브리핑으로 위임)
