$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) { Write-Error "CRITICAL: You must run this script as an ADMINISTRATOR."; Start-Sleep 5; Exit }

$DestFolder = "C:\CustomMonitor"
if (-not (Test-Path $DestFolder)) { New-Item -ItemType Directory -Path $DestFolder -Force | Out-Null }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

# Fixed: Mirror codebase into local execution directories cleanly to avoid cross-drive crashes
Copy-Item -Path "$ScriptDir\client.ps1" -Destination "$DestFolder\" -Force
Copy-Item -Path "$ScriptDir\nssm.exe" -Destination "$DestFolder\" -Force

Unregister-ScheduledTask -TaskName "CustomNetworkMonitor" -Confirm:$false -ErrorAction SilentlyContinue | Out-Null
Unregister-ScheduledTask -TaskName "NextToppersMonitor" -Confirm:$false -ErrorAction SilentlyContinue | Out-Null

$ServiceName = "NextToppersAgent"
& "$DestFolder\nssm.exe" stop $ServiceName | Out-Null
& "$DestFolder\nssm.exe" remove $ServiceName confirm | Out-Null

& "$DestFolder\nssm.exe" install $ServiceName "powershell.exe" "-ExecutionPolicy Bypass -NoProfile -WindowStyle Hidden -File C:\CustomMonitor\client.ps1" | Out-Null
& "$DestFolder\nssm.exe" set $ServiceName AppDirectory "C:\CustomMonitor" | Out-Null
& "$DestFolder\nssm.exe" set $ServiceName Start SERVICE_AUTO_START | Out-Null

# Fixed: Inject an explicit startup delay configuration block directly into the service engine context
& "$DestFolder\nssm.exe" set $ServiceName AppDelay 60000 | Out-Null

& "$DestFolder\nssm.exe" start $ServiceName | Out-Null

Write-Host "✅ Installation Complete! The Indestructible Service is configured with a 60s boot delay protection rule." -ForegroundColor Green
Start-Sleep -Seconds 5