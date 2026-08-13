# Build-Package.ps1
# VDI에서 LogisticsRisk 무설치 배포 패키지를 빌드한다.
#
# 사용 (VDI PowerShell 5.1):
#   powershell -NoProfile -ExecutionPolicy Bypass -File build\Build-Package.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File build\Build-Package.ps1 -NodeRoot C:\dev\node-v22.14.0-win-x64
#   powershell -NoProfile -ExecutionPolicy Bypass -File build\Build-Package.ps1 -SkipFrontend
#
# 사전 준비:
#   - 포터블 Node (Node 20 이상, 22 LTS 권장) 를 $NodeRoot 에 압축 해제해 둘 것
#     (GitHub Release Assets의 node-v*-win-x64.zip + .sha256sum 을 사내 반입)
#   - pip은 사내 Nexus 그룹(pip config 사전 설정) 사용
[CmdletBinding()]
param(
    # 포터블 node 폴터 (node.exe 가 있는 폴터)
    [string]$NodeRoot = "C:\dev\node",

    # 프런트엔드 npm ci/build 생략 (frontend/dist 가 이미 최신인 경우)
    [switch]$SkipFrontend,

    # 패키지 산출 폴터
    [string]$OutDir = "dist-package"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$FrontendDir = Join-Path $ProjectRoot "frontend"
$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$VenvDir = Join-Path $ProjectRoot ".venv"
$RequirementsFile = Join-Path $ProjectRoot "backend\requirements.txt"
$SpecFile = Join-Path $ProjectRoot "build\logistics_risk.spec"
$PyiDist = Join-Path $ProjectRoot "build\dist\LogisticsRisk"
$PackageRoot = Join-Path $ProjectRoot $OutDir
$PackageAppDir = Join-Path $PackageRoot "LogisticsRisk"

$env:PYTHONUTF8 = "1"

$script:Step = 0
$TotalSteps = 6
function Write-Step([string]$Message) {
    $script:Step += 1
    Write-Host ("[{0}/{1}] {2}" -f $script:Step, $TotalSteps, $Message) -ForegroundColor Cyan
}

# =====================================================
# [1/6] Node 검증 (버전 >= 20)
# =====================================================
if (-not $SkipFrontend) {
    Write-Step "Node 검증"
    $NodeExe = Join-Path $NodeRoot "node.exe"
    if (-not (Test-Path $NodeExe)) {
        throw "node.exe를 찾을 수 없습니다: $NodeExe`n포터블 Node를 $NodeRoot 에 준비하세요 (Node 20 이상, 22 LTS 권장)."
    }
    $NodeVersion = (& $NodeExe --version).Trim()   # 예: v22.14.0
    $NodeMajor = [int]($NodeVersion.TrimStart('v').Split('.')[0])
    if ($NodeMajor -lt 20) {
        throw "vite 8은 Node 20 이상이 필요합니다 (현재: $NodeVersion). GitHub Release Assets에서 node-v22.x win-x64 zip으로 준비하세요."
    }
    Write-Host "  Node $NodeVersion 확인됨 ($NodeExe)"
} else {
    Write-Step "Node 검증 생략 (-SkipFrontend)"
}

# =====================================================
# [2/6] Node zip sha256 검증 (zip + sha256sum이 함께 있을 때만)
# =====================================================
if (-not $SkipFrontend) {
    Write-Step "Node zip sha256 검증 (있을 때만)"
    $NodeZip = Get-ChildItem -Path $NodeRoot -Filter "node-v*-win-x64.zip" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($NodeZip) {
        $SumFile = Get-ChildItem -Path $NodeRoot -Filter "node-v*-win-x64.sha256sum" -ErrorAction SilentlyContinue | Select-Object -First 1
        if (-not $SumFile) {
            Write-Warning "sha256sum 파일이 없어 zip 해시 검증을 건너뜩니다: $($NodeZip.Name)"
        } else {
            $Expected = (($SumFile | Get-Content -First 1) -split '\s+')[0].ToUpper()
            $Actual = (Get-FileHash -Path $NodeZip.FullName -Algorithm SHA256).Hash.ToUpper()
            if ($Expected -ne $Actual) {
                throw "Node zip 해시 불일치! 기대: $Expected / 실제: $Actual — 반입 파일이 손상됐을 수 있습니다."
            }
            Write-Host "  sha256 검증 통과: $($NodeZip.Name)"
        }
    } else {
        Write-Host "  zip 없음 — 이미 압축 해제된 폴터로 간주, 검증 생략"
    }
} else {
    Write-Step "sha256 검증 생략 (-SkipFrontend)"
}

# =====================================================
# [3/6] 프런트엔드 빌드 (npm ci + npm run build)
# =====================================================
if (-not $SkipFrontend) {
    Write-Step "프런트엔드 빌드"
    $NpmCmd = Join-Path $NodeRoot "npm.cmd"
    if (-not (Test-Path $NpmCmd)) { throw "npm.cmd를 찾을 수 없습니다: $NpmCmd" }
    $env:Path = "$NodeRoot;$env:Path"
    Push-Location $FrontendDir
    try {
        & $NpmCmd ci
        if ($LASTEXITCODE -ne 0) { throw "npm ci 실패 (exit $LASTEXITCODE)" }
        & $NpmCmd run build
        if ($LASTEXITCODE -ne 0) { throw "npm run build 실패 (exit $LASTEXITCODE)" }
    } finally {
        Pop-Location
    }
    if (-not (Test-Path (Join-Path $FrontendDir "dist\index.html"))) {
        throw "frontend\dist\index.html이 생성되지 않았습니다."
    }
} else {
    Write-Step "프런트엔드 빌드 생략 (-SkipFrontend)"
    if (-not (Test-Path (Join-Path $FrontendDir "dist\index.html"))) {
        throw "-SkipFrontend인데 frontend\dist\index.html이 없습니다. 먼저 프런트엔드를 빌드하세요."
    }
}

# =====================================================
# [4/6] .venv + requirements + pyinstaller
# =====================================================
Write-Step "Python 환경 준비"
if (-not (Test-Path $PythonExe)) {
    Write-Host "  .venv 생성 중..."
    & python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) { throw "python -m venv 실패 — 시스템 python이 PATH에 있어야 합니다." }
}
& $PythonExe -m pip install -r $RequirementsFile
if ($LASTEXITCODE -ne 0) { throw "pip install -r requirements.txt 실패" }
& $PythonExe -m pip install pyinstaller
if ($LASTEXITCODE -ne 0) { throw "pip install pyinstaller 실패" }
& $PythonExe -m pip install pystray windows-toasts pillow
if ($LASTEXITCODE -ne 0) { throw "pip install tray deps 실패" }

