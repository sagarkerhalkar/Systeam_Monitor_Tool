
param(
  [string]$RepoPath = "D:\SagarSystemHealthMonitor"
)

$ErrorActionPreference = "Continue"
$ReportDir = Join-Path $RepoPath "reports\final_v2"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
$Report = Join-Path $ReportDir "STARTUP_CHECK_REPORT.txt"
if (Test-Path $Report) { Remove-Item $Report -Force }

function Add-Line($t){ Add-Content -Path $Report -Value $t -Encoding UTF8 }

Add-Line "STARTUP CHECK REPORT"
Add-Line "Time: $(Get-Date)"
Add-Line "Repo: $RepoPath"
Add-Line ""

$required = @(
  "server.py",
  "RUN_SERVER_2278.ps1",
  "public\index.html",
  "public\app.js",
  "public\styles.css"
)

Add-Line "Required files:"
foreach($r in $required){
  $p = Join-Path $RepoPath $r
  Add-Line "$r : $(Test-Path $p)"
}

Add-Line ""
Add-Line "Python:"
$py = Get-Command python -ErrorAction SilentlyContinue
if(-not $py){ $py = Get-Command py -ErrorAction SilentlyContinue }
if($py){
  Add-Line "Found: $($py.Source)"
  $out = & $py.Source --version 2>&1
  Add-Line "Version: $out"
  if(Test-Path (Join-Path $RepoPath "server.py")){
    Add-Line "server.py syntax:"
    $out = & $py.Source -m py_compile (Join-Path $RepoPath "server.py") 2>&1
    Add-Line ($out | Out-String)
    Add-Line "Exit: $LASTEXITCODE"
  }
}else{
  Add-Line "Python not found"
}

Add-Line ""
Add-Line "Node / JS:"
$node = Get-Command node -ErrorAction SilentlyContinue
if($node){
  Add-Line "Found: $($node.Source)"
  $out = & node --version 2>&1
  Add-Line "Version: $out"
  if(Test-Path (Join-Path $RepoPath "public\app.js")){
    $out = & node --check (Join-Path $RepoPath "public\app.js") 2>&1
    Add-Line ($out | Out-String)
    Add-Line "Exit: $LASTEXITCODE"
  }
}else{
  Add-Line "Node not found. JS syntax check skipped."
}

Add-Line ""
Add-Line "Port 2278:"
try{
  $port = Get-NetTCPConnection -LocalPort 2278 -ErrorAction SilentlyContinue
  if($port){ Add-Line ($port | Format-Table -AutoSize | Out-String) } else { Add-Line "No listener on port 2278 currently." }
}catch{
  Add-Line "Could not check port: $($_.Exception.Message)"
}

Add-Line ""
Add-Line "DONE"
Write-Host "Startup check completed: $Report" -ForegroundColor Green
