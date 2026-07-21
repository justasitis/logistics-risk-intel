# Stop-Backend.ps1
# Start-Backend.ps1이 기록한 backend.pid를 읽어 백엔드를 종료한다.
# 사용: powershell -NoProfile -ExecutionPolicy Bypass -File Stop-Backend.ps1 [-ProjectRoot C:\dev\logistics-risk-intel]

[CmdletBinding()]
param(
    [string]$ProjectRoot = "C:\dev\logistics-risk-intel"
)

$ErrorActionPreference = "Stop"

$PidFile = Join-Path $ProjectRoot "backend.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "backend.pid가 없습니다. 실행 중인 백엔드가 없는 것으로 간주합니다."
    exit 0
}

$procId = [int](Get-Content $PidFile -Raw).Trim()
$process = Get-Process -Id $procId -ErrorAction SilentlyContinue

if ($process) {
    Stop-Process -Id $procId -Force
    Start-Sleep -Seconds 2
    Write-Host "백엔드 종료 완료 (PID $procId)"
}
else {
    Write-Host "PID $procId 프로세스가 이미 종료되어 있습니다."
}

Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
