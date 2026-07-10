
param(
  [string]$Url = "http://localhost:2278",
  [string]$RepoPath = "D:\SagarSystemHealthMonitor"
)

$ErrorActionPreference = "Continue"
$ReportDir = Join-Path $RepoPath "reports\final_v2"
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null
$Report = Join-Path $ReportDir "RUNNING_CHECK_REPORT.txt"
if (Test-Path $Report) { Remove-Item $Report -Force }

function Add-Line($t){ Add-Content -Path $Report -Value $t -Encoding UTF8 }

Add-Line "RUNNING CHECK REPORT"
Add-Line "Time: $(Get-Date)"
Add-Line "URL: $Url"
Add-Line ""

try{
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  $resp = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
  $sw.Stop()
  Add-Line "HTTP status: $($resp.StatusCode)"
  Add-Line "Response ms: $($sw.ElapsedMilliseconds)"
  Add-Line "Content length: $($resp.Content.Length)"
  if($resp.Content -match "System|Monitor|Dashboard|Login"){
    Add-Line "Basic content keyword check: OK"
  } else {
    Add-Line "Basic content keyword check: WARNING"
  }
}catch{
  Add-Line "HTTP check failed: $($_.Exception.Message)"
}

Add-Line ""
Add-Line "Local port 2278:"
try{
  $port = Get-NetTCPConnection -LocalPort 2278 -ErrorAction SilentlyContinue
  if($port){ Add-Line ($port | Format-Table -AutoSize | Out-String) } else { Add-Line "No listener on port 2278 currently." }
}catch{
  Add-Line "Could not check port: $($_.Exception.Message)"
}

Add-Line "DONE"
Write-Host "Running check completed: $Report" -ForegroundColor Green
