param([string]$ServerUrl='http://127.0.0.1:2278')
Write-Host "Checking server history API..." -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri ($ServerUrl.TrimEnd('/') + '/api/history?days=30') -TimeoutSec 15
$r.daily | Format-Table -AutoSize
Write-Host "`nPer machine sample:" -ForegroundColor Cyan
$r.per_machine | Select-Object -First 20 date,hostname,download_gb,upload_gb,max_current_download_mbps,max_current_upload_mbps,cpu_max,ram_max,last_seen | Format-Table -AutoSize
