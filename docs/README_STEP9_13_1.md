# Step 9.13.1 — 공통 좌표·스크롤·미등록 개수 Hotfix

## 해결 내용

### 좌표 범위

기존:

```text
법인 + Location Code
```

수정:

```text
Location Code 단독
모든 법인이 공통 좌표 사용
```

### 미등록 개수

수정 전에는 Dashboard 원본 집계와 법인/POL/POD 중복 때문에
좌표 저장 후에도 개수가 그대로 남을 수 있었다.

수정 후:

```text
Location Code 기준 1개로 집계
수동 좌표 Code를 즉시 known 처리
저장 이벤트에서 local state 먼저 갱신
상태바는 missingCoordinateItems.length 사용
```

### 스크롤

```text
Panel 고정 높이
body min-height: 0
목록 overflow-y: auto
입력 Form overflow-y: auto
```

## 1. 압축 해제

```powershell
$Zip="$env:USERPROFILE\Downloads\logistics_risk_step9_13_1_common_coordinate_hotfix.zip"
$Extract=".\_step9_13_1_common_coordinate_hotfix"

Remove-Item $Extract -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -LiteralPath $Zip -DestinationPath $Extract -Force

$Patch="$Extract\logistics_risk_step9_13_1_common_coordinate_hotfix"
```

## 2. 백업

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

& "$Patch\tools\backup_step9_13_1.ps1" `
  -ProjectRoot (Get-Location).Path
```

## 3. 파일 교체

```powershell
& "$Patch\tools\apply_step9_13_1_files.ps1" `
  -ProjectRoot (Get-Location).Path
```

기존 `data/manual_coordinates.json`은 덮어쓰지 않는다.

## 4. App.vue 수정

```powershell
code "$Patch\PATCH_SNIPPETS\AppVue_STEP9_13_1.md"
code ".\frontend\src\App.vue"
```

핵심:

```text
fetchManualCoordinates() — company 없이 호출
Panel의 :company 제거
handleCoordinateSaved / handleCoordinateDeleted 분리
상태바는 missingCoordinateItems.length 사용
```

## 5. 검증

```powershell
& "$Patch\tools\verify_step9_13_1.ps1" `
  -ProjectRoot (Get-Location).Path
```

검증 중 기존 법인별 좌표는 Location Code 기준 공통 좌표로 정리된다.

## 6. FastAPI 재시작

```text
Ctrl + C
```

```powershell
python -m uvicorn api_server:app `
  --reload `
  --host 127.0.0.1 `
  --port 8000
```

Health:

```text
http://127.0.0.1:8000/api/coordinates/manual/health
```

정상:

```json
{
  "status": "ok",
  "scope": "GLOBAL"
}
```

## 7. 화면 확인

```text
좌표 미등록 x개 클릭
→ 목록 영역에 세로 스크롤바
→ 특정 Code 등록
→ 저장 즉시 미등록 개수 1 감소
→ 등록 좌표 탭에 표시
```

같은 Port가 POL과 POD에 동시에 있어도 미등록 개수는 Code 기준 1개다.
