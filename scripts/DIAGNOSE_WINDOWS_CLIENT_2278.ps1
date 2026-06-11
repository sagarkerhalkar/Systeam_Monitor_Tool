param(
  [Parameter(Mandatory=$true)][string]$ServerUrl
)
$ErrorActionPreference='Continue'
$Root='C:\ProgramData\SagarSystemMonitor'
Write-Host "==== SagarSystemMonitor Windows Client Diagnosis ====" -ForegroundColor Cyan
Write-Host "ServerUrl: $ServerUrl"
Write-Host "Computer: $env:COMPUTERNAME"
Write-Host "Time: $(Get-Date)"

Write-Host "`n1) Check server health from client" -ForegroundColor Cyan
try { Invoke-RestMethod -Uri ($ServerUrl.TrimEnd('/') + '/api/health') -TimeoutSec 10 | ConvertTo-Json -Depth 5 } catch { Write-Host "FAILED: $($_.Exception.Message)" -ForegroundColor Red }

Write-Host "`n2) Check TCP port" -ForegroundColor Cyan
try {
  $u=[uri]$ServerUrl
  Test-NetConnection -ComputerName $u.Host -Port $u.Port
} catch { Write-Host "FAILED: $($_.Exception.Message)" -ForegroundColor Red }

Write-Host "`n3) Check scheduled task" -ForegroundColor Cyan
Get-ScheduledTask -TaskName 'SagarSystemMonitor_Test2278' -ErrorAction SilentlyContinue | Format-List TaskName,State,TaskPath
Get-ScheduledTaskInfo -TaskName 'SagarSystemMonitor_Test2278' -ErrorAction SilentlyContinue | Format-List LastRunTime,LastTaskResult,NextRunTime,NumberOfMissedRuns

Write-Host "`n4) Check local files" -ForegroundColor Cyan
Get-ChildItem $Root -ErrorAction SilentlyContinue | Select-Object Name,Length,LastWriteTime | Format-Table -AutoSize

Write-Host "`n5) Last client status" -ForegroundColor Cyan
if(Test-Path "$Root\client_status.json"){ Get-Content "$Root\client_status.json" -Raw } else { Write-Host "No client_status.json yet" -ForegroundColor Yellow }

Write-Host "`n6) Last client errors/log" -ForegroundColor Cyan
if(Test-Path "$Root\client_error.log"){ Get-Content "$Root\client_error.log" -Tail 40 } else { Write-Host "No client_error.log yet" -ForegroundColor Yellow }

Write-Host "`n7) Run one foreground heartbeat now" -ForegroundColor Cyan
if(Test-Path "$Root\client_windows.ps1"){
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$Root\client_windows.ps1" -ServerUrl "$ServerUrl" -Once
  Write-Host "After foreground run, status:" -ForegroundColor Cyan
  if(Test-Path "$Root\client_status.json"){ Get-Content "$Root\client_status.json" -Raw }
} else {
  Write-Host "client_windows.ps1 not found in $Root. Reinstall client." -ForegroundColor Red
}
