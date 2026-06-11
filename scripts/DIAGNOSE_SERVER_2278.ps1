param(
  [string]$ServerUrl = 'http://127.0.0.1:2278'
)
$ErrorActionPreference='Continue'
Write-Host "==== CommercialMonitorPro Server Diagnosis ====" -ForegroundColor Cyan
Write-Host "ServerUrl: $ServerUrl"
Write-Host "`n1) Health" -ForegroundColor Cyan
try { Invoke-RestMethod -Uri ($ServerUrl.TrimEnd('/') + '/api/health') -TimeoutSec 10 | ConvertTo-Json -Depth 5 } catch { Write-Host "FAILED: $($_.Exception.Message)" -ForegroundColor Red }
Write-Host "`n2) Machines count" -ForegroundColor Cyan
try { $m=Invoke-RestMethod -Uri ($ServerUrl.TrimEnd('/') + '/api/machines') -TimeoutSec 10; "machines=$($m.machines.Count)"; $m.machines | Select-Object hostname,primary_ip,public_ip,isp_name,updated_at | Format-Table -AutoSize } catch { Write-Host "FAILED: $($_.Exception.Message)" -ForegroundColor Red }
Write-Host "`n3) ISP check" -ForegroundColor Cyan
try { Invoke-RestMethod -Uri ($ServerUrl.TrimEnd('/') + '/api/isp-check') -TimeoutSec 20 | ConvertTo-Json -Depth 8 } catch { Write-Host "FAILED: $($_.Exception.Message)" -ForegroundColor Red }
Write-Host "`n4) Server log tail" -ForegroundColor Cyan
$log = Join-Path (Get-Location) 'data\server.log'
if(Test-Path $log){ Get-Content $log -Tail 80 } else { Write-Host "No data\server.log in current folder" -ForegroundColor Yellow }
