param(
  [Parameter(Mandatory=$true)][string]$DuckDomain,
  [Parameter(Mandatory=$true)][string]$DuckToken,
  [int]$Port = 2278
)
$ErrorActionPreference='Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
powershell -ExecutionPolicy Bypass -File (Join-Path $Root 'INSTALL_SERVER_AUTOSTART_TASK.ps1') -Port $Port
powershell -ExecutionPolicy Bypass -File (Join-Path $Root 'INSTALL_DUCKDNS_FIXED_DOMAIN.ps1') -DuckDomain $DuckDomain -DuckToken $DuckToken -Port $Port
Write-Host "Done. Server autostart + DuckDNS autoupdate installed." -ForegroundColor Green
Write-Host "Do router port forwarding on TP-Link ER8411: WAN TCP $Port -> 156.156.40.51 TCP $Port" -ForegroundColor Yellow