# =====================================================
# [5/6] PyInstaller 빌드
# =====================================================
Write-Step "PyInstaller 빌드"
Push-Location $ProjectRoot
try {
    & $PythonExe -m PyInstaller $SpecFile --noconfirm `
        --workpath (Join-Path $ProjectRoot "build\work") `
        --distpath (Join-Path $ProjectRoot "build\dist")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 빌드 실패 (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}
$TraySpecFile = Join-Path $ProjectRoot "build\logistics_risk_tray.spec"
Push-Location $ProjectRoot
try {
    & $PythonExe -m PyInstaller $TraySpecFile --noconfirm `
        --workpath (Join-Path $ProjectRoot "build\work-tray") `
        --distpath (Join-Path $ProjectRoot "build\dist-tray")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller 트레이 빌드 실패 (exit $LASTEXITCODE)" }
} finally {
    Pop-Location
}
$ExePath = Join-Path $PyiDist "LogisticsRisk.exe"
if (-not (Test-Path $ExePath)) { throw "빌드 산출물이 없습니다: $ExePath" }

# =====================================================
# [6/6] 패키지 조립
# =====================================================
Write-Step "패키지 조립 → $PackageRoot"
if (Test-Path $PackageRoot) { Remove-Item -Recurse -Force $PackageRoot }
New-Item -ItemType Directory -Force -Path $PackageAppDir | Out-Null

# robocopy: 0~7이 정상 종료 코드
& robocopy $PyiDist $PackageAppDir /E /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -gt 7) { throw "robocopy 실패 (exit $LASTEXITCODE)" }
& robocopy (Join-Path $ProjectRoot "build\dist-tray\LogisticsRiskTray") (Join-Path $PackageAppDir "LogisticsRiskTray") /E /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -gt 7) { throw "robocopy(tray) 실패 (exit $LASTEXITCODE)" }

