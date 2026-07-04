param(
  [Parameter(Mandatory=$true)][string]$DuckDomain,
  [Parameter(Mandatory=$true)][string]$DuckToken,
  [int]$Port = 2278
)
$ErrorActionPreference = 'Stop'
function Assert-Admin {
  $id = [Security.Principal.WindowsIdentity]::GetCurrent()
  $p = New-Object Security.Principal.WindowsPrincipal($id)
  if (-not $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Run PowerShell as Administrator."
  }
}
Assert-Admin
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Updater = Join-Path $Root 'UPDATE_DUCKDNS_IP.ps1'
$TaskName = 'SagarMonitor_DuckDNS_Update'
try {
  New-NetFirewallRule -DisplayName "Sagar Monitor Public $Port" -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -ErrorAction SilentlyContinue | Out-Null
} catch {}
@"
param([string]`$DuckDomain='$DuckDomain',[string]`$DuckToken='$DuckToken')
`$ErrorActionPreference='SilentlyContinue'
`$url = "https://www.duckdns.org/update?domains=`$DuckDomain&token=`$DuckToken&ip="
try {
  `$r = Invoke-WebRequest -Uri `$url -UseBasicParsing -TimeoutSec 20
  `$line = "`$(Get-Date -Format s) domain=`$DuckDomain result=`$(`$r.Content)"
} catch {
  `$line = "`$(Get-Date -Format s) domain=`$DuckDomain error=`$(`$_.Exception.Message)"
}
Add-Content -Path "`$PSScriptRoot\duckdns_update.log" -Value `$line
"@ | Set-Content -Path $Updater -Encoding UTF8
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Updater`""
$triggerBoot = New-ScheduledTaskTrigger -AtStartup
$triggerEvery = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration ([TimeSpan]::MaxValue)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($triggerBoot,$triggerEvery) -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $TaskName
powershell -NoProfile -ExecutionPolicy Bypass -File $Updater
Write-Host "DuckDNS updater installed." -ForegroundColor Green
Write-Host "Your fixed free dashboard URL will be:" -ForegroundColor Cyan
Write-Host "http://$DuckDomain.duckdns.org:$Port" -ForegroundColor Yellow
Write-Host "Now set TP-Link ER8411 port forwarding: External TCP $Port -> 156.156.40.51:$Port" -ForegroundColor Cyan
Write-Host "Then test from mobile data, not same Wi-Fi." -ForegroundColor Cyan
