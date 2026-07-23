# VDI 배포 런북

변경·신규 파일만 VDI에 반영하는 증분 배포. git은 로컬 PC까지만 쓰고,
VDI 반영은 robocopy(`/MIR`, `/PURGE` 미사용 — VDI 측 파일 삭제 없음)로 한다.

## 구성 파일 (deploy/)

| 파일 | 실행 위치 | 역할 |
|---|---|---|
| `01_Git-Pull.cmd` | 로컬 PC | GitHub 최신 코드 가져오기 — 최초엔 자동 연결(clone 대체), 이후 pull. `C:\Work\logistics-risk-intel` 에 두고 실행 |
| `02_VDI-Deploy.cmd` | VDI | 원클릭 배포 — Deploy-From-Local.ps1을 호출 (더블클릭 실행) |
| `Deploy-From-Local.ps1` | VDI | 변경·신규 복사 → npm ci(조걶) → build → pip(조걶) → 재기동 |
| `Start-Backend.ps1` | VDI | `.venv`로 백엔드 백그라운드 기동 (`backend.pid`, `logs\` 기록) |
| `Stop-Backend.ps1` | VDI | `backend.pid`로 백엔드 종료 |

## 팀원 온보딩 (신규 사용자)

앱은 SharePoint 동기화 폴터의 데이터(AIS, MI 후보, 수동 좌표)를 읽으므로,
팀원은 먼저 **해당 SharePoint 폴터를 본인 PC에 동기화**해야 한다.

1. `deploy/sharepoint-sync/` 의 두 파일을 팀원 PC에 전달
2. 팀원 PC에서 `Setup-SharePointSync.cmd` 를 더블클릭 (또는 아래 명령 실행):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File Install-OneDriveSpecificFolderSync_v1.5.ps1
```

3. 설치 마지막에 **경로 표준화**가 자동 실행된다 — OneDrive는 PC마다 동기화 폴터명을 다르게 만든다
   (예: `SK on - LogisticsRisk`). `Repair-SharePointPath.ps1`이 실제 위치를 찾아 표준 경로
   (`...\SK on\Global물류팀 - LogisticsRisk`)로 Junction 연결한다. 실패하면 동기화 완료 후
   `Repair-SharePointPath.ps1`만 다시 실행하면 된다.
4. 이후는 일반 배포 절차와 동일 (프로젝트 배치 → `.env` → `02_VDI-Deploy.cmd`)

## 사전 조건 (최초 1회)

1. 로컬 PC: `git clone` → `C:\Work\logistics-risk-intel`
2. VDI: `C:\dev\logistics-risk-intel` 에 프로젝트 배치 (zip 또는 본 스크립트 최초 실행)
3. VDI: `.env` 작성 (`.env.example` 복사). `.venv`와 패키지는 배포 스크립트가 없으면 자동 생성하므로 수동 생성은 선택
4. VDI: `frontend\npm ci` + `.env` 작성 (`.env.example` 복사)
5. VDI 파일 탐색기에서 `\\Client\C$\Work\logistics-risk-intel` 이 보이는지 확인
   (RDP 클라이언트 드라이브 공유. 안 보이면 zip 반입 후 로컬 경로를 -Source로 지정)

## 일상 배포 절차

```
[로컬 PC]  01_Git-Pull.cmd                    ← GitHub 최신 코드 (원클릭)
[VDI]      02_VDI-Deploy.cmd                  ← 원클릭 배포 (복사~재기동 전체)

세부 확인이 필요하면 ps1을 직접:
[VDI]      Deploy-From-Local.ps1 -Preview     ← 변경 예정 파일만 확인
[VDI]      Deploy-From-Local.ps1              ← 실제 반영
```

VDI PowerShell 실행:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\dev\logistics-risk-intel\deploy\Deploy-From-Local.ps1 -Preview
powershell -NoProfile -ExecutionPolicy Bypass -File C:\dev\logistics-risk-intel\deploy\Deploy-From-Local.ps1
```

## 스크립트 동작 상세 (5단계)

1. **robocopy**: 신규(New File)·변경(Newer)만 복사. 코드 8 이상이면 실패 중단
2. **npm ci**: `package.json`/`package-lock.json` 해시가 바뀐 경우에만 (사내 Nexus 경유)
3. **npm run build**: VDI에서 빌드 (로컬 PC에서 빌드하지 않음)
4. **pip install**: `backend/requirements.txt` 해시가 바뀐 경우에만 (`PYTHONUTF8=1` 자동 설정)
5. **백엔드 재기동**: `deploy\Stop-Backend.ps1` → `Start-Backend.ps1` → `/api/health` 확인

### 부분 배포 스위치

| 스위치 | 용도 |
|---|---|
| `-SkipFrontend` | 백엔드만 바뀐 배포 (npm 단계 전체 생략) |
| `-SkipPip` | requirements 변경을 이번에 반영하지 않을 때 |
| `-SkipRestart` | 재기동 없이 파일만 반영 |

## 복사 제외 대상 (repo 구조 기준)

- 환경/빌드: `.git`, `node_modules`, `dist`, `.venv`, `__pycache__`, `logs`, `uploads`
- VDI 런타임 데이터: `<root>\data`, `backend\data\mi_runs`
- 런타임 파일: `.env`, `approved_mi_events.json`, `manual_coordinates.json`, `backend.pid`
- **git 관리 data는 복사 대상에 포함**: `backend\app\data\mi_location_master.json`, `backend\data\*.sample.json`

## 파일 삭제·이름 변경 규칙 (중요)

robocopy(`/E`)는 삭제를 전파하지 않는다 — repo에서 지운 파일도 VDI에 남는다.

1. 삭제/리네임 커밋에는 메시지에 `VDI 수동 삭제: <경로>` 를 적는다.
2. 배포 후 VDI에서 해당 파일을 수동 삭제한다.

## 트러블슈팅

| 증상 | 확인 |
|---|---|
| `Source를 찾을 수 없음` | RDP 클라이언트 드라이브 공유: VDI에서 `\\Client\C$` 접근 확인. 안 되면 zip 풀고 `-Source`로 로컬 경로 지정 |
| `npm ci 실패` | 사내 Nexus npm 레지스트리 연결, `.npmrc` 확인 |
| `pip install 실패` | Nexus PyPI(`pypi-group-internal`) 확인, `PYTHONUTF8=1` 여부(스크립트가 자동 설정) |
| 백엔드 헬스체크 실패 | `logs\backend_*.log` 확인. 포트 8000 점유 여부 (`netstat -ano \| findstr :8000`) |
| 스크립트 실행 자체가 안 됨 | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` 또는 `-ExecutionPolicy Bypass` 사용 |
| 배포 후 한글 깨짐 | ps1은 UTF-8 BOM+CRLF 형식 유지 필요 (편집 시 형식 보존) |

## 최초 1회 배포

최초에는 GitHub zip을 VDI에 풀거나, 본 스크립트를 그대로 실행하면 전체가
"New File"로 복사된다. `.venv`와 패키지 설치는 스크립트가 자동 수행하므로
최초에도 `.env` 작성만 수동으로 하면 된다.
