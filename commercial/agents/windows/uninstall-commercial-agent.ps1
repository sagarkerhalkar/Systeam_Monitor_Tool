[CmdletBinding()]
param(
    [string]$InstallRoot = "$env:ProgramFiles\SagarMonitorCommercialAgent",
    [string]$StateRoot = "$env:ProgramData\SagarMonitorCommercialAgent\state",
    [switch]$RemoveState
)

$ErrorActionPreference = 'Stop'
$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run this uninstaller from an elevated PowerShell window.'
}

foreach ($name in @('SagarMonitorCommercialAgent', 'SagarMonitorCommercialNotifier')) {
    Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    Unregister-ScheduledTask -TaskName $name -Confirm:$false -ErrorAction SilentlyContinue
}

if (Test-Path -LiteralPath $InstallRoot) {
    Remove-Item -LiteralPath $InstallRoot -Recurse -Force
}
$rollback = "${InstallRoot}.rollback"
if (Test-Path -LiteralPath $rollback) {
    Remove-Item -LiteralPath $rollback -Recurse -Force
}
if ($RemoveState -and (Test-Path -LiteralPath $StateRoot)) {
    Remove-Item -LiteralPath $StateRoot -Recurse -Force
}

Write-Host 'Sagar Monitor commercial pilot agent removed.'
if (-not $RemoveState) {
    Write-Host "State and permanent identity were preserved at: $StateRoot"
}
