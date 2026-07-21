@echo off
rem 로컬 PC에서 GitHub 최신 코드만 받아오는 스크립트.
rem PROJECT 경로를 로컬 clone 위치에 맞게 수정하세요.
setlocal EnableExtensions

set "PROJECT=C:\Work\logistics-risk-intel"

echo.
echo ==========================================
echo   LogisticsRisk Git 업데이트
echo ==========================================
echo.

if not exist "%PROJECT%\.git" (
    echo [실패] Git 프로젝트가 아닙니다: %PROJECT%
    pause
    exit /b 1
)

cd /d "%PROJECT%"

echo [1/2] 로컬 변경사항 확인 중...
git status --short

for /f "delims=" %%A in ('git status --porcelain') do (
    echo.
    echo [중단] 로컬에서 수정된 파일이 있습니다.
    echo 변경사항을 commit, stash 또는 정리한 후 다시 실행하세요.
    pause
    exit /b 1
)

echo.
echo [2/2] Git pull 실행 중...
git pull --ff-only

if errorlevel 1 (
    echo.
    echo [실패] Git pull에 실패했습니다.
    pause
    exit /b 1
)

echo.
echo ==========================================
echo   Git 업데이트 완료
echo ==========================================
echo.
git log -1 --format="Commit: %%h / %%ci / %%s"
echo.
echo 이제 VDI에서 Deploy-From-Local.ps1 -Preview 를 실행하세요.
pause