# .env.example (팀원이 .env로 복사해 값 입력)
$EnvExampleDst = Join-Path $PackageRoot ".env.example"
Copy-Item (Join-Path $ProjectRoot ".env.example") $EnvExampleDst
$EnvNote = "`r`n# ===== 배포 패키지 안내 =====`r`n# 이 파일을 LogisticsRisk 폴터의 .env 로 복사한 뒤 실제 값을 입력하세요.`r`n# (.env 는 실행 폴터 기준으로 로드됩니다)"
Add-Content -Path $EnvExampleDst -Value $EnvNote -Encoding UTF8

# SharePoint 동기화 설치 스크립트
& robocopy (Join-Path $ProjectRoot "deploy\sharepoint-sync") (Join-Path $PackageRoot "sharepoint-sync") /E /NFL /NDL /NJH /NJS | Out-Null
if ($LASTEXITCODE -gt 7) { throw "robocopy(sharepoint-sync) 실패 (exit $LASTEXITCODE)" }

# 실행 래퍼 cmd (포트 8000 사용 중이면 기존 프로세스를 종료하고 시작)
$CmdContent = "@echo off`r`nchcp 65001 >nul`r`ncd /d %~dp0`r`nfor /f `"tokens=5`" %%a in ('netstat -ano ^| findstr LISTENING ^| findstr `":8000 `"') do taskkill /F /PID %%a >nul 2>&1`r`nLogisticsRisk\LogisticsRisk.exe`r`npause`r`n"
[System.IO.File]::WriteAllText((Join-Path $PackageRoot "LogisticsRisk-시작.cmd"), $CmdContent, [System.Text.Encoding]::Default)

# 팀원용 README
$ReadmeLines = @(
    "LogisticsRisk 실행 패키지 (무설치)",
    "",
    "[최초 1회] SharePoint 동기화 설치",
    "  1) sharepoint-sync\Setup-SharePointSync.cmd 를 더블클릭해 안내에 따라 설치",
    "",
    "[실행]",
    "  1) .env.example 을 LogisticsRisk\.env 로 복사하고 실제 값 입력",
    "     (데이터레이크/Actify 계정 등 — .env 는 관리자가 별도 전달한 값 사용)",
    "  2) LogisticsRisk-시작.cmd 더블클릭",
    "  3) 잠시 후 브라우저가 http://127.0.0.1:8000 을 자동으로 엽니다",
    "",
    "[종료]",
    "  검은 콘솔 창을 닫으면 서버가 종료됩니다.",
    "",
    "[주의]",
    "  - 백신/스마트스크린이 exe를 경고할 수 있습니다 (내부 서명 없는 PyInstaller 산출물).",
    "  - 포트 8000을 쓰는 기존 프로세스는 시작 시 자동으로 종료됩니다."
)
[System.IO.File]::WriteAllText((Join-Path $PackageRoot "README-팀원안내.txt"), ($ReadmeLines -join "`r`n"), [System.Text.UTF8Encoding]::new($true))

Write-Host ""
Write-Host "===== 패키지 완성 =====" -ForegroundColor Green
Write-Host "  산출 폴터 : $PackageRoot"
Write-Host "  exe       : $ExePath"
Write-Host "  전달 방법 : $OutDir 폴터를 zip으로 묶어 팀원에게 전달"
