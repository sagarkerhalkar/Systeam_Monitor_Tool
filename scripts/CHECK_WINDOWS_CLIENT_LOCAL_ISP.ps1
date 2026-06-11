$ErrorActionPreference = 'SilentlyContinue'
try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12 } catch {}
$Root = 'C:\ProgramData\CommercialMonitorPro'
$Cache = Join-Path $Root 'isp_state.json'
Write-Host "Checking internet ISP lookup from THIS client PC..." -ForegroundColor Cyan
$targets = @(
  @{ name='ipinfo'; url='https://ipinfo.io/json' },
  @{ name='ip-api'; url='http://ip-api.com/json/?fields=status,query,isp,org,as,country,city' },
  @{ name='ipify'; url='https://api.ipify.org?format=json' }
)
foreach($t in $targets){
  Write-Host "\n--- $($t.name) ---" -ForegroundColor Yellow
  try { Invoke-RestMethod -Uri $t.url -TimeoutSec 8 -Headers @{ 'User-Agent'='CommercialMonitorPro-Check/5.1' } | ConvertTo-Json -Depth 5 }
  catch { Write-Host "FAILED: $($_.Exception.Message)" -ForegroundColor Red }
}
Write-Host "\nClient cache file:" -ForegroundColor Yellow
if(Test-Path $Cache){ Get-Content $Cache -Raw } else { Write-Host "Not created yet: $Cache" -ForegroundColor Red }
Write-Host "\nClient task:" -ForegroundColor Yellow
Get-ScheduledTask -TaskName 'CommercialMonitorPro_Test2278' | Select-Object TaskName,State | Format-Table -AutoSize
Write-Host "\nRecent client errors:" -ForegroundColor Yellow
$Err = Join-Path $Root 'client_error.log'
if(Test-Path $Err){ Get-Content $Err -Tail 20 } else { Write-Host 'No client_error.log found.' }
