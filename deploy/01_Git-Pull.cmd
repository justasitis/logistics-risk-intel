@echo off
chcp 65001 >nul
setlocal EnableExtensions

rem =====================================================
rem 01_Git-Pull.cmd (로컬 PC용)
rem GitHub repo의 최신 코드를 로컬 프로젝트 폴터로 가져온다.
rem - 프로젝트가 없으면 최초 연결(init+fetch)
rem - 있으면 pull --ff-only
rem 이 파일을 C:\Work\logistics-risk-intel 에 두고 실행한다.
rem =====================================================

set "WORK_DIR=C:\Work"
set "PROJECT_NAME=logistics-risk-intel"
set "PROJECT_DIR=%WORK_DIR%\%PROJECT_NAME%"
set "REPO_URL=https://github.com/justasitis/logistics-risk-intel.git"
set "BRANCH=main"

echo.
echo ==========================================
echo   Logistics Risk Intel Git Update
echo ==========================================
echo.

if not exist "%PROJECT_DIR%" (
    mkdir "%PROJECT_DIR%"
)

cd /d "%PROJECT_DIR%"

rem --- 프로젝트가 아직 git 저장소가 아니면 최초 연결 ---
if not exist "%PROJECT_DIR%\.git" (
    echo [최초 실행] GitHub 저장소와 연결합니다...
    echo.

    git init
    if errorlevel 1 goto :ERROR

    git remote add origin "%REPO_URL%"
    if errorlevel 1 (
        echo [실패] remote 등록 실패. REPO_URL을 확인하세요.
        goto :ERROR
    )

    git fetch origin
    if errorlevel 1 (
        echo [실패] fetch 실패. GitHub 로그인 또는 네트워크를 확인하세요.
        goto :ERROR
    )

    git checkout -t "origin/%BRANCH%"
    if errorlevel 1 (
        echo [실패] checkout 실패. 폴터 내 기존 파일과 충돌 여부를 확인하세요.
        goto :ERROR
    )

    echo.
    echo [완료] 프로젝트를 처음 내려받았습니다.
    goto :SUCCESS
)

rem --- 기존 저장소면 pull ---
echo [1/3] 현재 브랜치 확인
git branch --show-current
echo.

echo [2/3] 로컬 변경사항 확인
git status --short

for /f "delims=" %%A in ('git status --porcelain') do (
    echo.
    echo [중단] 로컬 프로젝트에 수정된 파일이 있습니다.
    echo 변경사항을 먼저 commit, stash 또는 삭제해야 합니다.
    echo.
    git status
    goto :ERROR
)

echo.
echo [3/3] 최신 코드 가져오기
git pull --ff-only origin "%BRANCH%"
if errorlevel 1 (
    echo.
    echo [실패] Git pull에 실패했습니다.
    goto :ERROR
)

:SUCCESS
echo.
echo ==========================================
echo   Git 업데이트 완료
echo ==========================================
echo.
cd /d "%PROJECT_DIR%"
git log -1 --format="Commit: %%h"
git log -1 --format="Date: %%ci"
git log -1 --format="Message: %%s"
echo.
echo 프로젝트 위치: %PROJECT_DIR%
echo.
echo 이제 VDI에서 02_VDI-Deploy.cmd 를 실행하세요.
echo.
pause
exit /b 0

:ERROR
echo.
echo ==========================================
echo   작업 실패
echo ==========================================
echo.
pause
exit /b 1
