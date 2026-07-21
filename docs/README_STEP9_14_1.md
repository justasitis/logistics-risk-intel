# Step 9.14.1 - Windows PowerShell UTF-8 BOM hotfix

## Cause
The Step 9.14 PowerShell scripts were stored as UTF-8 without BOM. Windows PowerShell 5.1 can read such files using the system ANSI code page. Korean text can then be corrupted and the parser may report a missing string terminator or an unmatched try block.

## Changes
- All PowerShell scripts are saved as UTF-8 with BOM and CRLF.
- Verification markers and console messages use ASCII where possible.
- Application payload is the same as Step 9.14.
- No environment variable and no api_server.py change.

## Use when Step 9.14 was already applied
Run only verification:

```powershell
$Patch = "<extracted-folder>\logistics_risk_step9_14_1_external_mi_sharepoint_powershell_hotfix"
& "$Patch\tools\verify_step9_14_1.ps1" -ProjectRoot (Get-Location).Path -SkipFrontendBuild
```

Then run the frontend build separately:

```powershell
cd .\frontend
npm run build
cd ..
```

## Clean reapplication

```powershell
$Patch = "<extracted-folder>\logistics_risk_step9_14_1_external_mi_sharepoint_powershell_hotfix"
& "$Patch\tools\backup_step9_14_1.ps1" -ProjectRoot (Get-Location).Path
& "$Patch\tools\apply_step9_14_1.ps1" -ProjectRoot (Get-Location).Path
& "$Patch\tools\verify_step9_14_1.ps1" -ProjectRoot (Get-Location).Path -SkipFrontendBuild
```
