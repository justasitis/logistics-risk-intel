@echo off
chcp 65001 >nul
setlocal EnableExtensions

rem =====================================================
rem 02_VDI-Deploy.cmd (VDI용)
rem 로컬 PC(\\Client\C$)의 최신 코드를 VDI 프로젝트에 반영한다.
rem 더블클릭으로 실행하면 된다.
rem deploy\ 폴터에 두어도, 프로젝트 루트에 두어도 동작한다.
rem =====================================================

set "SCRIPT_DIR=%~dp0"

rem --- 프로젝트 루트 감지 (위치 무관) ---
if /i "%SCRIPT_DIR:~-7%"=="\deploy\" (
    for %%I in ("%SCRIPT_DIR%..") do set "PROJECT_DIR=%%~fI"
) else (
    for %%I in ("%SCRIPT_DIR%.") do set "PROJECT_DIR=%%~fI"
)

rem ps1 위치 결정 (deploy\ 안에 있으면 그쪽 우선)
set "PS1_FILE=%SCRIPT_DIR%Deploy-From-Local.ps1"
if not exist "%PS1_FILE%" set "PS1_FILE=%PROJECT_DIR%\deploy\Deploy-From-Local.ps1"

if not exist "%PS1_FILE%" (
    echo [실패] Deploy-From-Local.ps1을 찾을 수 없습니다.
    echo 이 파일과 같은 폴터 또는 deploy\ 폴터에 있어야 합니다.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   LogisticsRisk VDI 배포 (원클릭)
echo ==========================================
echo.
echo 프로젝트: %PROJECT_DIR%
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1_FILE%" -Target "%PROJECT_DIR%"

if errorlevel 1 (
    echo.
    echo [실패] 배포 중 오류가 발생했습니다. 위 메시지를 확인하세요.
    echo.
    pause
    exit /b 1
)

echo.
pause
exit /b 0
