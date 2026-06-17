$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Write-Host "Sagar Kerhalkar System Monitor Tool starting on port 2278" -ForegroundColor Cyan
Write-Host "Dashboard: http://localhost:2278" -ForegroundColor Green
try { New-NetFirewallRule -DisplayName "Sagar System Monitor 2278" -Direction Inbound -Protocol TCP -LocalPort 2278 -Action Allow -ErrorAction SilentlyContinue | Out-Null } catch {}
$py = (Get-Command py -ErrorAction SilentlyContinue)
if ($py) { py -3 .\server.py --host 0.0.0.0 --port 2278 }
else { python .\server.py --host 0.0.0.0 --port 2278 }
