param(
  [string]$AppFolder = "D:\SagarSystemHealthMonitor",
  [string]$PublicUrl = "https://monitor.sagarkerhalkar.com"
)

$index = Join-Path $AppFolder "public\index.html"
if (!(Test-Path $index)) {
  Write-Host "ERROR: public\index.html not found in $AppFolder" -ForegroundColor Red
  exit 1
}

$text = Get-Content $index -Raw
$text = $text -replace 'http://156\.156\.40\.51:2278', $PublicUrl
$text = $text -replace 'V8\.4 single-port 2278\. These commands always install/update the latest Windows and Ubuntu client from this same server port\. Run after every client-code change\.', 'Domain deploy mode. These commands install/update clients through your permanent Cloudflare Tunnel URL. Use these after every client-code change.'
Set-Content $index $text -Encoding UTF8

$domainFile = Join-Path $AppFolder "DOMAIN_CLIENT_DEPLOY_COMMANDS.txt"
@"
SAGAR SYSTEM HEALTH MONITOR - DOMAIN CLIENT INSTALL COMMANDS

WINDOWS CLIENT INSTALL / UPDATE - run PowerShell as Administrator:

Remove-Item C:\Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 -Force -ErrorAction SilentlyContinue
Remove-Item C:\Temp\SagarSystemMonitor -Recurse -Force -ErrorAction SilentlyContinue

mkdir C:\Temp -Force

iwr "http://156.156.40.51:2278/scripts/BOOTSTRAP_WINDOWS_CLIENT_2278.ps1?restore=v84fixed" -OutFile C:\Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1

powershell -ExecutionPolicy Bypass -File C:\Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 -ServerUrl "http://156.156.40.51:2278" -FileServerUrl "http://156.156.40.51:2278" -IntervalSeconds 5

WINDOWS CLIENT TEST:

Copy-Item C:\ProgramData\SagarSystemMonitor\client_status.json C:\Temp\client_status_copy.json -Force -ErrorAction SilentlyContinue
type C:\Temp\client_status_copy.json

Copy-Item C:\ProgramData\SagarSystemMonitor\last_payload.json C:\Temp\last_payload_copy.json -Force -ErrorAction SilentlyContinue
type C:\Temp\last_payload_copy.json

or

type C:\ProgramData\SagarSystemMonitor\client_status.json
type C:\ProgramData\SagarSystemMonitor\server_messages.log
powershell -ExecutionPolicy Bypass -File C:\Temp\SagarSystemMonitor\DIAGNOSE_WINDOWS_CLIENT_2278.ps1 -ServerUrl $PublicUrl

UBUNTU CLIENT INSTALL / UPDATE:

curl -fsSL $PublicUrl/scripts/BOOTSTRAP_UBUNTU_CLIENT_2278.sh -o /tmp/bootstrap.sh
sudo SERVER_URL=$PublicUrl INTERVAL_SECONDS=5 bash /tmp/bootstrap.sh

UBUNTU CLIENT TEST:

sudo cat /var/lib/commercial-monitor-pro/client_status.json
sudo cat /var/lib/commercial-monitor-pro/server_messages.log
sudo systemctl status sagar-system-monitor-client.service
sudo journalctl -u sagar-system-monitor-client.service -n 80 --no-pager
curl $PublicUrl/api/health
"@ | Set-Content $domainFile -Encoding UTF8

Write-Host "Deploy page updated to $PublicUrl" -ForegroundColor Green
Write-Host "Restart monitor server, then press Ctrl+F5 in browser." -ForegroundColor Yellow
