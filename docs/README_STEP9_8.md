# Step 9.8 — ETD·ETA 변경이력 조회 수정

## 수정 대상 문제

현재 Timeline 코드는 다음 이유로 일부 법인, 특히 SKBM의 ETD·ETA 이력을
0건으로 처리할 수 있다.

1. Denodo 조회 조건에 `cmpy_cd + plnt_cd + trpr_no`를 모두 사용한다.
2. History 원천의 회사·Plant 코드가 Snapshot과 다르면 결과가 누락된다.
3. `fr_date`가 비어 있는 최초 일정 등록행을 삭제한다.
4. 이력이 없을 때 현재 날짜를 최초·현재 양쪽에 표시해 실제 이력처럼 보인다.

이번 패치는 다음과 같이 수정한다.

```text
Denodo 조회
trpr_no 기준

조회 후
cmpy_cd/plnt_cd 정확 일치행이 있으면 우선
없으면 trpr_no 결과 유지

Overview History
trpr_no로 조회 후 Snapshot transport_key로 재매핑

History 정규화
ETA/ETD만 사용
fr_date가 비어 있는 최초 등록행 유지
DLVY_ETA, ATD 제외

UI
원천 이력 0건과 실제 변경 0회를 구분
```

## 패키지 파일

교체 파일:

```text
services/datalake_schedule_client.py
services/schedule_history_service.py
services/schedule_timeline_service.py
frontend/src/components/ScheduleTimeline.vue
```

수정 파일:

```text
api_server.py
frontend/src/types/dashboard.ts
```

---

## 1. 압축 해제

프로젝트 루트에서:

```powershell
$Zip="$env:USERPROFILE\Downloads\logistics_risk_step9_8_timeline_history_fix.zip"
$Extract=".\_step9_8_timeline_history_fix"

Remove-Item $Extract -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -LiteralPath $Zip -DestinationPath $Extract -Force

$Patch="$Extract\logistics_risk_step9_8_timeline_history_fix"
```

확인:

```powershell
Test-Path "$Patch\README_STEP9_8.md"
```

---

## 2. 적용 전 백업

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "$Patch\tools\backup_step9_8.ps1" -ProjectRoot (Get-Location).Path
```

---

## 3. Backend 서비스 파일 교체

프로젝트 루트에서:

```powershell
Copy-Item "$Patch\services\datalake_schedule_client.py" ".\services\datalake_schedule_client.py" -Force
Copy-Item "$Patch\services\schedule_history_service.py" ".\services\schedule_history_service.py" -Force
Copy-Item "$Patch\services\schedule_timeline_service.py" ".\services\schedule_timeline_service.py" -Force
```

---

## 4. api_server.py 자동 패치

```powershell
& "$Patch\tools\patch_api_server_timeline.ps1" -ProjectRoot (Get-Location).Path
```

변경 내용:

```python
from services.datalake_schedule_client import (
    fetch_bl_history_for_transport,
    fetch_bl_history_for_transports,
    ...
)
```

Timeline endpoint의 기존 코드:

```python
history_df = fetch_bl_history_for_transports(
    [(cmpy_cd, plnt_cd, trpr_no)],
    changed_from=date.today() - timedelta(days=history_days),
    max_rows_per_chunk=10_000,
)
```

변경 코드:

```python
history_df = fetch_bl_history_for_transport(
    trpr_no=trpr_no,
    cmpy_cd=cmpy_cd or None,
    plnt_cd=plnt_cd or None,
    changed_from=date.today() - timedelta(days=history_days),
    max_rows=20_000,
)
```

자동 패치가 기존 블록을 찾지 못하면 스크립트가 수동 변경 코드를 출력한다.

---

## 5. Frontend Timeline 파일 교체

```powershell
Copy-Item "$Patch\frontend\src\components\ScheduleTimeline.vue" ".\frontend\src\components\ScheduleTimeline.vue" -Force
```

타입 자동 보완:

```powershell
& "$Patch\tools\patch_dashboard_types.ps1" -ProjectRoot (Get-Location).Path
```

자동 패치가 타입 위치를 찾지 못하면:

```powershell
code "$Patch\PATCH_SNIPPETS\dashboard_types_step9_8.md"
code ".\frontend\src\types\dashboard.ts"
```

를 열어 안내된 선택 필드를 추가한다.

---

## 6. 로컬 코드 검증

```powershell
& "$Patch\tools\verify_step9_8.ps1" -ProjectRoot (Get-Location).Path
```

검증 내용:

```text
Backend 파일 존재
api_server.py 새 Timeline 함수 연결
Python 구문 검사
최초 일정행 유지 테스트
ETA/ETD 변경 횟수 테스트
Vue npm run build
```

---

## 7. FastAPI 실행

기존 데이터레이크 환경변수가 설정된 PowerShell에서:

```powershell
python -m uvicorn api_server:app --reload --host 127.0.0.1 --port 8000
```

---

## 8. 특정 Transportation No. API 테스트

예시:

```powershell
& "$Patch\tools\test_timeline_endpoint.ps1" `
  -TransportationNo "TR260619007" `
  -CompanyCode "S330" `
  -PlantCode "SN01"
```

