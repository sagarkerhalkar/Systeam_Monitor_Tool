param(
  [string]$AppFolder = "D:\SagarSystemHealthMonitor",
  [string]$PublicUrl = "https://monitor.sagarkerhalkar.com"
)
$ErrorActionPreference='Stop'
$src = Join-Path $PSScriptRoot 'scripts'
$dst = Join-Path $AppFolder 'scripts'
if(!(Test-Path $AppFolder)){ throw "App folder not found: $AppFolder" }
if(!(Test-Path $dst)){ New-Item -ItemType Directory -Force -Path $dst | Out-Null }
$files = @(
 'client_windows.ps1',
 'install_windows_client_2278.ps1',
 'BOOTSTRAP_WINDOWS_CLIENT_2278.ps1',
 'DIAGNOSE_WINDOWS_CLIENT_2278.ps1',
 'CHECK_WINDOWS_CLIENT_VISIBLE_DATA.ps1',
 'CHECK_WINDOWS_USB_MESSAGES.ps1'
)
foreach($f in $files){ Copy-Item -Force (Join-Path $src $f) (Join-Path $dst $f) }
# Update visible deploy commands in common UI/static files without touching server/client logic.
Get-ChildItem -Path $AppFolder -Recurse -Include *.html,*.js,*.txt,*.ps1,*.md -ErrorAction SilentlyContinue | ForEach-Object {
  try {
    $p=$_.FullName
    $t=Get-Content $p -Raw -ErrorAction Stop
    $t2=$t -replace 'http://156\.156\.40\.51:2278', $PublicUrl
    $t2=$t2 -replace 'https://monitor.sagarkerhalkar.com', $PublicUrl
    if($t2 -ne $t){ Set-Content -Path $p -Value $t2 -Encoding UTF8 }
  } catch {}
}
Write-Host "Restored V8.4 Windows client scripts with ONLY Int64 counter fix." -ForegroundColor Green
Write-Host "AppFolder: $AppFolder" -ForegroundColor Cyan
Write-Host "Public URL in deploy text: $PublicUrl" -ForegroundColor Cyan
Write-Host "Now restart server or reboot, then run bootstrap with ?restore=v84fixed" -ForegroundColor Yellow

