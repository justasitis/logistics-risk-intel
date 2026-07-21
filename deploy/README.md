# VDI 배포 가이드

변경·신규 파일만 VDI에 반영하는 증분 배포 방식. git은 로컬 PC까지만 사용하고,
VDI 반영은 robocopy(`/MIR`, `/PURGE` 미사용 — VDI 측 파일 삭제 없음)로 한다.

## 사전 조건

- 로컬 PC: 이 repo를 git clone (예: `C:\Work\logistics-risk-intel`), `git pull` 가능
- VDI: RDP 드라이브 리다이렉션 활성화 — 파일 탐색기에서 `\\tsclient\C\Work\LogisticsRisk` 접근 가능해야 함
- VDI 프로젝트: 예 `C:\dev\logistics-risk-intel` (최초 1회는 zip 풀어 전체 배치)
- VDI `.venv`, `npm`, pip config(Nexus) 설정 완료

## 운영 절차

```
[로컬 PC]  git pull                      (01_Git-Pull.cmd 사용 가능)
[VDI]      Deploy-From-Local.ps1 -Preview   → 변경 예정 파일 확인
[VDI]      Deploy-From-Local.ps1            → 실제 반영
```

실행 (VDI PowerShell):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File Deploy-From-Local.ps1 -Preview
powershell -NoProfile -ExecutionPolicy Bypass -File Deploy-From-Local.ps1
```

경로가 다르면 파라미터로 지정:

```powershell
... -Source "\\tsclient\C\Work\logistics-risk-intel" -Target "C:\dev\logistics-risk-intel"
```

## 스크립트 동작

1. robocopy로 신규·변경 파일만 복사 (New File / Newer)
2. `package.json`/`package-lock.json` 해시 변경 시에만 `npm ci`
3. VDI에서 `npm run build`
4. `backend/requirements.txt` 해시 변경 시에만 pip install (`PYTHONUTF8=1` 자동 설정)
5. `-StopBackendScript`/`-StartBackendScript` 지정 시 백엔드 재기동 + 헬스체크(`/docs`)

## 복사 제외 대상 (repo 구조 기준)

- 환경/빌드: `.git`, `node_modules`, `dist`, `.venv`, `__pycache__`, `logs`, `uploads`
- VDI 런타임 데이터: `<root>/data`, `backend/data/mi_runs`
- 런타임 파일: `.env`, `approved_mi_events.json`, `manual_coordinates.json`
- **git 관리 data는 복사 대상에 포함**: `backend/app/data/mi_location_master.json`, `backend/data/*.sample.json`

## 파일 삭제·이름 변경 규칙 (중요)

robocopy(`/E`)는 삭제를 전파하지 않는다. repo에서 파일이 삭제/리네임되면
VDI에는 구 파일이 남는다. 규칙:

1. 파일을 삭제/리네임하는 커밋에는 메시지에 `VDI 수동 삭제: <경로>` 를 적는다.
2. 배포 후 VDI에서 해당 파일을 수동 삭제한다.

## 최초 1회 배포

최초에는 증분이 아니라 전체가 필요하므로, GitHub에서 zip을 받아 VDI에 풀거나
이 스크립트를 그대로 실행하면 전체가 "New File"로 복사된다(단, 제외 대상은 스킵).
이후 `.venv` 생성 및 패키지 설치는 루트 README의 "실행" 절차를 따른다.
