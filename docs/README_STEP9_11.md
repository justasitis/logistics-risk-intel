# Step 9.11 — 유럽향 희망봉 기본값 적용 범위 수정

## 변경 정책

기존:

```text
stopby 공란 + 유럽 도착
→ 모두 희망봉
```

수정:

```text
IF stopby 명시
→ 명시값 우선

stopby 공란 + 유럽 도착
→ 최단항로 먼저 계산

최단항로가 수에즈 통과
→ 희망봉 기본값

최단항로가 수에즈 미통과
→ 최단항로 유지
```

예:

```text
USORF → DEBRV, stopby 공란
→ SHORTEST

CNSHA → DEBRV, stopby 공란
→ EUROPE_SUEZ_DEFAULT
→ south_africa

USORF → DEBRV, stopby=희망봉
→ IF
→ south_africa
```

`searoute 1.4.3` 비지원 인자인 아래 항목도 제거했다.

```text
algorithm=
backend=
```

---

## 1. 압축 해제

프로젝트 루트에서 실행:

```powershell
$Zip="$env:USERPROFILE\Downloads\logistics_risk_step9_11_suez_exposure_default.zip"
$Extract=".\_step9_11_suez_exposure_default"

Remove-Item $Extract -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -LiteralPath $Zip -DestinationPath $Extract -Force

$Patch="$Extract\logistics_risk_step9_11_suez_exposure_default"
```

확인:

```powershell
Test-Path "$Patch\README_STEP9_11.md"
```

---

## 2. 기존 파일 백업

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

& "$Patch\tools\backup_step9_11.ps1" `
  -ProjectRoot (Get-Location).Path
```

---

## 3. 패치 적용

```powershell
& "$Patch\tools\apply_step9_11.ps1" `
  -ProjectRoot (Get-Location).Path
```

교체 대상:

```text
backend/app/services/stopby_route_builder.py
```

Frontend 수정은 없다.

---

## 4. 검증

```powershell
& "$Patch\tools\verify_step9_11.ps1" `
  -ProjectRoot (Get-Location).Path
```

정상 결과 핵심:

```text
version: 1.4.3
algorithm=algorithm 없음
backend=networkx 없음
Step 9.11 검증 성공
```

단위 테스트 정상 예:

```json
{
  "us_to_europe_blank": {
    "stopby_effective": "",
    "stopby_source": "SHORTEST",
    "suez_exposed": false
  },
  "asia_to_europe_blank": {
    "stopby_effective": "south_africa",
    "stopby_source": "EUROPE_SUEZ_DEFAULT",
    "suez_exposed": true,
    "passes_cape_latitude": true
  }
}
```

---

## 5. FastAPI 완전 재시작

기존 서버:

```text
Ctrl + C
```

재실행:

```powershell
python -m uvicorn api_server:app `
  --reload `
  --host 127.0.0.1 `
  --port 8000
```

Route 캐시 초기화를 위해 완전 재시작한다.

---

## 6. 브라우저 새 요청

```text
F12
→ Network
→ Disable cache 체크
→ 요청 목록 삭제
→ Ctrl + Shift + R
```

SKBM 법인 조회를 다시 실행한다.

Network Filter:

```text
stopby
```

`POST /api/routes/stopby`의 Response를 연다.

---

## 7. 미국 → 유럽 확인

`USORF` 또는 `DEBRV` 검색.

정상:

```json
{
  "europe_bound": true,
  "baseline_traversed_passages": [
    "gibraltar"
  ],
  "suez_exposed": false,
  "stopby_raw": "",
  "stopby_effective": "",
  "stopby_source": "SHORTEST",
  "route_mode": "shortest",
  "route_geometry_status": "GENERATED"
}
```

지도에서는 대서양 직항으로 표시돼야 한다.

---

## 8. 아시아 → 유럽 확인

정상:

```json
{
  "europe_bound": true,
  "baseline_traversed_passages": [
    "suez"
  ],
  "suez_exposed": true,
  "stopby_effective": "south_africa",
  "stopby_source": "EUROPE_SUEZ_DEFAULT",
  "route_geometry_status": "GENERATED",
  "passes_cape_latitude": true
}
```

B-LAP의 stopby가 직접 `희망봉`이면:

```json
{
  "stopby_source": "IF",
  "stopby_effective": "south_africa"
}
```

---

## 9. Warning 확인

Response의 `warnings`에서 아래 문구가 없어야 한다.

```text
unexpected keyword argument 'algorithm'
unexpected keyword argument 'backend'
```

실패 시 Feature에서 확인:

```text
route_geometry_status
route_geometry_error
```

---

## 10. 롤백

백업 파일을 원래 위치로 복사하고 FastAPI를 완전 재시작한다.

```powershell
Copy-Item `
  ".\_backup_before_step9_11_YYYYMMDD_HHMMSS\backend\app\services\stopby_route_builder.py" `
  ".\backend\app\services\stopby_route_builder.py" `
  -Force
```
