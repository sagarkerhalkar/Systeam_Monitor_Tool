param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('windows_server','windows_client_1','windows_client_2','restore_host')]
    [string]$Role,

    [Parameter(Mandatory = $true)]
    [string]$Site,

    [Parameter(Mandatory = $true)]
    [string]$Operator,

    [string]$WorkRoot = 'C:\ProgramData\SagarMonitorStaging',
    [string]$PythonExe = 'python'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run this staging-host preparation from an elevated PowerShell window.'
    }
}

Assert-Administrator

$cli = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\tools\run_staging_lab.py'))
$commercialRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
if (-not (Test-Path -LiteralPath $cli -PathType Leaf)) {
    throw "Staging CLI is missing: $cli"
}

New-Item -ItemType Directory -Path $WorkRoot -Force | Out-Null
$workRootResolved = (Resolve-Path -LiteralPath $WorkRoot).Path
$preflight = Join-Path $workRootResolved 'host-preflight.json'
$marker = Join-Path $workRootResolved 'host-marker.json'

if (Test-Path -LiteralPath $marker) {
    throw "A staging marker already exists. Verify or remove it intentionally before re-preparing this host: $marker"
}

$userSid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$aclArguments = @(
    $workRootResolved,
    '/inheritance:r',
    '/grant:r',
    '*S-1-5-18:(OI)(CI)F',
    '*S-1-5-32-544:(OI)(CI)F',
    "*${userSid}:(OI)(CI)M",
    '*S-1-5-20:(OI)(CI)RX'
)
& icacls.exe @aclArguments | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw 'Unable to apply protected ACLs to the staging work directory.'
}

$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = $commercialRoot
    & $PythonExe $cli preflight `
        --role $Role `
        --work-root $workRootResolved `
        --phase clean `
        --output $preflight `
        --marker $marker `
        --site $Site `
        --operator $Operator
    if ($LASTEXITCODE -ne 0) {
        throw "Staging preflight failed. Review: $preflight"
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}

& icacls.exe $preflight /inheritance:r /grant:r '*S-1-5-18:F' '*S-1-5-32-544:F' "*${userSid}:M" '*S-1-5-20:R' | Out-Null
& icacls.exe $marker /inheritance:r /grant:r '*S-1-5-18:F' '*S-1-5-32-544:F' "*${userSid}:M" '*S-1-5-20:R' | Out-Null

Write-Host "Staging host prepared."
Write-Host "Preflight: $preflight"
Write-Host "Marker:    $marker"
