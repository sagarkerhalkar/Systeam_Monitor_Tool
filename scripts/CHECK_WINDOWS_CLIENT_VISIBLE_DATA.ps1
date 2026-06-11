param(
  [string]$ServerUrl = 'http://156.156.40.51:2278'
)
$Root='C:\ProgramData\SagarSystemMonitor'
$Client=Join-Path $Root 'client_windows.ps1'
if(!(Test-Path $Client)){ Write-Host "Client not installed at $Client" -ForegroundColor Red; exit 1 }
Write-Host "Running one client heartbeat and saving last_payload.json..." -ForegroundColor Cyan
powershell.exe -NoProfile -ExecutionPolicy Bypass -File $Client -ServerUrl $ServerUrl -Once
$PayloadPath=Join-Path $Root 'last_payload.json'
$StatusPath=Join-Path $Root 'client_status.json'
if(Test-Path $StatusPath){ Write-Host "`nSTATUS:" -ForegroundColor Cyan; Get-Content $StatusPath -Raw }
if(!(Test-Path $PayloadPath)){ Write-Host "No last_payload.json found." -ForegroundColor Red; exit 1 }
$p = Get-Content $PayloadPath -Raw | ConvertFrom-Json
Write-Host "`nVISIBLE DATA CHECK" -ForegroundColor Green
Write-Host "Hostname: $($p.hostname)"
Write-Host "ISP: $($p.network.public_internet.isp)"
Write-Host "Public IP: $($p.network.public_internet.public_ip)"
Write-Host "Current Download Mbps: $($p.network.current_download_mbps)"
Write-Host "Current Upload Mbps: $($p.network.current_upload_mbps)"
Write-Host "Today Download GB: $($p.network.today_download_gb)"
Write-Host "Today Upload GB: $($p.network.today_upload_gb)"
Write-Host "RAM Total GB: $($p.hardware.memory.total_gb)"
Write-Host "RAM Used GB: $($p.hardware.memory.used_gb)"
Write-Host "RAM Used %: $($p.hardware.memory.used_percent)"
Write-Host "USB/Peripheral Count: $(@($p.usb.devices).Count)"
@($p.usb.devices) | Select-Object -First 20 type,name,class,vid,pid,status | Format-Table -AutoSize
Write-Host "`nIf ISP is blank, that client cannot reach ipinfo/ip-api/ipify from internet, but server fallback can still show server ISP." -ForegroundColor Yellow
Write-Host "If current Mbps is 0, generate traffic on client, wait 30 seconds, then run again." -ForegroundColor Yellow
