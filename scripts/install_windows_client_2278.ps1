param(
  [Parameter(Mandatory=$true)][string]$ServerUrl,
  [int]$IntervalSeconds = 5,
  [switch]$SkipImmediateTest
)
$ErrorActionPreference = 'Stop'
$Root = 'C:\ProgramData\SagarSystemMonitor'
New-Item -ItemType Directory -Force -Path $Root | Out-Null
# Clean older test tasks/services so only this fixed client keeps running.
@('SagarSystemMonitor_Client_2278','SagarSystemMonitor_Test2278','NextToppersAgentTest2278','CustomMonitor_Test2278') | ForEach-Object { Unregister-ScheduledTask -TaskName $_ -Confirm:$false -ErrorAction SilentlyContinue }

Write-Host "Checking server: $ServerUrl/api/health" -ForegroundColor Cyan
try {
  $health = Invoke-RestMethod -Uri ($ServerUrl.TrimEnd('/') + '/api/health') -TimeoutSec 10
  Write-Host "Server reachable: OK" -ForegroundColor Green
} catch {
  Write-Host "Server NOT reachable from this client." -ForegroundColor Red
  Write-Host $_.Exception.Message -ForegroundColor Yellow
  Write-Host "Fix server/firewall/IP first, then run installer again." -ForegroundColor Yellow
  throw
}

Copy-Item -Force -Path (Join-Path $PSScriptRoot 'client_windows.ps1') -Destination (Join-Path $Root 'client_windows.ps1')

if(-not $SkipImmediateTest){
  Write-Host "Sending one test heartbeat now. This can take 20-90 seconds first time because software/USB inventory is collected." -ForegroundColor Cyan
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$Root\client_windows.ps1" -ServerUrl "$ServerUrl" -IntervalSeconds $IntervalSeconds -Once
  if(Test-Path "$Root\client_status.json"){
    Write-Host "Client status:" -ForegroundColor Cyan
    Get-Content "$Root\client_status.json" -Raw
  }
}

$taskName = 'SagarSystemMonitor_Client_2278'
$arg = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Root\client_windows.ps1`" -ServerUrl `"$ServerUrl`" -IntervalSeconds $IntervalSeconds"
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $arg
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Host "Installed and started $taskName" -ForegroundColor Green
Write-Host "Sending to $ServerUrl" -ForegroundColor Cyan
Write-Host "Check log: C:\ProgramData\SagarSystemMonitor\client_error.log" -ForegroundColor Cyan
