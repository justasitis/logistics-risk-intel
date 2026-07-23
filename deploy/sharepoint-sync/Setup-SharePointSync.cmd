@echo off
chcp 65001 >nul
setlocal EnableExtensions

rem =====================================================
rem Setup-SharePointSync.cmd (팀원 PC용, 1회 실행)
rem SharePoint의 LogisticsRisk 폴터를 본인 PC에 동기화 연결한다.
rem 이 파일은 deploy\sharepoint-sync\ 폴터에 있다.
rem =====================================================

set "SCRIPT_DIR=%~dp0"

echo.
echo ==========================================
echo   SharePoint 폴터 동기화 설치
echo ==========================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%Install-OneDriveSpecificFolderSync_v1.5.ps1" -DefinitionPath "%SCRIPT_DIR%folder-sync-definition.json"

if errorlevel 1 (
    echo.
    echo [실패] 동기화 설치 중 오류가 발생했습니다.
    echo OneDrive(회사 계정) 로그인 상태를 확인하세요.
    echo.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   경로 표준화 (PC마다 다른 동기화 폴터명 보정)
echo ==========================================
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%Repair-SharePointPath.ps1"

if errorlevel 1 (
    echo.
    echo [주의] 경로 표준화에 실패했습니다.
    echo 동기화가 완료된 뒤 Repair-SharePointPath.ps1 만 다시 실행하세요.
    echo.
)

echo.
echo ==========================================
echo   설치 완료
echo ==========================================
echo.
echo C:\Users\%USERNAME%\SK on\Global물류팀 - LogisticsRisk
echo 경로에 폴터가 생겼는지 확인하세요.
echo.
pause
exit /b 0
