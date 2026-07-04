$taskName = 'SagarSystemMonitor_Server_2278'
Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
Write-Host "Removed $taskName" -ForegroundColor Green
