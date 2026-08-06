param(
    [string]$InstallRoot = 'C:\actions-runner-sagar-staging',
    [string]$WorkRoot = 'C:\ProgramData\SagarMonitorStaging',
    [string]$RemovalTokenFile
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw 'Run runner removal from an elevated PowerShell window.'
}

if (-not (Test-Path -LiteralPath $InstallRoot -PathType Container)) {
    Write-Host "Runner directory is already absent: $InstallRoot"
    exit 0
}

Push-Location $InstallRoot
try {
    $svc = Join-Path $InstallRoot 'svc.cmd'
    if (Test-Path -LiteralPath $svc -PathType Leaf) {
        & $svc stop
        & $svc uninstall
    }

    if ($RemovalTokenFile) {
        if (-not (Test-Path -LiteralPath $RemovalTokenFile -PathType Leaf)) {
            throw "Removal token file is missing: $RemovalTokenFile"
        }
        $token = (Get-Content -LiteralPath $RemovalTokenFile -Raw -Encoding UTF8).Trim()
        try {
            & (Join-Path $InstallRoot 'config.cmd') remove --token $token
        }
        finally {
            $token = $null
            Remove-Item -LiteralPath $RemovalTokenFile -Force -ErrorAction SilentlyContinue
        }
    }
}
finally {
    Pop-Location
}

Remove-Item -LiteralPath $InstallRoot -Recurse -Force
Remove-Item -LiteralPath (Join-Path $WorkRoot 'runner-receipt.json') -Force -ErrorAction SilentlyContinue
Write-Host 'Staging runner removed. Host marker and physical evidence were preserved.'
