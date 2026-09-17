param(
  [switch]$CheckOnly,
  [switch]$Apply,
  [switch]$Rollback,
  [string]$RepoPath = 'D:\SagarSystemHealthMonitor'
)
$ErrorActionPreference='Stop'
$prefix='[V31 Incremental DOM]'
$target=Join-Path $RepoPath 'public\app.js'
$backupRoot=Join-Path $RepoPath 'SAFE_BACKUPS'
$block=Join-Path $PSScriptRoot 'V31_INCREMENTAL_DOM_LIVE_UPDATE.js'
$marker='V31_INCREMENTAL_DOM_LIVE_UPDATE_START'
function Say([string]$s){Write-Host "$prefix $s"}
function Hash([string]$p){(Get-FileHash $p -Algorithm SHA256).Hash.ToLowerInvariant()}
if($Rollback){
  $b=Get-ChildItem $backupRoot -Directory -ErrorAction SilentlyContinue | Where-Object {$_.Name -like 'V31_INCREMENTAL_DOM_*'} | Sort-Object LastWriteTime -Descending | Select-Object -First 1
  if(!$b){throw "$prefix No V31 backup found."}
  Copy-Item (Join-Path $b.FullName 'app.js') $target -Force
  Say "Rollback restored: $($b.FullName)\app.js"; Say "Current SHA256: $(Hash $target)"; exit 0
}
if(!(Test-Path $target)){throw "$prefix Target not found: $target"}
if(!(Test-Path $block)){throw "$prefix V31 block missing: $block"}
$text=[IO.File]::ReadAllText($target)
Say "Target: $target"; Say "Current SHA256: $(Hash $target)"
if($text.Contains($marker)){Say 'V31 is already installed. Nothing to do.';exit 0}
$anchors=@('async function refresh(manual=false)','setInterval(()=>{ if(state.authenticated && state.autoRefresh) refresh(false); }','V20_6_FAST_LAZY_UI_START','CLIENT_HOST_LOOKUP_V16_START')
foreach($a in $anchors){if(!$text.Contains($a)){throw "$prefix SAFETY STOP: required anchor missing: $a`nNothing was changed."};Say "Anchor OK: $a"}
if($CheckOnly -or !$Apply){
  Say 'Automatic 5-second poll will remain enabled.'
  Say 'Automatic poll will no longer call renderAll or replace page/search DOM.'
  Say 'Manual Refresh and user-triggered page/machine renders remain unchanged.'
  Say 'Dashboard/Machine360/Network/common live values are patched in-place.'
  Say 'No server.py / DB / API / client / heartbeat / inventory-data changes are included.'
  Say 'CHECK ONLY PASSED. Nothing was changed.'; Say 'Run again with -Apply when ready.'; exit 0
}
New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss';$backup=Join-Path $backupRoot "V31_INCREMENTAL_DOM_$stamp";New-Item -ItemType Directory -Path $backup -Force|Out-Null
Copy-Item $target (Join-Path $backup 'app.js') -Force;Say "Backup created: $backup\app.js"
$patch=[IO.File]::ReadAllText($block);$new=$text.TrimEnd()+"`r`n`r`n"+$patch.Trim()+"`r`n";[IO.File]::WriteAllText($target,$new,(New-Object Text.UTF8Encoding($false)))
$node=Get-Command node -ErrorAction SilentlyContinue
if($node){& node --check $target;if($LASTEXITCODE -ne 0){Copy-Item (Join-Path $backup 'app.js') $target -Force;throw "$prefix JavaScript syntax FAILED. Backup restored."};Say 'JavaScript syntax check: PASS'}else{Say 'Node.js not found; syntax check skipped.'}
Say "Applied successfully. New SHA256: $(Hash $target)"
Say 'No server restart required. Ctrl+F5 once, then test reading + typing for at least 30 seconds.'
Say "Rollback: powershell -ExecutionPolicy Bypass -File `"$($MyInvocation.MyCommand.Path)`" -Rollback"
