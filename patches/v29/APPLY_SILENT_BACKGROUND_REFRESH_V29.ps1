param(
  [string]$AppRoot = 'D:\SagarSystemHealthMonitor',
  [switch]$CheckOnly,
  [switch]$Apply,
  [switch]$Rollback
)
$ErrorActionPreference='Stop'
$Target=Join-Path $AppRoot 'public\app.js'
$BackupRoot=Join-Path $AppRoot 'SAFE_BACKUPS'
$StateFile=Join-Path $BackupRoot 'SILENT_BACKGROUND_REFRESH_V29_LAST_BACKUP.txt'
$BlockFile=Join-Path $PSScriptRoot 'SILENT_BACKGROUND_REFRESH_V29.block.js'
$Start='/* SILENT_BACKGROUND_REFRESH_SAFE_FIX_V29_START'
$End='/* SILENT_BACKGROUND_REFRESH_SAFE_FIX_V29_END */'
function Log($m){Write-Host "[V29 Silent Refresh] $m"}
function Hash($p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}

if($Rollback){
  if(!(Test-Path -LiteralPath $StateFile)){throw "Rollback state file not found: $StateFile"}
  $b=(Get-Content -LiteralPath $StateFile -Raw).Trim()
  if(!(Test-Path -LiteralPath $b)){throw "Backup not found: $b"}
  Copy-Item -LiteralPath $b -Destination $Target -Force
  Log "Rollback complete from: $b"
  Log "Current SHA256: $(Hash $Target)"
  exit 0
}

if(!(Test-Path -LiteralPath $Target)){throw "Target not found: $Target"}
if(!(Test-Path -LiteralPath $BlockFile)){throw "Package block not found: $BlockFile"}
$text=[System.IO.File]::ReadAllText($Target)
Log "Target: $Target"
Log "Current SHA256: $(Hash $Target)"

$required=@(
  '/* SELECTED_CLIENT_LIVE_REFRESH_SAFE_FIX_V25_START',
  '/* UI_SEARCH_MOBILE_SMOOTHNESS_SAFE_FIX_V26_START',
  '/* MOBILE_FIRST_LAYOUT_SAFE_FIX_V27_START',
  '/* UI_TIMER_SMOOTHNESS_SAFE_FIX_V28_APPLIED */'
)
$missing=@()
foreach($r in $required){if($text.IndexOf($r,[System.StringComparison]::Ordinal)-lt 0){$missing+=$r}}
if($missing.Count -gt 0){
  Log 'SAFETY STOP: required V25-V28 baseline is incomplete. Nothing changed.'
  $missing|ForEach-Object{Write-Host "  Missing: $_"}
  Log 'Apply/verify the earlier safe fixes first, then run V29 CheckOnly again.'
  exit 2
}

$sc=([regex]::Matches($text,[regex]::Escape($Start))).Count
$ec=([regex]::Matches($text,[regex]::Escape($End))).Count
if($sc -eq 1 -and $ec -eq 1){Log 'V29 is already installed.'; if($CheckOnly){Log 'CHECK ONLY PASSED (already installed).'}; exit 0}
if($sc -ne 0 -or $ec -ne 0){throw 'SAFETY STOP: partial/duplicate V29 marker found. Nothing changed.'}

$anchors=@(
  'async function refresh(manual=false)',
  'function showBanner(show)',
  'setInterval(()=>{ if(state.authenticated && state.autoRefresh) refresh(false); },DASHBOARD_POLL_SECONDS*1000);',
  "const DASHBOARD_POLL_SECONDS = 5;"
)
foreach($a in $anchors){
  if($text.IndexOf($a,[System.StringComparison]::Ordinal)-lt 0){
    Log "SAFETY STOP: refresh anchor not found: $a"
    Log 'Nothing was changed.'
    exit 3
  }
}
Log 'Existing 5-second background polling anchor verified.'
Log 'V25-V28 baseline verified.'
Log 'V29 will hide automatic-refresh banners and suppress refresh-time animations/flicker only.'
Log 'Manual Refresh remains available.'
Log 'No server.py / DB / API / client / heartbeat / inventory-data changes are included.'

if($CheckOnly -or -not $Apply){
  Log 'CHECK ONLY PASSED. Nothing was changed.'
  Log 'Run again with -Apply when ready.'
  exit 0
}

$block=Get-Content -LiteralPath $BlockFile -Raw
if($block.IndexOf($Start,[System.StringComparison]::Ordinal)-lt 0 -or $block.IndexOf($End,[System.StringComparison]::Ordinal)-lt 0){throw 'Packaged V29 block self-check failed.'}
New-Item -ItemType Directory -Force -Path $BackupRoot|Out-Null
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$bd=Join-Path $BackupRoot ("SILENT_BACKGROUND_REFRESH_V29_"+$stamp)
New-Item -ItemType Directory -Force -Path $bd|Out-Null
$backup=Join-Path $bd 'app.js'
Copy-Item -LiteralPath $Target -Destination $backup -Force
[System.IO.File]::WriteAllText($StateFile,$backup,[System.Text.UTF8Encoding]::new($false))
Log "Backup created: $backup"

try{
  [System.IO.File]::AppendAllText($Target,"`r`n"+$block.Trim()+"`r`n",[System.Text.UTF8Encoding]::new($false))
  $verify=[System.IO.File]::ReadAllText($Target)
  if((([regex]::Matches($verify,[regex]::Escape($Start))).Count)-ne 1 -or (([regex]::Matches($verify,[regex]::Escape($End))).Count)-ne 1){throw 'Post-write V29 marker verification failed.'}
  $node=Get-Command node -ErrorAction SilentlyContinue
  if($node){
    & $node.Source --check $Target
    if($LASTEXITCODE -ne 0){throw "node --check failed with exit code $LASTEXITCODE"}
    Log 'JavaScript syntax check: PASS'
  } else {Log 'Node.js not found; syntax check skipped. Backup/rollback remains available.'}
  Log "Applied successfully. New SHA256: $(Hash $Target)"
  Log 'No server restart was performed.'
  Log 'Automatic refresh is now silent; use Ctrl+F5 once, then observe normal live data updates.'
  Log "Rollback: powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Rollback"
}catch{
  Log "ERROR: $($_.Exception.Message)"
  Copy-Item -LiteralPath $backup -Destination $Target -Force
  Log 'Automatic rollback completed.'
  throw
}
