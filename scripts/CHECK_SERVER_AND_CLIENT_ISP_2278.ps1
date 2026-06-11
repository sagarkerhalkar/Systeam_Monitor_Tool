param([string]$ServerUrl = 'http://127.0.0.1:2278')
$ErrorActionPreference = 'Stop'
Write-Host "Checking ISP data from server API: $ServerUrl/api/isp-check" -ForegroundColor Cyan
$r = Invoke-RestMethod -Uri ($ServerUrl.TrimEnd('/') + '/api/isp-check') -TimeoutSec 15
$r | ConvertTo-Json -Depth 8
Write-Host "\nMeaning:" -ForegroundColor Yellow
Write-Host "- server_isp = ISP detected by the monitoring server itself"
Write-Host "- machines_with_client_isp = how many clients have already sent ISP/public IP"
Write-Host "If machines_with_client_isp is 0, update/start the client on at least one machine."
