param([string]$DuckDomain,[string]$DuckToken)
$ErrorActionPreference='SilentlyContinue'
if(-not $DuckDomain -or -not $DuckToken){ Write-Host "Usage: .\UPDATE_DUCKDNS_IP.ps1 -DuckDomain yourname -DuckToken token"; exit 1 }
$url = "https://www.duckdns.org/update?domains=$DuckDomain&token=$DuckToken&ip="
try {
  $r = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 20
  $line = "$(Get-Date -Format s) domain=$DuckDomain result=$($r.Content)"
  Write-Host $line
} catch {
  $line = "$(Get-Date -Format s) domain=$DuckDomain error=$($_.Exception.Message)"
  Write-Host $line -ForegroundColor Red
}
Add-Content -Path "$PSScriptRoot\duckdns_update.log" -Value $line
