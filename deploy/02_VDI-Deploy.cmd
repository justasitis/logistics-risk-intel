@echo off
chcp 65001 >nul
setlocal EnableExtensions

rem =====================================================
rem 02_VDI-Deploy.cmd (VDI용)
rem 로컬 PC(\\Client\C$)의 최신 코드를 VDI 프로젝트에 반영한다.
rem 더블클릭으로 실행하면 된다. 이 파일은 deploy\ 폴터에 있다.
rem =====================================================

set "SCRIPT_DIR=%~dp0"
set "PROJECT_DIR=%SCRIPT_DIR%.."

echo.
echo ==========================================
echo   LogisticsRisk VDI 배포 (원클릭)
echo ==========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%Deploy-From-Local.ps1" -Target "%PROJECT_DIR%"

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
