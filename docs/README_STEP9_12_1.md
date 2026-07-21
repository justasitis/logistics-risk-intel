# Step 9.12.1 — AIS 표시·선택·B-LAP 연결 Hotfix

## 화면에서 확인된 핵심 원인

Console:

```text
activeTransportCount: 0
displayedVesselCount: 0
```

지도:

```text
36 vessels
AFIF가 잘못 선택됨
대부분 B-LAP 미연결
```

따라서 다음 문제가 동시에 있었다.

1. 필터 결과가 아닌 원본 `aisVessels`가 지도에 전달됨
2. Overview 응답에 actual_atd가 없어 모든 Transport가 비활성 처리됨
3. 과거 여러 선적에 같은 선박명이 있어 전체 이력 기준 선명 매칭이 실패함
4. AIS 선택 ID가 고유하지 않거나 이전 선택이 남을 수 있음

## 변경 내용

```text
기존 aisVessels
→ allAisVessels로 이름 변경

새 aisVessels
→ 현재 ETD/ETA 운항 Window에 포함되는
   B-LAP Transport와 연결된 AIS만 반환

선명 매칭
→ 전체 129건이 아니라 활성 Transport 후보 안에서
   가장 최근 출항건을 선택

ais_id
→ MMSI 우선 고유 ID 생성

Event 선택
→ transport_key
→ trpr_no
→ vessel_name 순으로 정확한 AIS 선택
```

---

## 1. 압축 해제

```powershell
$Zip="$env:USERPROFILE\Downloads\logistics_risk_step9_12_1_ais_pipeline_hotfix.zip"
$Extract=".\_step9_12_1_ais_pipeline_hotfix"

Remove-Item $Extract -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -LiteralPath $Zip -DestinationPath $Extract -Force

$Patch="$Extract\logistics_risk_step9_12_1_ais_pipeline_hotfix"
```

---

## 2. 백업

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

& "$Patch\tools\backup_step9_12_1.ps1" `
  -ProjectRoot (Get-Location).Path
```

---

## 3. Utility 교체

```powershell
Copy-Item `
  "$Patch\frontend\src\utils\activeCargoAis.ts" `
  ".\frontend\src\utils\activeCargoAis.ts" `
  -Force
```

---

## 4. App.vue 적용

```powershell
code "$Patch\PATCH_SNIPPETS\AppVue_STEP9_12_1.md"
code ".\frontend\src\App.vue"
```

가장 중요한 구조:

```ts
const allAisVessels = computed(() => {
  // 기존 aisVessels 본문
})

const activeCargoAisView = computed(() =>
  buildActiveCargoAisView(
    allAisVessels.value,
    transports.value,
    {
      requireActualDeparture: false,
      scheduledDepartureGraceDays: 0,
      maxVoyageDays: 120,
      etaOverdueGraceDays: 30,
    },
  ),
)

const aisVessels = computed(
  () => activeCargoAisView.value.items,
)
```

Template은 그대로 유지:

```vue
:ais-vessels="aisVessels"
```

---

## 5. LogisticsMap 확인

```powershell
code "$Patch\PATCH_SNIPPETS\LogisticsMap_STEP9_12_1.md"
code ".\frontend\src\components\LogisticsMap.vue"
```

Popup과 선택 Layer가 `ais_id` 및 Step 9.10의
`aisPopupLinkState()`를 사용하는지 확인한다.

---

## 6. 감사

```powershell
& "$Patch\tools\audit_step9_12_1.ps1" `
  -ProjectRoot (Get-Location).Path
```

---

## 7. 빌드 검증

```powershell
& "$Patch\tools\verify_step9_12_1.ps1" `
  -ProjectRoot (Get-Location).Path
```

---

## 8. 브라우저 검증

```text
F12
→ Console
→ Active cargo AIS filter 검색
```

정상:

```text
activeTransportCount > 0
displayedVesselCount > 0
excludedAisCount > 0
```

`TR260630020` 선택 후:

```text
F12
→ Console
→ Selected cargo vessel 검색
```

정상:

```text
trprNo: TR260630020
vesselName: MTT BINTANGOR
linkedAisVessel: MTT BINTANGOR
linkedTrprNo: TR260630020
```

지도:

```text
MTT BINTANGOR만 선택 하이라이트
AFIF 선택 해제
2025년 12월 과거 선적 제외
표시되는 AIS Popup은 B-LAP 연결
```
