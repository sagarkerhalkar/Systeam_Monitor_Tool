param(
  [switch]$CheckOnly,
  [switch]$Apply,
  [switch]$Rollback,
  [string]$AppRoot='D:\SagarSystemHealthMonitor'
)
$ErrorActionPreference='Stop'
$Target=Join-Path $AppRoot 'public\app.js'
$BackupRoot=Join-Path $AppRoot 'SAFE_BACKUPS'
$StateFile=Join-Path $BackupRoot 'V31_CORE_NO_AUTO_RERENDER_LAST_BACKUP.txt'
$HelperFile=Join-Path $PSScriptRoot 'V31_CORE_NO_AUTO_RERENDER_HELPERS.js'
$Marker='V31_CORE_NO_AUTO_RERENDER_HELPERS_START'
function Log($m){Write-Host "[V31 Core Refresh] $m"}
function Hash($p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}
if($Rollback){
  if(!(Test-Path $StateFile)){throw "No V31 rollback state found: $StateFile"}
  $b=(Get-Content $StateFile -Raw).Trim();if(!(Test-Path $b)){throw "Backup not found: $b"}
  Copy-Item $b $Target -Force;Log "Rollback complete from: $b";Log "Current SHA256: $(Hash $Target)";exit 0
}
if(!(Test-Path $Target)){throw "Target not found: $Target"}
if(!(Test-Path $HelperFile)){throw "Helper file missing: $HelperFile"}
$text=[IO.File]::ReadAllText($Target)
Log "Target: $Target";Log "Current SHA256: $(Hash $Target)"
if($text.Contains('V30_TYPING_PROTECTED_SILENT_REFRESH')){Log 'SAFETY STOP: V30 is still present. Roll back V30 first.';exit 2}
$req=@('SELECTED_CLIENT_LIVE_REFRESH_SAFE_FIX_V25_START','UI_SEARCH_MOBILE_SMOOTHNESS_SAFE_FIX_V26_START','MOBILE_FIRST_LAYOUT_SAFE_FIX_V27_START','UI_TIMER_SMOOTHNESS_SAFE_FIX_V28_APPLIED','SILENT_BACKGROUND_REFRESH_SAFE_FIX_V29_START')
foreach($r in $req){if(!$text.Contains($r)){Log "SAFETY STOP: required baseline marker missing: $r";exit 3}}
if($text.Contains($Marker)){Log 'V31 already installed.';if($CheckOnly){Log 'CHECK ONLY PASSED (already installed).'};exit 0}
$rx1='if\(!manual\s*&&\s*quietPages\.has\(state\.page\)\)\{\s*state\.pendingUpdate=true;\s*showBanner\(true\);\s*return;\s*\}\s*hydrateSelectors\(\);\s*state\.pendingUpdate=false;\s*showBanner\(false\);\s*renderAll\(\);\s*applyRoleControls\(\);'
$m1=[regex]::Matches($text,$rx1)
if($m1.Count -ne 1){Log "SAFETY STOP: expected 1 core auto-render branch, found $($m1.Count).";exit 4}
$old2=@'
    }).then(function(d){
      if(d && selectedId(page)===mid) renderPage(page);
      return d;
'@
if(([regex]::Matches($text,[regex]::Escape($old2))).Count -ne 1){Log 'SAFETY STOP: V25 overview-render anchor not found exactly once.';exit 5}
Log 'Core 5-second refresh branch verified.'
Log 'V25 selected-machine auto-render branch verified.'
Log 'Automatic polling will continue, but automatic full-page render will be removed.'
Log 'Typing/search/scroll DOM will not be recreated by background polling.'
Log 'Manual Refresh, tab changes and machine selection keep normal full render behavior.'
Log 'No server.py / DB / API / client / heartbeat / inventory-data changes are included.'
if($CheckOnly -or !$Apply){Log 'CHECK ONLY PASSED. Nothing was changed.';Log 'Run again with -Apply when ready.';exit 0}
New-Item -ItemType Directory -Force -Path $BackupRoot|Out-Null
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss';$bd=Join-Path $BackupRoot ("V31_CORE_NO_AUTO_RERENDER_"+$stamp);New-Item -ItemType Directory -Force -Path $bd|Out-Null
$backup=Join-Path $bd 'app.js';Copy-Item $Target $backup -Force;[IO.File]::WriteAllText($StateFile,$backup,[Text.UTF8Encoding]::new($false));Log "Backup created: $backup"
try{
  $new1=@'
if(!manual){
      state.pendingUpdate=false;
      showBanner(false);
      try{ if(window.v31ApplyStableLiveValues) window.v31ApplyStableLiveValues(data); }catch(_v31e){}
      return;
    }
    hydrateSelectors(); state.pendingUpdate=false; showBanner(false); renderAll(); applyRoleControls();
'@
  $new=[regex]::Replace($text,$rx1,[System.Text.RegularExpressions.MatchEvaluator]{param($m)$new1},1)
  $new2=@'
    }).then(function(d){
      if(d && selectedId(page)===mid){
        if(reason==='overview-updated'){
          try{ if(window.v31ApplySelectedDetailValues) window.v31ApplySelectedDetailValues(page,d); }catch(_v31e){}
        }else{
          renderPage(page);
        }
      }
      return d;
'@
  $new=$new.Replace($old2,$new2)
  $helper=[IO.File]::ReadAllText($HelperFile)
  $new=$new.TrimEnd()+"`r`n`r`n"+$helper.Trim()+"`r`n"
  $bytes=[IO.File]::ReadAllBytes($Target);$bom=($bytes.Length-ge3 -and $bytes[0]-eq0xEF -and $bytes[1]-eq0xBB -and $bytes[2]-eq0xBF)
  $enc=[Text.UTF8Encoding]::new($bom);[IO.File]::WriteAllText($Target,$new,$enc)
  $node=Get-Command node -ErrorAction SilentlyContinue
  if($node){& $node.Source --check $Target;if($LASTEXITCODE-ne0){throw 'node --check failed'};Log 'JavaScript syntax check: PASS'}else{Log 'Node.js not found; syntax check skipped.'}
  Log "Applied successfully. New SHA256: $(Hash $Target)"
  Log 'No server restart required. Ctrl+F5 once, then leave the page open for at least 30 seconds.'
  Log "Rollback: powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Rollback"
}catch{Copy-Item $backup $Target -Force;Log 'ERROR - backup restored automatically.';throw}
