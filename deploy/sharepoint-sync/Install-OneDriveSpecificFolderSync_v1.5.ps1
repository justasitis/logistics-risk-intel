<#
.SYNOPSIS
  folder-sync-definition.json의 SharePoint 특정 폴더를 현재 사용자 OneDrive에 연결합니다. (v1.5)

.DESCRIPTION
  Windows PowerShell 5.1에서는 param() 기본값 안에서 $PSScriptRoot를 참조할 때
  빈 문자열로 평가되는 환경이 있어, DefinitionPath 기본 경로를 param 블록 이후에 계산합니다.

.EXAMPLE
  powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File ".\Install-OneDriveSpecificFolderSync.ps1"

.EXAMPLE
  powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File ".\Install-OneDriveSpecificFolderSync.ps1" `
    -DefinitionPath ".\folder-sync-definition.json"

.EXAMPLE
  powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File ".\Install-OneDriveSpecificFolderSync.ps1" `
    -DefinitionPath ".\folder-sync-definition.json" `
    -UserEmail "team.member@company.com"
#>

[CmdletBinding()]
param(
    [string]$DefinitionPath,
    [string]$UserEmail,
    [switch]$CreateLogonTask,
    [switch]$Force
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Windows PowerShell 5.1 호환: param() 기본값에서 $PSScriptRoot를 사용하지 않는다.
$scriptRoot = $PSScriptRoot
if ([string]::IsNullOrWhiteSpace($scriptRoot)) {
    $scriptFile = $MyInvocation.MyCommand.Path
    if (-not [string]::IsNullOrWhiteSpace($scriptFile)) {
        $scriptRoot = Split-Path -Parent $scriptFile
    }
}
if ([string]::IsNullOrWhiteSpace($scriptRoot)) {
    $scriptRoot = (Get-Location).Path
}

if ([string]::IsNullOrWhiteSpace($DefinitionPath)) {
    $DefinitionPath = Join-Path -Path $scriptRoot -ChildPath 'folder-sync-definition.json'
}
elseif (-not [System.IO.Path]::IsPathRooted($DefinitionPath)) {
    $DefinitionPath = Join-Path -Path (Get-Location).Path -ChildPath $DefinitionPath
}

function Get-CurrentBusinessEmails {
    $root = 'HKCU:\Software\Microsoft\OneDrive\Accounts'
    if (-not (Test-Path -LiteralPath $root)) { return @() }

    $businessKeys = @(
        Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue |
            Where-Object { $_.PSChildName -like 'Business*' }
    )

    @(
        foreach ($key in $businessKeys) {
            try {
                $account = Get-ItemProperty -LiteralPath $key.PSPath
                $emailProperty = $account.PSObject.Properties['UserEmail']
                if ($null -ne $emailProperty -and
                    -not [string]::IsNullOrWhiteSpace([string]$emailProperty.Value)) {
                    [string]$emailProperty.Value
                }
            }
            catch {
                # 읽을 수 없는 보조 계정 키는 건너뜁니다.
            }
        }
    ) | Sort-Object -Unique
}

function Normalize-SharePointUrl {
    param([AllowNull()][string]$Url)

    if ([string]::IsNullOrWhiteSpace($Url)) { return '' }

    $value = $Url.Trim()
    try { $value = [uri]::UnescapeDataString($value) } catch {}
    $value = $value.Replace('\', '/').TrimEnd('/')

    # 절대 URL이면 호스트와 경로를 표준화한다.
    $uri = $null
    if ([uri]::TryCreate($value, [UriKind]::Absolute, [ref]$uri)) {
        $path = $uri.AbsolutePath
        try { $path = [uri]::UnescapeDataString($path) } catch {}
        $path = $path.TrimEnd('/')
        return ('{0}://{1}{2}' -f $uri.Scheme.ToLowerInvariant(), $uri.Host.ToLowerInvariant(), $path)
    }

    return $value
}

function Get-ExistingMountMatches {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FolderUrl
    )

    $providerRoot = 'HKCU:\Software\SyncEngines\Providers\OneDrive'
    if (-not (Test-Path -LiteralPath $providerRoot)) { return @() }

    $expected = Normalize-SharePointUrl -Url $FolderUrl
    if ([string]::IsNullOrWhiteSpace($expected)) { return @() }

    $matches = @(
        foreach ($key in @(Get-ChildItem -LiteralPath $providerRoot -ErrorAction SilentlyContinue)) {
            try {
                $provider = Get-ItemProperty -LiteralPath $key.PSPath

                $urlProperty = $provider.PSObject.Properties['URLNamespace']
                if ($null -eq $urlProperty -or
                    [string]::IsNullOrWhiteSpace([string]$urlProperty.Value)) {
                    continue
                }

                $actual = Normalize-SharePointUrl -Url ([string]$urlProperty.Value)
                if ([string]::IsNullOrWhiteSpace($actual)) { continue }

                # 절대 URL은 정확히 같은 폴더일 때만 일치시킨다.
                $isMatch = $actual -ieq $expected

                # 정의 파일이 서버 상대 경로인 경우에만 URL 경로 끝부분 비교를 허용한다.
                if (-not $isMatch -and $expected.StartsWith('/')) {
                    $isMatch = $actual.EndsWith($expected, [StringComparison]::OrdinalIgnoreCase)
                }

                if (-not $isMatch) { continue }

                $mountProperty = $provider.PSObject.Properties['MountPoint']
                $mountPoint = if ($null -ne $mountProperty) {
                    [string]$mountProperty.Value
                }
                else {
                    ''
                }

                $mountExists = -not [string]::IsNullOrWhiteSpace($mountPoint) -and
                    (Test-Path -LiteralPath $mountPoint -PathType Container)

                [pscustomobject]@{
                    RegistryKey = $key.PSPath
                    URLNamespace = [string]$urlProperty.Value
                    MountPoint = $mountPoint
                    MountExists = [bool]$mountExists
                }
            }
            catch {
                # 읽을 수 없는 보조 공급자 키는 건너뜁니다.
            }
        }
    )

    return $matches
}

function Encode-QueryValue {
    param([AllowNull()][object]$Value)

    if ($null -eq $Value) { return '' }
    return [uri]::EscapeDataString([string]$Value)
}

if (-not (Test-Path -LiteralPath $DefinitionPath -PathType Leaf)) {
    throw "정의 파일을 찾지 못했습니다: $DefinitionPath"
}

$DefinitionPath = (Resolve-Path -LiteralPath $DefinitionPath).Path
Write-Host "정의 파일: $DefinitionPath" -ForegroundColor DarkGray

$config = Get-Content -LiteralPath $DefinitionPath -Raw -Encoding UTF8 | ConvertFrom-Json

$completeProperty = $config.PSObject.Properties['complete']
if ($null -eq $completeProperty -or -not [bool]$completeProperty.Value) {
    $missing = @()
    $missingProperty = $config.PSObject.Properties['missingFields']
    if ($null -ne $missingProperty) {
        $missing = @($missingProperty.Value)
    }
    throw "정의 파일이 완성되지 않았습니다. 누락 필드: $($missing -join ', ')"
}

$parametersProperty = $config.PSObject.Properties['parameters']
if ($null -eq $parametersProperty -or $null -eq $parametersProperty.Value) {
    throw '정의 파일에 parameters 항목이 없습니다.'
}
$p = $parametersProperty.Value

# 특정 폴더 정의가 문서 라이브러리 루트로 잘못 추출된 경우 조기에 중단한다.
$folderNameCheckProperty = $p.PSObject.Properties['folderName']
$folderUrlCheckProperty = $p.PSObject.Properties['folderUrl']
$folderNameCheck = if ($null -ne $folderNameCheckProperty) { [string]$folderNameCheckProperty.Value } else { '' }
$folderUrlCheck = if ($null -ne $folderUrlCheckProperty) { [string]$folderUrlCheckProperty.Value } else { '' }

$normalizedFolderUrlCheck = Normalize-SharePointUrl -Url $folderUrlCheck
$folderUrlLeaf = ''
if (-not [string]::IsNullOrWhiteSpace($normalizedFolderUrlCheck)) {
    $folderUrlLeaf = ($normalizedFolderUrlCheck.TrimEnd('/') -split '/')[-1]
    try { $folderUrlLeaf = [uri]::UnescapeDataString($folderUrlLeaf) } catch {}
}

if ([string]::IsNullOrWhiteSpace($folderNameCheck) -or
    $folderNameCheck -match '(?i)(^|[/\\])RootFolder$' -or
    $folderNameCheck.Contains('/') -or
    $folderNameCheck.Contains('\\')) {
    throw "folderName이 특정 폴더명이 아닙니다: '$folderNameCheck'. LogisticsRisk처럼 폴더명만 들어가야 합니다."
}

if ([string]::IsNullOrWhiteSpace($folderUrlCheck) -or
    $normalizedFolderUrlCheck -match '(?i)/Shared Documents$' -or
    $normalizedFolderUrlCheck -match '(?i)/Documents$') {
    throw "folderUrl이 문서 라이브러리 루트를 가리킵니다: '$folderUrlCheck'. 대상 폴더까지 포함해야 합니다."
}

if (-not [string]::IsNullOrWhiteSpace($folderUrlLeaf) -and
    -not $folderUrlLeaf.Equals($folderNameCheck, [StringComparison]::OrdinalIgnoreCase)) {
    throw "folderName('$folderNameCheck')과 folderUrl의 마지막 경로('$folderUrlLeaf')가 일치하지 않습니다."
}

if ([string]::IsNullOrWhiteSpace($UserEmail)) {
    $emails = @(Get-CurrentBusinessEmails)

    if ($emails.Count -eq 1) {
        $UserEmail = [string]$emails[0]
    }
    elseif ($emails.Count -gt 1) {
        throw "OneDrive 업무 계정이 여러 개입니다. -UserEmail을 지정하십시오: $($emails -join ', ')"
    }
    else {
        throw '현재 사용자에게 로그인된 OneDrive 업무 계정을 찾지 못했습니다. OneDrive 로그인 후 다시 실행하거나 -UserEmail을 지정하십시오.'
    }
}

$folderUrlProperty = $p.PSObject.Properties['folderUrl']
$folderUrl = if ($null -ne $folderUrlProperty) { [string]$folderUrlProperty.Value } else { '' }

if (-not [string]::IsNullOrWhiteSpace($folderUrl) -and -not $Force) {
    $mountMatches = @(Get-ExistingMountMatches -FolderUrl $folderUrl)
    $activeMatches = @($mountMatches | Where-Object { $_.MountExists })
    $staleMatches = @($mountMatches | Where-Object { -not $_.MountExists })

    if ($staleMatches.Count -gt 0) {
        Write-Warning '같은 SharePoint URL의 과거 OneDrive 레지스트리 항목이 있지만 실제 로컬 마운트 폴더가 없어 무시합니다.'
        foreach ($match in $staleMatches) {
            Write-Host "  레지스트리 URL : $($match.URLNamespace)" -ForegroundColor DarkGray
            Write-Host "  이전 MountPoint: $($match.MountPoint)" -ForegroundColor DarkGray
        }
    }

    if ($activeMatches.Count -gt 0) {
        Write-Host '동일 URL에 해당하며 실제로 존재하는 OneDrive 마운트 폴더를 찾았습니다.' -ForegroundColor Green
        foreach ($match in $activeMatches) {
            Write-Host "  URL       : $($match.URLNamespace)"
            Write-Host "  MountPoint: $($match.MountPoint)"
        }
        Write-Host '위 경로가 실제 대상 폴더가 아니라면 -Force 옵션으로 중복 검사만 건너뛸 수 있습니다.' -ForegroundColor Yellow
        exit 0
    }
}

if (-not (Get-Process -Name OneDrive -ErrorAction SilentlyContinue)) {
    $oneDriveCandidates = @(
        (Join-Path -Path $env:LOCALAPPDATA -ChildPath 'Microsoft\OneDrive\OneDrive.exe'),
        (Join-Path -Path $env:ProgramFiles -ChildPath 'Microsoft OneDrive\OneDrive.exe')
    )

    if (-not [string]::IsNullOrWhiteSpace(${env:ProgramFiles(x86)})) {
        $oneDriveCandidates += Join-Path -Path ${env:ProgramFiles(x86)} -ChildPath 'Microsoft OneDrive\OneDrive.exe'
    }

    $oneDriveExe = $oneDriveCandidates |
        Where-Object { -not [string]::IsNullOrWhiteSpace($_) -and (Test-Path -LiteralPath $_ -PathType Leaf) } |
        Select-Object -First 1

    if ([string]::IsNullOrWhiteSpace($oneDriveExe)) {
        throw 'OneDrive.exe를 찾지 못했습니다.'
    }

    Start-Process -FilePath $oneDriveExe
    Start-Sleep -Seconds 10
}

$orderedNames = @(
    'scope', 'siteId', 'webId', 'webTitle', 'listId', 'listTitle', 'userEmail',
    'listTemplateTypeId', 'webUrl', 'webLogoUrl', 'webTemplate', 'isSiteAdmin',
    'folderId', 'folderName', 'folderUrl'
)

$values = [ordered]@{}
foreach ($name in $orderedNames) {
    if ($name -eq 'userEmail') {
        $values[$name] = $UserEmail
        continue
    }

    $property = $p.PSObject.Properties[$name]
    if ($null -ne $property -and
        -not [string]::IsNullOrWhiteSpace([string]$property.Value)) {
        $values[$name] = [string]$property.Value
    }
}
$values['scope'] = 'OPENFOLDER'

$requiredNames = @('siteId', 'webId', 'listId', 'folderId', 'folderName', 'folderUrl', 'webUrl')
$missingRequired = @(
    foreach ($requiredName in $requiredNames) {
        if (-not $values.Contains($requiredName) -or
            [string]::IsNullOrWhiteSpace([string]$values[$requiredName])) {
            $requiredName
        }
    }
)
if ($missingRequired.Count -gt 0) {
    throw "연결 요청에 필요한 값이 없습니다: $($missingRequired -join ', ')"
}

$queryParts = @(
    foreach ($entry in $values.GetEnumerator()) {
        '{0}={1}' -f $entry.Key, (Encode-QueryValue -Value $entry.Value)
    }
)
$query = $queryParts -join '&'
$odopenUri = 'odopen://sync/?' + $query

Write-Host 'OneDrive에 SharePoint 특정 폴더 연결을 요청합니다.' -ForegroundColor Cyan
Write-Host "사용자: $UserEmail"
Write-Host "폴더: $folderUrl"

Start-Process -FilePath $odopenUri

if ($CreateLogonTask) {
    $folderNameProperty = $p.PSObject.Properties['folderName']
    $folderName = if ($null -ne $folderNameProperty) { [string]$folderNameProperty.Value } else { 'SharePointFolder' }

    $taskName = 'OneDriveSpecificFolderSync_' +
        ([regex]::Replace($folderName, '[^0-9A-Za-z가-힣_-]', '_'))

    $scriptPath = $MyInvocation.MyCommand.Path
    if ([string]::IsNullOrWhiteSpace($scriptPath)) {
        throw '로그온 작업을 만들기 위한 현재 스크립트 경로를 확인할 수 없습니다.'
    }

    $arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`" -DefinitionPath `"$DefinitionPath`" -UserEmail `"$UserEmail`""
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arguments
    $trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited

    try {
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
        Write-Host "로그온 재확인 작업을 등록했습니다: $taskName" -ForegroundColor Green
    }
    catch {
        Write-Warning "로그온 작업 등록이 차단되었습니다. 설치 요청 자체는 실행되었습니다. $($_.Exception.Message)"
    }
}

Write-Host '요청을 전송했습니다. OneDrive 알림 또는 파일 탐색기에서 연결 결과를 확인하십시오.' -ForegroundColor Green
