# Step 9.9 — 선택 운송 고정 및 Timeline 응답 경합 방지

## 문제

Event 카드 클릭 직후에는 올바른 선적건이 표시되지만, 잠시 후 이전에 선택돼 있던
AIS 선박의 연결 운송건으로 상세 화면이 바뀌는 현상이 있다.

```text
Event 클릭
→ 올바른 selectedTransportKey 설정
→ 이전 AIS 선택 상태가 남아 있음
→ AIS watcher/background refresh 실행
→ unrelated matched_transport_key로 덮어쓰기
```

Timeline 요청도 비동기이므로 이전 선적의 응답이 늦게 도착하면 현재 화면을 덮을 수 있다.

## 해결 원칙

```text
Event 선택
→ Event가 selectedTransportKey의 소유권을 가짐
→ 관련 AIS만 선택하거나 AIS 선택 해제

AIS 선택
→ 사용자가 AIS를 직접 클릭한 경우에만 selectedTransportKey 변경

Background AIS/Stopby 갱신
→ selectedTransportKey 변경 금지

Timeline
→ 최신 요청 Token + transport_key 검증 후에만 화면 반영
```

## 포함 파일

```text
frontend/src/utils/selectionSync.ts
PATCH_SNIPPETS/AppVue_STEP9_9_SELECTION_LOCK.md
tools/backup_step9_9.ps1
tools/audit_selection_writes.ps1
tools/verify_step9_9.ps1
```

## 적용 순서

### 1. 압축 해제

```powershell
$Zip="$env:USERPROFILE\Downloads\logistics_risk_step9_9_selection_lock.zip"
$Extract=".\_step9_9_selection_lock"

Remove-Item $Extract -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -LiteralPath $Zip -DestinationPath $Extract -Force

$Patch="$Extract\logistics_risk_step9_9_selection_lock"
```

### 2. 백업

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "$Patch\tools\backup_step9_9.ps1" -ProjectRoot (Get-Location).Path
```

### 3. 신규 Utility 복사

```powershell
New-Item -ItemType Directory -Force ".\frontend\src\utils" | Out-Null

Copy-Item "$Patch\frontend\src\utils\selectionSync.ts" ".\frontend\src\utils\selectionSync.ts" -Force
```

### 4. 현재 선택값 쓰기 위치 확인

```powershell
& "$Patch\tools\audit_selection_writes.ps1" -ProjectRoot (Get-Location).Path
```

출력에서 다음 함수·watcher를 확인한다.

```text
selectEvent
AIS 클릭 함수
loadMarinesiaFromSharePoint
handleAisLoaded
refreshStopbyRoutes
watch(selectedAisItem)
Timeline 조회 함수
```

### 5. App.vue 수정

```powershell
code "$Patch\PATCH_SNIPPETS\AppVue_STEP9_9_SELECTION_LOCK.md"
code ".\frontend\src\App.vue"
```

안내문의 A~K를 현재 App.vue 구조에 맞게 적용한다.

기존에 직접 만든 다음 함수가 있으면 삭제하고 Utility import를 사용한다.

```text
eventSelectionKey
findTransportForEvent
```

### 6. 검증

```powershell
& "$Patch\tools\verify_step9_9.ps1" -ProjectRoot (Get-Location).Path
```

### 7. 실행 테스트

```powershell
python -m uvicorn api_server:app --reload --host 127.0.0.1 --port 8000
```

```powershell
cd frontend
npm run dev
```

## 정상 동작 기준

Event 카드 `TR260609009` 클릭 시:

```text
카드 하이라이트              TR260609009
선택 운송 상세 Transportation TR260609009
Timeline Network 요청         trpr_no=TR260609009
AIS 카드                      연결 AIS 또는 미선택
```

잠시 후에도 다른 선적건으로 바뀌지 않아야 한다.

AIS 선박 `AL MANAMAH`을 사용자가 직접 클릭한 경우에만 해당 연결 운송건으로 상세가 바뀐다.

## 중요한 구분

```text
transport_key / trpr_no
시스템 내부 식별 및 Timeline 조회

hbl_no
사용자 화면 대표 표시

selectedEventKey
Event 카드 하이라이트

selectedTransportKey
상세·지도·Timeline 선택

selectedAisId
AIS 카드 선택
```
