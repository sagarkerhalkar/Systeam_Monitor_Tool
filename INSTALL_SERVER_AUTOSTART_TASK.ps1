param(
  [int]$Port = 2278
)
$ErrorActionPreference='Stop'
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ServerPy = Join-Path $Root 'server.py'
if(!(Test-Path $ServerPy)){ throw "server.py not found in $Root" }
# Find Python launcher
$pyCmd = $null
foreach($cmd in @('py.exe','python.exe')){
  $found = Get-Command $cmd -ErrorAction SilentlyContinue
  if($found){ $pyCmd = $found.Source; break }
}
if(-not $pyCmd){ throw "Python not found. Install Python first." }
try {
  New-NetFirewallRule -DisplayName "SagarSystemMonitor $Port" -Direction Inbound -Protocol TCP -LocalPort $Port -Action Allow -ErrorAction SilentlyContinue | Out-Null
} catch {}
$taskName = 'SagarSystemMonitor_Server_2278'
if($pyCmd -like '*py.exe'){
  $args = "-3 `"$ServerPy`" --host 0.0.0.0 --port $Port"
} else {
  $args = "`"$ServerPy`" --host 0.0.0.0 --port $Port"
}
$action = New-ScheduledTaskAction -Execute $pyCmd -Argument $args -WorkingDirectory $Root
$trigger1 = New-ScheduledTaskTrigger -AtStartup
$trigger2 = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1)
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero)
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName $taskName -Action $action -Trigger @($trigger1,$trigger2) -Principal $principal -Settings $settings | Out-Null
Start-ScheduledTask -TaskName $taskName
Write-Host "Installed and started $taskName" -ForegroundColor Green
Write-Host "Dashboard: http://localhost:$Port" -ForegroundColor Cyan
Write-Host "Client scripts now download from: http://SERVER-IP:$Port/scripts/..." -ForegroundColor Cyan
