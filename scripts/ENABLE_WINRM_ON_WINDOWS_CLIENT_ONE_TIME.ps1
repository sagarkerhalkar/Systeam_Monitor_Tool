param([Parameter(Mandatory=$true)][string]$ServerIp)
$ErrorActionPreference='Stop'
Enable-PSRemoting -Force
Set-NetFirewallRule -Name 'WINRM-HTTP-In-TCP' -RemoteAddress Any -ErrorAction SilentlyContinue
Set-Item WSMan:\localhost\Client\TrustedHosts -Value $ServerIp -Force
Write-Host "WinRM enabled. Now run update again from server." -ForegroundColor Green
