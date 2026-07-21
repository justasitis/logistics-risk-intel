# Step 9.10 — AIS B-LAP 연결 표시 및 희망봉 Route 보강

## 해결 대상

### 1. AIS Popup 모순

```text
Transportation No.는 표시됨
B-LAP 미연결로 표시됨
```

기존 Popup은 `properties.linked`만 보고 연결 여부를 판단했다.
이 값이 AIS GeoJSON 생성 시점에 갱신되지 않으면 Transportation No.가 있어도
미연결로 보일 수 있다.

Step 9.10은 다음 연결 필드를 다시 계산한다.

```text
matched_transport_key
matched_trpr_no
matched_hbl_no
linked
```

Popup도 `linked` 하나만 보지 않고 실제 Key와 번호를 함께 확인한다.

### 2. SKBM 희망봉 Route 미표시

SKBM의 Route Feature와 Transport의 `transport_key` Prefix가 다르면
기존 Backend가 Transport를 찾지 못해 `stopby=희망봉`을 읽지 못할 수 있다.

Step 9.10은 다음 순서로 Transport를 찾는다.

```text
transport_key
trpr_no
hbl_no
transport_key 마지막 TR No.
```

희망봉 Route는 임의의 Passage Edge 하나가 아니라 아래 해상 Waypoint를 사용한다.

```text
인도양 남부
→ 희망봉 남쪽
→ 남대서양
```

생성된 좌표가 남위 30도 이하를 통과하지 않으면 생성 실패로 처리한다.

---

## 패키지 구성

교체 파일:

```text
backend/app/services/stopby_route_builder.py
```

신규 파일:

```text
frontend/src/utils/aisTransportLink.ts
frontend/src/utils/stopbyRouteMerge.ts
```

수동 연결 안내:

```text
PATCH_SNIPPETS/AppVue_STEP9_10.md
PATCH_SNIPPETS/LogisticsMap_STEP9_10.md
PATCH_SNIPPETS/dashboard_types_STEP9_10.md
```

---

## 1. 압축 해제

프로젝트 루트에서:

```powershell
$Zip="$env:USERPROFILE\Downloads\logistics_risk_step9_10_ais_link_cape_route.zip"
$Extract=".\_step9_10_ais_link_cape_route"

Remove-Item $Extract -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -LiteralPath $Zip -DestinationPath $Extract -Force

$Patch="$Extract\logistics_risk_step9_10_ais_link_cape_route"
```

확인:

```powershell
Test-Path "$Patch\README_STEP9_10.md"
```

---

## 2. 적용 전 백업

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& "$Patch\tools\backup_step9_10.ps1" -ProjectRoot (Get-Location).Path
```

---

## 3. Backend 희망봉 Builder 교체

```powershell
Copy-Item `
  "$Patch\backend\app\services\stopby_route_builder.py" `
  ".\backend\app\services\stopby_route_builder.py" `
  -Force
```

기존 `/api/routes/stopby` Router는 그대로 사용한다.

---

## 4. Frontend Utility 복사

```powershell
New-Item -ItemType Directory -Force ".\frontend\src\utils" | Out-Null

Copy-Item `
  "$Patch\frontend\src\utils\aisTransportLink.ts" `
  ".\frontend\src\utils\aisTransportLink.ts" `
  -Force

Copy-Item `
  "$Patch\frontend\src\utils\stopbyRouteMerge.ts" `
  ".\frontend\src\utils\stopbyRouteMerge.ts" `
  -Force
```

---

## 5. Dashboard 타입 보완

자동 적용:

```powershell
& "$Patch\tools\patch_dashboard_types_step9_10.ps1" `
  -ProjectRoot (Get-Location).Path
```

자동 패치가 위치를 찾지 못하면:

```powershell
code "$Patch\PATCH_SNIPPETS\dashboard_types_STEP9_10.md"
code ".\frontend\src\types\dashboard.ts"
```

---

## 6. App.vue 연결

```powershell
code "$Patch\PATCH_SNIPPETS\AppVue_STEP9_10.md"
code ".\frontend\src\App.vue"
```

반드시 적용할 항목:

```text
A. Utility import
B. matchedAisItems를 ensureAisTransportLinks로 보강
C. effectiveRoutes를 mergeStopbyRoutes로 변경
F. handleAisLoaded에서 selectedTransportKey 대입 금지
```

Console 진단 D/E는 문제 확인 후 제거해도 된다.

---

## 7. LogisticsMap.vue Popup 수정

```powershell
code "$Patch\PATCH_SNIPPETS\LogisticsMap_STEP9_10.md"
code ".\frontend\src\components\LogisticsMap.vue"
```

기존 `aisPopupHtml()` 전체를 안내 코드로 교체한다.

---

## 8. 적용 상태 감사

```powershell
& "$Patch\tools\audit_step9_10.ps1" `
  -ProjectRoot (Get-Location).Path
```

---

## 9. 전체 검증

```powershell
& "$Patch\tools\verify_step9_10.ps1" `
  -ProjectRoot (Get-Location).Path
```

검증 내용:

```text
신규 Frontend Utility 연결
AIS Popup helper 연결
Backend Python 구문
실제 VDI의 searoute import 확인
SKBM TR260630020 형태의 Transport Key 불일치 단위 테스트
희망봉 Waypoint Route 남위 30도 통과 단위 테스트
Vue npm run build
```

정상 출력 예:

```text
"transport_key": "SKBM|SN01|TR260630020"
"stopby_effective": "south_africa"
"route_status": "GENERATED"
"minimum_latitude": -35 이하
Step 9.10 검증 성공
```

---

## 10. 서버 재시작

FastAPI:

```powershell
python -m uvicorn api_server:app --reload --host 127.0.0.1 --port 8000
```

Health 확인:

```powershell
& "$Patch\tools\test_stopby_health.ps1"
```

Frontend:

```powershell
cd frontend
npm run dev
```

---

## 11. 앱 검증

SKBM에서 `TR260630020`을 선택한다.

### AIS Popup

정상:

```text
MTT BINTANGOR
Transportation No. TR260630020
B-LAP 연결: TR260630020
```

HBL이 있으면 HBL도 표시된다.

### Console Route 진단

정상:

```text
found: true
trprNo: "TR260630020"
stopbyRaw: "희망봉"
stopbyEffective: "south_africa"
stopbySource: "IF"
routeStatus: "GENERATED"
passesCapeLatitude: true
minLatitude: -30 이하
```

### 지도

항로가 중국/아시아에서 인도양을 지나 남아프리카 남쪽으로 내려간 뒤
대서양·유럽 방향으로 표시돼야 한다.

---

## 12. 문제가 계속되는 경우

Network에서 `/api/routes/stopby` Response의 `TR260630020` Feature를 찾는다.

정상 Properties:

```json
{
  "trpr_no": "TR260630020",
  "transport_match_method": "TRPR_NO",
  "stopby_raw": "희망봉",
  "stopby_effective": "south_africa",
  "stopby_source": "IF",
  "route_geometry_status": "GENERATED",
  "passes_cape_latitude": true
}
```

아래 상태별 의미:

```text
transport_match_method = UNMATCHED
→ Route와 Transport의 TR No./HBL도 일치하지 않음

stopby_raw = ""
→ Dashboard Transport 응답에 stopby가 없음

route_geometry_status = FALLBACK_ORIGINAL
→ route_geometry_error 확인

passes_cape_latitude = false
→ Step 9.10 Builder가 실제로 적용되지 않았거나
  이전 API 응답이 캐시된 상태
```
