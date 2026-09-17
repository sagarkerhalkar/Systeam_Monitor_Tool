param(
    [string]$AppRoot = "D:\SagarSystemHealthMonitor",
    [switch]$CheckOnly,
    [switch]$Apply,
    [switch]$Rollback
)

$ErrorActionPreference = "Stop"
$Target = Join-Path $AppRoot "public\app.js"
$BackupRoot = Join-Path $AppRoot "SAFE_BACKUPS"
$StateFile = Join-Path $BackupRoot "UI_TIMER_SMOOTHNESS_V28_LAST_BACKUP.txt"
$Marker = "/* UI_TIMER_SMOOTHNESS_SAFE_FIX_V28_APPLIED */"

function Log([string]$m) { Write-Host "[V28 Smoothness] $m" }
function Hash([string]$p) { (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant() }
function Restore-Backup([string]$backup) {
    Copy-Item -LiteralPath $backup -Destination $Target -Force
    Log "RESTORED backup: $backup"
}

function Find-Section([string]$text,[string]$startToken,[string]$endToken) {
    $s = $text.IndexOf($startToken,[System.StringComparison]::Ordinal)
    if($s -lt 0) { throw "Missing section start: $startToken" }
    $e = $text.IndexOf($endToken,$s,[System.StringComparison]::Ordinal)
    if($e -lt 0) { throw "Missing section end: $endToken" }
    return @($s,$e)
}

function Count-InSection([string]$text,[string]$startToken,[string]$endToken,[string]$needle) {
    $p = Find-Section $text $startToken $endToken
    $section = $text.Substring($p[0],$p[1]-$p[0])
    return ([regex]::Matches($section,[regex]::Escape($needle))).Count
}

function Replace-InSection([string]$text,[string]$startToken,[string]$endToken,[string]$old,[string]$new) {
    $p = Find-Section $text $startToken $endToken
    $before = $text.Substring(0,$p[0])
    $section = $text.Substring($p[0],$p[1]-$p[0])
    $after = $text.Substring($p[1])
    $count = ([regex]::Matches($section,[regex]::Escape($old))).Count
    if($count -ne 1) { throw "Expected exactly 1 '$old' inside $startToken, found $count" }
    $section = $section.Replace($old,$new)
    return $before + $section + $after
}

if($Rollback) {
    if(-not (Test-Path -LiteralPath $StateFile)) { throw "Rollback state file not found: $StateFile" }
    $backup = (Get-Content -LiteralPath $StateFile -Raw).Trim()
    if(-not (Test-Path -LiteralPath $backup)) { throw "Recorded backup not found: $backup" }
    Restore-Backup $backup
    Log "Rollback complete. Current SHA256: $(Hash $Target)"
    exit 0
}

if(-not (Test-Path -LiteralPath $Target)) { throw "Target app.js not found: $Target" }
$text = [System.IO.File]::ReadAllText($Target)
Log "Target: $Target"
Log "Current SHA256: $(Hash $Target)"

$required = @(
    "/* SELECTED_CLIENT_LIVE_REFRESH_SAFE_FIX_V25_START",
    "/* UI_SEARCH_MOBILE_SMOOTHNESS_SAFE_FIX_V26_START",
    "/* MOBILE_FIRST_LAYOUT_SAFE_FIX_V27_START"
)
$missing = @()
foreach($r in $required){ if($text.IndexOf($r,[System.StringComparison]::Ordinal) -lt 0){ $missing += $r } }
if($missing.Count -gt 0){
    Log "SAFETY STOP: V25/V26/V27 baseline markers are missing. Nothing changed."
    $missing | ForEach-Object { Write-Host "  Missing: $_" }
    exit 2
}

if($text.IndexOf($Marker,[System.StringComparison]::Ordinal) -ge 0){
    Log "V28 smoothness fix is already installed."
    if($CheckOnly){ Log "CHECK ONLY PASSED (already installed)." }
    exit 0
}

$checks = @(
    @{Name='Branding Settings maintenance';Start='BRANDING_SETTINGS_FOUNDATION_ONLY_START';End='BRANDING_SETTINGS_FOUNDATION_ONLY_END';Old='}, 2500);';New='}, 15000);'},
    @{Name='Login layout maintenance';Start='LOGIN_APPROVED_LAYOUT_ANIMATED_ONLY_START';End='LOGIN_APPROVED_LAYOUT_ANIMATED_ONLY_END';Old='setInterval(apply,2000);';New="setInterval(function(){try{if(document.visibilityState==='visible'&&loginVisible())apply()}catch(e){}},15000);"},
    @{Name='Machine 360 maintenance';Start='MACHINE360_LOCK_V6_NO_SOURCE_CLEAN_START';End='MACHINE360_LOCK_V6_NO_SOURCE_CLEAN_END';Old='}, 1500);';New='}, 12000);'},
    @{Name='Client hostname lookup maintenance';Start='CLIENT_HOST_LOOKUP_V16_START';End='CLIENT_HOST_LOOKUP_V16_END';Old='},1800);';New='},12000);'},
    @{Name='USB/Software UI maintenance';Start='ASSETS_SOFTWARE_USB_UI_V17_START';End='ASSETS_SOFTWARE_USB_UI_V17_END';Old='},2000);';New='},12000);'}
)

try {
    foreach($c in $checks){
        $count = Count-InSection $text $c.Start $c.End $c.Old
        if($count -ne 1){ throw "Anchor check failed for $($c.Name): expected 1, found $count" }
        Log "Anchor OK: $($c.Name)"
    }
} catch {
    Log "SAFETY STOP: $($_.Exception.Message)"
    Log "Nothing was changed."
    exit 3
}

if($CheckOnly -or -not $Apply){
    Log "V25/V26/V27 baseline verified."
    Log "Five UI-only maintenance loops will be reduced from 1.5-2.5 sec to 12-15 sec fallback checks."
    Log "Existing page-switch, render, MutationObserver and user-event hooks remain unchanged."
    Log "The main 5-second monitoring refresh is NOT changed."
    Log "No server.py / DB / API / client / heartbeat / inventory-data changes are included."
    Log "CHECK ONLY PASSED. Nothing was changed."
    if(-not $Apply){ Log "Run again with -Apply when ready." }
    exit 0
}

New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDir = Join-Path $BackupRoot ("UI_TIMER_SMOOTHNESS_V28_" + $stamp)
New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
$backup = Join-Path $backupDir "app.js"
Copy-Item -LiteralPath $Target -Destination $backup -Force
[System.IO.File]::WriteAllText($StateFile,$backup,[System.Text.UTF8Encoding]::new($false))
Log "Backup created: $backup"

try {
    $newText = $text
    foreach($c in $checks){
        $newText = Replace-InSection $newText $c.Start $c.End $c.Old $c.New
        Log "Updated: $($c.Name)"
    }
    $newText = $newText.TrimEnd("`r","`n") + "`r`n`r`n" + $Marker + "`r`n"
    [System.IO.File]::WriteAllText($Target,$newText,[System.Text.UTF8Encoding]::new($true))

    $verify = [System.IO.File]::ReadAllText($Target)
    if(([regex]::Matches($verify,[regex]::Escape($Marker))).Count -ne 1){ throw "V28 marker verification failed." }

    $node = Get-Command node -ErrorAction SilentlyContinue
    if($node){
        & $node.Source --check $Target
        if($LASTEXITCODE -ne 0){ throw "node --check failed with exit code $LASTEXITCODE" }
        Log "JavaScript syntax check: PASS"
    } else {
        Log "Node.js not found; syntax check skipped. Backup/rollback remains available."
    }

    Log "Applied successfully. New SHA256: $(Hash $Target)"
    Log "No server restart was performed."
    Log "Test navigation, Machine 360, Network, Software, USB and mobile scrolling/search."
    Log "Rollback command: powershell -ExecutionPolicy Bypass -File `"$PSCommandPath`" -Rollback"
} catch {
    Log "ERROR: $($_.Exception.Message)"
    Log "Automatic rollback starting..."
    Restore-Backup $backup
    throw
}
