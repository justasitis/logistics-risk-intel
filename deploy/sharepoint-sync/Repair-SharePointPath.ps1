# Repair-SharePointPath.ps1
# OneDrive가 PC마다 다르게 만드는 SharePoint 동기화 폴터명을
# 표준 경로(C:\Users\<사용자>\SK on\M365_TtNUJmLE - 데이터_접근금지)로 맞춘다.
#
# 동작:
#   1. 표준 경로가 이미 있으면 아무것도 하지 않는다.
#   2. OneDrive 루트 후보 아래에서 AIS 또는 MI 하위 폴터를 가진 동기화 폴터를
#      찾는다 ("*LogisticsRisk*" 또는 "*데이터_접근금지*" 이름).
#   3. 찾으면 표준 경로에 Junction을 만든다 (관리자 권한 불필요).
#
# 사용: powershell -NoProfile -ExecutionPolicy Bypass -File Repair-SharePointPath.ps1

[CmdletBinding()]
param(
    # 표준 경로 (앱의 .env와 동일해야 함)
    [string]$CanonicalPath = "C:\Users\$env:USERNAME\SK on\M365_TtNUJmLE - 데이터_접근금지",

    # 테스트/특수 환경용: OneDrive 루트 검색 위치를 직접 지정
    [string[]]$SearchRoots = @()
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "[1/3] 표준 경로 확인: $CanonicalPath"

if (Test-Path -LiteralPath $CanonicalPath) {
    Write-Host "      이미 존재합니다. 작업 없이 종료합니다."
    exit 0
}

if ($SearchRoots.Count -eq 0) {
    $SearchRoots = @(
        "C:\Users\$env:USERNAME\SK on",
        "C:\Users\$env:USERNAME\OneDrive - SK on",
        "C:\Users\$env:USERNAME"
    )
}

Write-Host "[2/3] 실제 동기화 폴터 검색 중..."

$found = $null
foreach ($root in $SearchRoots) {
    if (-not (Test-Path -LiteralPath $root)) { continue }
    $candidates = Get-ChildItem -LiteralPath $root -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -like "*LogisticsRisk*" -or $_.Name -like "*데이터_접근금지*" }
    foreach ($candidate in $candidates) {
        $hasData = (Test-Path -LiteralPath (Join-Path $candidate.FullName "AIS")) -or
                   (Test-Path -LiteralPath (Join-Path $candidate.FullName "MI"))
        if ($hasData) {
            $found = $candidate.FullName
            break
        }
    }
    if ($found) { break }
}

if (-not $found) {
    Write-Host ""
    Write-Host "[실패] 동기화된 데이터 폴터(LogisticsRisk/데이터_접근금지)를 찾지 못했습니다."
    Write-Host "       OneDrive 동기화가 완료됐는지(파일 온디맨드 해제 포함) 확인 후 다시 실행하세요."
    exit 1
}

Write-Host "      발견: $found"

Write-Host "[3/3] 표준 경로로 연결(Junction) 생성 중..."

$parent = Split-Path -Parent $CanonicalPath
if (-not (Test-Path -LiteralPath $parent)) {
    New-Item -ItemType Directory -Path $parent -Force | Out-Null
}

New-Item -ItemType Junction -Path $CanonicalPath -Value $found | Out-Null

Write-Host ""
Write-Host "완료: $CanonicalPath  -->  $found"
