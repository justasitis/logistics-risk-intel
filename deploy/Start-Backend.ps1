# Start-Backend.ps1
# VDI 프로젝트 루트의 .venv 로 FastAPI 백엔드를 백그라운드 기동한다.
# 사용: powershell -NoProfile -ExecutionPolicy Bypass -File Start-Backend.ps1 [-ProjectRoot C:\dev\logistics-risk-intel]

[CmdletBinding()]
param(
    [string]$ProjectRoot = "C:\dev\logistics-risk-intel",
    [int]$Port = 8000
)

$ErrorActionPreference = "Stop"

$PythonExe = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$PidFile = Join-Path $ProjectRoot "backend.pid"
$LogDir = Join-Path $ProjectRoot "logs"
$LogStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile = Join-Path $LogDir "backend_$LogStamp.log"
$ErrFile = Join-Path $LogDir "backend_${LogStamp}_error.log"

if (-not (Test-Path $PythonExe)) {
    throw "가상환경 Python을 찾을 수 없습니다: $PythonExe`npython -m venv .venv 후 패키지를 설치하세요."
}

# 이미 기동 중이면 중복 기동 방지
if (Test-Path $PidFile) {
    $oldPid = [int](Get-Content $PidFile -Raw).Trim()
    $oldProcess = Get-Process -Id $oldPid -ErrorAction SilentlyContinue
    if ($oldProcess) {
        Write-Host "백엔드가 이미 실행 중입니다 (PID $oldPid). 먼저 Stop-Backend.ps1을 실행하세요."
        exit 0
    }
}

if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

Push-Location $ProjectRoot
try {
    $process = Start-Process `
        -FilePath $PythonExe `
        -ArgumentList "-m", "uvicorn", "api_server:app", "--host", "127.0.0.1", "--port", "$Port" `
        -WorkingDirectory $ProjectRoot `
        -RedirectStandardOutput $LogFile `
        -RedirectStandardError $ErrFile `
        -WindowStyle Hidden `
        -PassThru
}
finally {
    Pop-Location
}

Set-Content -Path $PidFile -Value $process.Id -Encoding ascii
Write-Host "백엔드 기동 완료 (PID $($process.Id), 포트 $Port)"
Write-Host "로그: $LogFile"
