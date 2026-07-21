# Deploy-From-Local.ps1
# 회사 로컬 PC(git clone)에서 VDI 프로젝트로 변경·신규 파일만 반영하는 증분 배포 스크립트.
# robocopy /E 를 사용하며 /MIR, /PURGE 는 쓰지 않는다 (VDI 측 파일 삭제 없음).
#
# 기본 사용 (VDI PowerShell):
#   미리보기: powershell -NoProfile -ExecutionPolicy Bypass -File Deploy-From-Local.ps1 -Preview
#   실제 배포: powershell -NoProfile -ExecutionPolicy Bypass -File Deploy-From-Local.ps1
#
# 부분 배포:
#   -SkipFrontend   프런트엔드 npm ci/build 생략 (백엔드만 바뀐 경우)
#   -SkipPip        requirements.txt 변경이 있어도 pip install 생략
#   -SkipRestart    백엔드 재기동 생략

[CmdletBinding()]
param(
    [switch]$Preview,
    [switch]$SkipFrontend,
    [switch]$SkipPip,
    [switch]$SkipRestart,

    # VDI에서 보이는 로컬 PC 프로젝트 (RDP 드라이브 리다이렉션)
    [string]$Source = "\\tsclient\C\Work\logistics-risk-intel",

    # VDI 프로젝트
    [string]$Target = "C:\dev\logistics-risk-intel",

    # 백엔드 정상 확인 주소
    [string]$HealthUrl = "http://127.0.0.1:8000/api/health"
)

$ErrorActionPreference = "Stop"

$FrontendDir = Join-Path $Target "frontend"
$BackendDir = Join-Path $Target "backend"
$PythonExe = Join-Path $Target ".venv\Scripts\python.exe"
$RequirementsFile = Join-Path $BackendDir "requirements.txt"

# 백엔드 시작/종료 스크립트 (repo의 deploy/에 포함됨 — 배포 시 Target에 복사되어 존재)
$StopBackendScript = Join-Path $Target "deploy\Stop-Backend.ps1"
$StartBackendScript = Join-Path $Target "deploy\Start-Backend.ps1"

# 배포 로그는 VDI 프로젝트 아래 logs\ 에 둔다 (robocopy /XD logs 로 복사 제외됨)
$LogRoot = Join-Path $Target "logs\deploy"

# =====================================================
# 공통 함수
# =====================================================

function Get-HashOrEmpty {
    param([string]$Path)
    if (Test-Path $Path) {
        return (Get-FileHash -Path $Path -Algorithm SHA256).Hash
    }
    return ""
}

function Get-PackageFilesHash {
    $packageJson = Join-Path $FrontendDir "package.json"
    $packageLock = Join-Path $FrontendDir "package-lock.json"
    return "$(Get-HashOrEmpty $packageJson)|$(Get-HashOrEmpty $packageLock)"
}

function Test-BackendHealth {
    $maximumAttempts = 10
    for ($attempt = 1; $attempt -le $maximumAttempts; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $HealthUrl -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
                Write-Host "백엔드 정상 실행 확인 완료 (응답 코드: $($response.StatusCode))"
                return
            }
        }
        catch {
            Write-Host "백엔드 확인 재시도: $attempt/$maximumAttempts"
        }
        Start-Sleep -Seconds 2
    }
    throw "백엔드 정상 확인 실패: $HealthUrl"
}

# =====================================================
# 사전 확인
# =====================================================

Write-Host ""
Write-Host "=========================================="
Write-Host " LogisticsRisk VDI 배포"
Write-Host "=========================================="