중요 확인값:

```text
SourceRows          0보다 큼
NormalizedRows      0보다 큼
EtdSourceRows       실제 ETD 원천행 수
EtaSourceRows       실제 ETA 원천행 수
EtdChanges          실제 ETD 변경 횟수
EtaChanges          실제 ETA 변경 횟수
```

회사·Plant 조건 없이도 확인한다.

```powershell
& "$Patch\tools\test_timeline_endpoint.ps1" `
  -TransportationNo "TR260619007"
```

두 결과가 모두 이력을 반환해야 한다.

---

## 9. 앱 화면 검증

1. SKBM 법인을 선택한다.
2. 변경이력이 있는 운송건을 클릭한다.
3. Timeline 상단에서 `ETD N건 · ETA N건`을 확인한다.
4. 최초·현재 날짜가 실제 History와 일치하는지 확인한다.
5. 변경 Event에 `fr_date → to_date`가 표시되는지 확인한다.
6. 이력이 없는 운송건은 날짜를 복제하지 않고 아래 문구를 표시하는지 확인한다.

```text
데이터레이크에서 ETD·ETA 변경 이력을 찾지 못했습니다.
```

원천행은 있지만 실제 날짜 변경이 없는 경우:

```text
원천 이력은 있지만 실제 날짜 변경은 없습니다.
```

---

## 10. 정상 응답 예

```json
{
  "header": {
    "trpr_no": "TR260619007",
    "hbl_no": "..."
  },
  "history_source_row_count": 99,
  "history_row_count": 25,
  "etd": {
    "source_row_count": 2,
    "change_count": 1,
    "initial_date": "2026-06-26T00:00:00",
    "current_date": "2026-06-25T00:00:00"
  },
  "eta": {
    "source_row_count": 23,
    "change_count": 10
  }
}
```

`history_source_row_count`는 ETD·ETA 이외의 `DLVY_ETA`, `ATD` 등을 포함한
원천 전체 행 수다. `history_row_count`는 ETD·ETA로 정규화된 행 수다.

---

## 11. 이번 패치가 Dashboard 전체에도 미치는 효과

`fetch_bl_history_for_transports()`도 Transportation No. 중심 조회로 변경했으므로
선택 상세 Timeline뿐 아니라 Overview의 다음 값도 개선된다.

```text
ETA 반복지연 횟수
ETD 변경 횟수
ETA/ETD 최초 일정
순 지연일
Lead Time 변화
이상탐지 Risk Score
```

내부 선적 매핑은 계속 `transport_key`를 사용하며, 사용자 화면 식별자는 기존 원칙대로
HBL No.를 우선 사용한다.
