$ErrorActionPreference = "Stop"
$App = Split-Path -Parent $MyInvocation.MyCommand.Path
$TaskName = "SagarSystemMonitor_Server_2278"
$Watchdog = Join-Path $App "SERVER_WATCHDOG_2278.ps1"
if (-not (Test-Path (Join-Path $App "server.py"))) { throw "server.py not found in $App" }
if (-not (Test-Path (Join-Path $App "universal_server.py"))) { throw "universal_server.py not found in $App" }
if (-not (Test-Path $Watchdog)) { throw "SERVER_WATCHDOG_2278.ps1 not found in $App" }
Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "SagarSystemHealthMonitor.*(server|universal_server)\.py" -or $_.CommandLine -match "SERVER_WATCHDOG_2278\.ps1" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
$Action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$Watchdog`"" -WorkingDirectory $App
$Trigger = New-ScheduledTaskTrigger -AtStartup
$Principal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$Settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Description "Universal watchdog for Sagar System Monitor on TCP 2278" -Force | Out-Null
New-NetFirewallRule -DisplayName "Sagar System Monitor 2278" -Direction Inbound -Protocol TCP -LocalPort 2278 -Action Allow -Profile Any -ErrorAction SilentlyContinue | Out-Null
Start-ScheduledTask -TaskName $TaskName
Start-Sleep 10
Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName,State
Get-NetTCPConnection -LocalPort 2278 -State Listen -ErrorAction SilentlyContinue | Select-Object LocalAddress,LocalPort,State,OwningProcess