if (-not (Test-Path $Source)) {
    throw @"
VDI에서 로컬 프로젝트를 찾을 수 없습니다: $Source
VDI 파일 탐색기에서 \\tsclient\C 가 보이는지(RDP 드라이브 리다이렉션) 확인하세요.
"@
}
if (-not (Test-Path $Target)) {
    throw "VDI 프로젝트 폴터를 찾을 수 없습니다: $Target"
}
if (-not (Test-Path $LogRoot)) {
    New-Item -ItemType Directory -Path $LogRoot -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$DeployLog = Join-Path $LogRoot "deploy_$timestamp.log"

$PackageHashBefore = Get-PackageFilesHash
$RequirementsHashBefore = Get-HashOrEmpty $RequirementsFile

# =====================================================
# [1/5] Robocopy — 변경·신규 파일만
# =====================================================
#
# 제외 원칙 (repo 구조 기준):
#   - 환경/빌드 산출물: .git, node_modules, dist, .venv, __pycache__, logs 등
#   - VDI 런타임 데이터: <root>\data, backend\data\mi_runs
#   - 런타임 파일: .env, approved_mi_events.json, manual_coordinates.json
#   - git 관리 data(backend\app\data, backend\data\*.sample.json)는 복사 대상에 포함
#
# 주의: 삭제·이름변경된 파일은 자동 반영되지 않는다 (커밋 메시지의 "VDI 수동 삭제" 참고).

Write-Host ""
Write-Host "[1/5] 로컬 PC와 VDI 프로젝트 비교 중..."

$RobocopyOptions = @(
    "/E",
    "/FFT",                 # 원격 드라이브 시간 정밀도 차이 대응
    "/R:2", "/W:2",
    "/COPY:DAT", "/DCOPY:DAT",
    "/XJ",                  # Junction 순환 방지
    "/NP", "/TEE",
    "/LOG+:$DeployLog",

    # 폴터 제외 (이름 기준 — 어디에 있든 제외)
    "/XD", ".git", "node_modules", "dist", ".venv", "__pycache__", ".pytest_cache", "logs", "uploads",
    # 폴터 제외 (전체 경로 — VDI 런타임 데이터만, 소스 기준)
    (Join-Path $Source "data"),
    (Join-Path $Source "backend\data\mi_runs"),

    # 파일 제외
    "/XF", ".env", "*.log", "*.pyc", "backend.pid",
    "approved_mi_events.json", "manual_coordinates.json"
)

if ($Preview) {
    $RobocopyOptions += "/L"
    Write-Host "[미리보기 모드] 실제 파일은 복사하지 않습니다."
}

& robocopy $Source $Target @RobocopyOptions
$RobocopyExitCode = $LASTEXITCODE

if ($RobocopyExitCode -ge 8) {
    throw "Robocopy 실패. 종료 코드: $RobocopyExitCode (로그: $DeployLog)"
}

if ($Preview) {
    Write-Host ""
    Write-Host "변경 예정 파일 확인 완료 (New File=신규, Newer=변경)"
    Write-Host "로그: $DeployLog"
    exit 0
}

Write-Host "변경·신규 파일 복사 완료 (robocopy 코드: $RobocopyExitCode)"

$PackageFilesChanged = (Get-PackageFilesHash) -ne $PackageHashBefore
$RequirementsChanged = (Get-HashOrEmpty $RequirementsFile) -ne $RequirementsHashBefore

# =====================================================
# [2/5] 프런트엔드 의존성 (package 파일 변경 시에만 npm ci)
# =====================================================

if ($SkipFrontend) {
    Write-Host ""
    Write-Host "[2/5] -SkipFrontend 지정 - 프런트엔드 단계 생략"
}
else {
    Write-Host ""
    Write-Host "[2/5] 프런트엔드 의존성 확인 중..."

    if ($PackageFilesChanged -or -not (Test-Path (Join-Path $FrontendDir "node_modules"))) {
        Write-Host "package.json/package-lock.json 변경 또는 node_modules 없음 - npm ci 실행"
        Push-Location $FrontendDir
        try {
            & npm.cmd ci
            if ($LASTEXITCODE -ne 0) { throw "npm ci 실패 (사내 Nexus 레지스트리 연결 확인)" }
        }
        finally { Pop-Location }
    }
    else {
        Write-Host "패키지 설정 변경 없음 - npm ci 생략"
    }

    # =====================================================
    # [3/5] 프런트엔드 빌드 (VDI에서 수행)
    # =====================================================

    Write-Host ""
    Write-Host "[3/5] 프런트엔드 빌드 중..."

    Push-Location $FrontendDir
    try {
        & npm.cmd run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build 실패" }
    }
    finally { Pop-Location }

    if (-not (Test-Path (Join-Path $FrontendDir "dist\index.html"))) {
        throw "빌드 결과를 찾을 수 없습니다: dist\index.html"
    }
    Write-Host "프런트엔드 빌드 완료"
}

# =====================================================
# [4/5] Python 패키지 (requirements.txt 변경 시에만)
# =====================================================

Write-Host ""
Write-Host "[4/5] 백엔드 의존성 확인 중..."

if ($SkipPip) {
    Write-Host "-SkipPip 지정 - pip 단계 생략"
}
elseif ($RequirementsChanged) {
    Write-Host "requirements.txt 변경됨 - pip install 실행"
    if (-not (Test-Path $PythonExe)) {
        throw "VDI 가상환경 Python을 찾을 수 없습니다: $PythonExe"
    }
    # searoute 소스 빌드 시 한글 Windows 인코딩 오류 방지
    $env:PYTHONUTF8 = "1"
    & $PythonExe -m pip install -r $RequirementsFile
    if ($LASTEXITCODE -ne 0) { throw "Python 패키지 설치 실패 (사내 Nexus PyPI 확인)" }
}
else {
    Write-Host "requirements.txt 변경 없음 - pip install 생략"
}

# =====================================================
# [5/5] 백엔드 재기동
# =====================================================

Write-Host ""
Write-Host "[5/5] 백엔드 재기동 중..."

if ($SkipRestart) {
    Write-Host "-SkipRestart 지정 - 재기동 생략 (수동으로 재기동하세요)"
}
elseif ((Test-Path $StopBackendScript) -and (Test-Path $StartBackendScript)) {
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $StopBackendScript -ProjectRoot $Target
    if ($LASTEXITCODE -ne 0) { throw "백엔드 종료 실패" }

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $StartBackendScript -ProjectRoot $Target
    if ($LASTEXITCODE -ne 0) { throw "백엔드 시작 실패" }

    Test-BackendHealth
}
else {
    Write-Host "deploy\Start-Backend.ps1 / Stop-Backend.ps1 이 없어 수동 재기동이 필요합니다:"
    Write-Host "  .venv\Scripts\python -m uvicorn api_server:app --host 127.0.0.1 --port 8000"
}

Write-Host ""
Write-Host "=========================================="
Write-Host " VDI 배포 완료"
Write-Host "=========================================="
Write-Host "배포 로그: $DeployLog"
