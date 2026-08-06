param(
    [switch]$RemoveData
)

$ErrorActionPreference = 'Stop'
$TaskName = 'SagarMonitorCommercialServer'
$InstallRoot = Join-Path $env:ProgramFiles 'SagarMonitorCommercialServer'
$DataRoot = Join-Path $env:ProgramData 'SagarMonitorCommercialServer'

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this uninstaller from an elevated PowerShell window.'
}

Stop-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $InstallRoot -Recurse -Force -ErrorAction SilentlyContinue

if ($RemoveData) {
    Remove-Item -LiteralPath $DataRoot -Recurse -Force -ErrorAction SilentlyContinue
    Write-Host 'Commercial server application, configuration, database, TLS files and backups were removed.'
} else {
    Write-Host "Commercial server application removed. Data is preserved at: $DataRoot"
}
