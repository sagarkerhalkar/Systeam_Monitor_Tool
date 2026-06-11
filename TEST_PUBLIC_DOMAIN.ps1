param([Parameter(Mandatory=$true)][string]$Domain,[int]$Port=2278)
Write-Host "Testing local server..." -ForegroundColor Cyan
try { Invoke-WebRequest "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 10 | Select-Object -ExpandProperty Content } catch { Write-Host "Local server failed: $($_.Exception.Message)" -ForegroundColor Red }
Write-Host "Testing domain DNS..." -ForegroundColor Cyan
try { Resolve-DnsName "$Domain.duckdns.org" | Format-Table -AutoSize } catch { Write-Host "DNS failed: $($_.Exception.Message)" -ForegroundColor Red }
Write-Host "Testing public URL from this server..." -ForegroundColor Cyan
try { Invoke-WebRequest "http://$Domain.duckdns.org:$Port/api/health" -UseBasicParsing -TimeoutSec 15 | Select-Object -ExpandProperty Content } catch { Write-Host "Public URL failed from here: $($_.Exception.Message)" -ForegroundColor Red; Write-Host "Test from mobile data also. If mobile fails, router port forward or ISP CGNAT is the issue." -ForegroundColor Yellow }
