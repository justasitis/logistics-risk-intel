# LogisticsRisk — VDI 무설치 exe 패키지 빌드 안내

팀원이 설치 없이 exe만 실행해 대시보드를 쓸 수 있도록, 사내 VDI에서
PyInstaller 패키지를 빌드하는 절차입니다. **빌드도 VDI에서 수행합니다**
(인터넷 불가, 사내 Nexus만 사용).

## 사전 준비 (1회)

1. **포터블 Node 반입** — 프런트엔드 빌드용.
   - 사내 PC에서 GitHub Release Assets의 `node-vXX.X.X-win-x64.zip`과
     `SHASUMS256.txt`(또는 `node-vXX.X.X-win-x64.sha256sum`)를 다운로드해
     VDI로 반입합니다.
   - **Node 20 이상 필수 (22 LTS 권장)** — vite 8은 Node 20 미만에서
     동작하지 않습니다. 스크립트가 버전을 검사하며, 낮으면 명확한 에러로
     중단됩니다.
   - zip을 압축 해제해 `C:\dev\node`(기본값)에 둡니다.
     `C:\dev\node\node.exe`가 보이는 구조여야 합니다.
   - zip과 `.sha256sum` 파일을 같은 폴터에 두면 빌드 시 해시 검증을
     자동 수행합니다(없으면 경고 후 생략).
2. **Python + 사내 Nexus pip** — `.venv`가 없으면 스크립트가 생성합니다.
   pip은 사내 Nexus 그룹 저장소가 pip config로 설정되어 있다고 가정합니다.
3. **PyInstaller** — 스크립트가 자동 설치합니다.

## 빌드 실행

```powershell
cd C:\dev\logistics-risk-intel
powershell -NoProfile -ExecutionPolicy Bypass -File build\Build-Package.ps1

# Node 경로가 다르면:
powershell -NoProfile -ExecutionPolicy Bypass -File build\Build-Package.ps1 -NodeRoot C:\dev\node-v22.14.0-win-x64

# frontend/dist가 이미 최신이면 프런트 빌드 생략:
powershell -NoProfile -ExecutionPolicy Bypass -File build\Build-Package.ps1 -SkipFrontend
```

단계: [1] Node 검증 → [2] zip sha256 검증(있을 때) → [3] npm ci + build →
[4] .venv/requirements/pyinstaller → [5] PyInstaller → [6] 패키지 조립.

## 산출물 구조 (`dist-package/`)

```
dist-package/
├── LogisticsRisk/                 # exe + 런타임 (PyInstaller onedir)
│   ├── LogisticsRisk.exe
│   └── _internal/                 # 파이썬 런타임, frontend/dist, 데이터 파일
├── sharepoint-sync/               # SharePoint 동기화 설치 스크립트 (최초 1회)
├── .env.example                   # .env 작성 안내
├── README-팀원안내.txt
└── LogisticsRisk-시작.cmd         # 실행 래퍼 (chcp 65001)
```

## 팀원 전달

1. `dist-package` 폴터를 zip으로 묶어 전달합니다.
2. 팀원 절차:
   1. (최초 1회) `sharepoint-sync\Setup-SharePointSync.cmd` 실행 — 동기화 설치 안내
   2. `.env.example`을 `LogisticsRisk\.env`로 복사해 실제 값 입력
      (별도 전달된 계정 값 사용)
   3. `LogisticsRisk-시작.cmd` 실행 → 브라우저가 `http://127.0.0.1:8000` 자동 오픈
   4. 종료는 콘솔 창 닫기

## VDI 실행 시 주의점

- exe는 PyInstaller onedir 산출물이라 최초 기동에 수 초 걸립니다.
- 백신/스마트스크린이 미서명 exe를 경고할 수 있습니다 — 사내 예외 등록이
  필요할 수 있습니다.
- `.env`는 exe 폴터(`LogisticsRisk\`) 기준으로 로드됩니다(런처가 먼저 읽음).
- 포트 8000을 쓰는 기존 프로세스는 `LogisticsRisk-시작.cmd`가 시작 시
  자동으로 종료합니다 (이전 실행 잔여분 정리).
- 쓰기 데이터(mi_runs 등)는 exe 폴터 아래 상대경로에 생성됩니다.
  zip을 읽기 전용 위치에 풀지 마세요.

## 파일 구성

| 파일 | 역할 |
|---|---|
| `build/launcher.py` | exe 진입점 — base dir/.env 로드 → uvicorn 기동 → 브라우저 오픈 |
| `build/logistics_risk.spec` | PyInstaller 스펙 (onedir, 데이터 수집) |
| `build/Build-Package.ps1` | VDI 빌드 파이프라인 (PS 5.1, UTF-8 BOM/CRLF) |
| `api_server.py` (수정) | frontend/dist 정적 서빙 마운트 |

## 트레이 알림박스 (LogisticsRiskTray)

- 패키지에 `LogisticsRiskTray/LogisticsRiskTray.exe`가 포함됩니다.
- **트레이는 백엔드(uvicorn 또는 LogisticsRisk.exe)가 실행 중일 때만 동작합니다.**
  백엔드가 꺼져 있으면 아이콘 제목에 실패 종류(시간 초과/연결 실패/서버 오류)가 표시되고 조용히 재시도합니다.
- 환경변수: `TRAY_SERVER_URL`(기본 http://127.0.0.1:8000),
  `TRAY_POLL_SECONDS`(기본 600), `TRAY_FETCH_TIMEOUT`(기본 60초).
- 시작 프로그램 등록은 트레이 메뉴 → "시작 프로그램 등록/해제"
  (HKCU Run 키, 관리자 권한 불필요).
