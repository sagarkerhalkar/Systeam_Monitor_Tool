param([string]$ServerUrl='http://127.0.0.1:2278')
$Root='C:\ProgramData\SagarSystemMonitor'
Write-Host '=== Sagar Monitor Windows USB + Message Check ===' -ForegroundColor Cyan
Write-Host "Server: $ServerUrl"
Write-Host ''
if(Test-Path "$Root\client_status.json"){
  Write-Host 'Client status:' -ForegroundColor Yellow
  Get-Content "$Root\client_status.json" -Raw
} else { Write-Host 'No client_status.json found yet.' -ForegroundColor Red }
Write-Host ''
if(Test-Path "$Root\last_payload.json"){
  $p = Get-Content "$Root\last_payload.json" -Raw | ConvertFrom-Json
  $usb = @($p.usb.devices)
  Write-Host "USB/peripheral count in last payload: $($usb.Count)" -ForegroundColor Green
  $usb | Select-Object -First 50 type,name,class,vid,pid,device_id,source | Format-Table -AutoSize
} else { Write-Host 'No last_payload.json found yet.' -ForegroundColor Red }
Write-Host ''
Write-Host 'Message log:' -ForegroundColor Yellow
if(Test-Path "$Root\server_messages.log"){ Get-Content "$Root\server_messages.log" -Tail 20 } else { Write-Host 'No server_messages.log yet.' }
Write-Host ''
Write-Host 'Scheduled task:' -ForegroundColor Yellow
Get-ScheduledTask -TaskName 'SagarSystemMonitor_Client_2278' -ErrorAction SilentlyContinue | Format-List TaskName,State
