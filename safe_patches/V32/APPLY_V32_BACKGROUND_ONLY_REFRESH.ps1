param(
  [switch]$CheckOnly,
  [switch]$Apply,
  [switch]$Rollback,
  [string]$AppRoot='D:\SagarSystemHealthMonitor'
)

$ErrorActionPreference='Stop'
$Target=Join-Path $AppRoot 'public\app.js'
$BackupRoot=Join-Path $AppRoot 'SAFE_BACKUPS'
$StateFile=Join-Path $BackupRoot 'V32_BACKGROUND_ONLY_POLL_LAST_BACKUP.txt'
$ExpectedSha='9bfa4ee98c73c0e2526e777b9b25f21968ec9964df13754b5e0b9138d07704bf'
$Marker='/* V32_BACKGROUND_ONLY_POLL_START */'

function Log($m){Write-Host "[V32 Background Refresh] $m"}
function GetSha($p){(Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()}

if($Rollback){
  if(!(Test-Path -LiteralPath $StateFile)){throw "No V32 rollback state found: $StateFile"}
  $b=(Get-Content -LiteralPath $StateFile -Raw).Trim()
  if(!(Test-Path -LiteralPath $b)){throw "Backup not found: $b"}
  Copy-Item -LiteralPath $b -Destination $Target -Force
  Log "Rollback complete from: $b"
  Log "Current SHA256: $(GetSha $Target)"
  exit 0
}

if(!(Test-Path -LiteralPath $Target)){throw "Target not found: $Target"}
$text=[IO.File]::ReadAllText($Target)
$sha=GetSha $Target

Log "Target: $Target"
Log "Current SHA256: $sha"

if($text.Contains('V30_TYPING_PROTECTED_SILENT_REFRESH')){
  Log 'SAFETY STOP: V30 regression marker is present. Roll back V30 first.'
  exit 2
}

if(!$text.Contains('V31_CORE_NO_AUTO_RERENDER_HELPERS_START')){
  Log 'SAFETY STOP: V31 baseline marker is missing.'
  exit 3
}

if($text.Contains($Marker)){
  Log 'V32 is already installed.'
  if($CheckOnly){Log 'CHECK ONLY PASSED (already installed).'}
  exit 0
}

if($sha -ne $ExpectedSha){
  Log 'SAFETY STOP: app.js is not the exact diagnosed baseline.'
  Log "Expected: $ExpectedSha"
  Log "Current : $sha"
  Log 'Nothing was changed.'
  exit 4
}

$old="setInterval(()=>{ if(state.authenticated && state.autoRefresh) refresh(false); },DASHBOARD_POLL_SECONDS*1000);"
$count=([regex]::Matches($text,[regex]::Escape($old))).Count
if($count -ne 1){
  Log "SAFETY STOP: expected exactly one 5-second refresh timer anchor, found $count."
  Log 'Nothing was changed.'
  exit 5
}

Log 'Exact diagnosed baseline verified.'
Log 'Only the browser automatic refresh timer will be changed.'
Log 'The 5-second poll will fetch /api/overview directly into state without calling refresh(false).'
Log 'No hydrateSelectors(), renderAll(), page rebuild, search rebuild, or banner will run from the automatic poll.'
Log 'Manual Refresh, tab changes, machine selection and all backend/client collection remain unchanged.'
Log 'Client/server monitoring continues in the background exactly as before.'

if($CheckOnly -or !$Apply){
  Log 'CHECK ONLY PASSED. Nothing was changed.'
  Log 'Run again with -Apply when ready.'
  exit 0
}

New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
$stamp=Get-Date -Format 'yyyyMMdd_HHmmss'
$bd=Join-Path $BackupRoot ("V32_BACKGROUND_ONLY_POLL_"+$stamp)
New-Item -ItemType Directory -Force -Path $bd | Out-Null
$backup=Join-Path $bd 'app.js'
Copy-Item -LiteralPath $Target -Destination $backup -Force
[IO.File]::WriteAllText($StateFile,$backup,[Text.UTF8Encoding]::new($false))
Log "Backup created: $backup"

$new=@'
/* V32_BACKGROUND_ONLY_POLL_START
   Emergency refresh-only correction:
   - automatic browser poll still runs every DASHBOARD_POLL_SECONDS
   - fetches /api/overview directly
   - updates state/cache and safe leaf values only
   - NEVER calls refresh(false), hydrateSelectors(), renderAll(), or page render functions
   - manual Refresh and user actions remain unchanged
*/
async function v32BackgroundOnlyPoll(){
  try{
    if(!state.authenticated || !state.autoRefresh) return;
    if(state.__v32BackgroundPollInFlight) return;
    state.__v32BackgroundPollInFlight=true;

    const data=await api('/api/overview');
    state.overview=data;
    state.machines=data.machines||[];
    state.lastRefresh=new Date();

    try{$('#apiStatus')?.classList.add('ok')}catch(e){}
    try{if($('#statusText')) $('#statusText').textContent='Live'}catch(e){}

    try{
      if(window.v31ApplyStableLiveValues) window.v31ApplyStableLiveValues(data);
    }catch(e){console.error('[V32] stable leaf update failed',e)}
  }catch(e){
    console.error('[V32] background overview poll failed',e);
    try{$('#apiStatus')?.classList.remove('ok')}catch(_){}
    try{if($('#statusText')) $('#statusText').textContent='Offline'}catch(_){}
  }finally{
    state.__v32BackgroundPollInFlight=false;
  }
}
setInterval(v32BackgroundOnlyPoll,DASHBOARD_POLL_SECONDS*1000);

(function(){
  try{
    var s=document.getElementById('v32-background-only-style');
    if(!s){
      s=document.createElement('style');
      s.id='v32-background-only-style';
      s.textContent='#newDataBanner,#lastRefreshText{display:none!important}';
      document.head.appendChild(s);
    }
    var b=document.getElementById('newDataBanner');
    if(b){b.classList.add('hidden');b.style.display='none'}
    if(window.state) state.pendingUpdate=false;
  }catch(e){}
})();
/* V32_BACKGROUND_ONLY_POLL_END */
'@

try{
  $newText=$text.Replace($old,$new.Trim())
  $bytes=[IO.File]::ReadAllBytes($Target)
  $bom=($bytes.Length-ge3 -and $bytes[0]-eq0xEF -and $bytes[1]-eq0xBB -and $bytes[2]-eq0xBF)
  [IO.File]::WriteAllText($Target,$newText,[Text.UTF8Encoding]::new($bom))

  $node=Get-Command node -ErrorAction SilentlyContinue
  if($node){
    & $node.Source --check $Target
    if($LASTEXITCODE-ne0){throw 'node --check failed'}
    Log 'JavaScript syntax check: PASS'
  }else{
    Log 'Node.js not found; syntax check skipped.'
  }

  Log "Applied successfully. New SHA256: $(GetSha $Target)"
  Log 'No server restart required.'
  Log 'Do Ctrl+F5 once, then leave Machine 360 open and scroll/read for at least 30 seconds.'
  Log 'Background data polling continues, but automatic full-page redraw is now impossible from the main poll.'
  Log "Rollback: powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Rollback"
}catch{
  Copy-Item -LiteralPath $backup -Destination $Target -Force
  Log 'ERROR - backup restored automatically.'
  throw
}
