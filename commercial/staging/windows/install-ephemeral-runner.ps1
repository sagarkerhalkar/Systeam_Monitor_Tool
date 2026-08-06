param(
    [Parameter(Mandatory = $true)]
    [string]$Repository,

    [Parameter(Mandatory = $true)]
    [string]$RegistrationTokenFile,

    [Parameter(Mandatory = $true)]
    [string]$RunnerArchivePath,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{64}$')]
    [string]$RunnerArchiveSha256,

    [string]$RunnerName = "$($env:COMPUTERNAME)-sagar-staging",
    [string]$InstallRoot = 'C:\actions-runner-sagar-staging',
    [string]$WorkRoot = 'C:\ProgramData\SagarMonitorStaging',
    [string]$PythonExe = 'python',
    [string]$GitHubCli = 'gh'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Assert-Administrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw 'Run runner installation from an elevated PowerShell window.'
    }
}

Assert-Administrator

$cli = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\tools\run_staging_lab.py'))
$commercialRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$marker = Join-Path $WorkRoot 'host-marker.json'
$receipt = Join-Path $WorkRoot 'runner-receipt.json'

foreach ($required in @($cli, $marker, $RegistrationTokenFile, $RunnerArchivePath)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Required file is missing: $required"
    }
}
if (Test-Path -LiteralPath $InstallRoot) {
    throw "Runner installation directory already exists: $InstallRoot"
}

$previousPythonPath = $env:PYTHONPATH
$token = $null
try {
    $env:PYTHONPATH = $commercialRoot

    & $PythonExe $cli repository-check --repository $Repository --gh-executable $GitHubCli
    if ($LASTEXITCODE -ne 0) {
        throw 'Runner registration is blocked until the repository is private and GitHub CLI authentication is valid.'
    }

    & $PythonExe $cli verify-marker --marker $marker
    if ($LASTEXITCODE -ne 0) {
        throw 'Staging host marker verification failed.'
    }

    $actualHash = (Get-FileHash -LiteralPath $RunnerArchivePath -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($actualHash -ne $RunnerArchiveSha256.ToLowerInvariant()) {
        throw "Runner archive SHA-256 mismatch. Expected $RunnerArchiveSha256 but got $actualHash"
    }

    $token = (Get-Content -LiteralPath $RegistrationTokenFile -Raw -Encoding UTF8).Trim()
    if ([string]::IsNullOrWhiteSpace($token)) {
        throw 'Runner registration token file is empty.'
    }

    New-Item -ItemType Directory -Path $InstallRoot -Force | Out-Null
    Expand-Archive -LiteralPath $RunnerArchivePath -DestinationPath $InstallRoot -Force

    $config = Join-Path $InstallRoot 'config.cmd'
    if (-not (Test-Path -LiteralPath $config -PathType Leaf)) {
        throw 'The supplied archive is not a Windows GitHub Actions runner package.'
    }

    Push-Location $InstallRoot
    try {
        & $config `
            --unattended `
            --url "https://github.com/$Repository" `
            --token $token `
            --name $RunnerName `
            --labels 'sagar-monitor-staging,commercial-certification' `
            --work '_work' `
            --replace `
            --ephemeral `
            --runasservice
        if ($LASTEXITCODE -ne 0) {
            throw "GitHub runner configuration failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        Pop-Location
    }

    & $PythonExe $cli write-runner-receipt `
        --receipt $receipt `
        --marker $marker `
        --repository $Repository `
        --platform windows `
        --runner-name $RunnerName
    if ($LASTEXITCODE -ne 0) {
        throw 'Unable to write the staging runner receipt.'
    }

    & $PythonExe $cli verify-runner-receipt `
        --receipt $receipt `
        --marker $marker `
        --repository $Repository `
        --platform windows
    if ($LASTEXITCODE -ne 0) {
        throw 'Staging runner receipt verification failed.'
    }
}
finally {
    $token = $null
    if (Test-Path -LiteralPath $RegistrationTokenFile) {
        Remove-Item -LiteralPath $RegistrationTokenFile -Force
    }
    $env:PYTHONPATH = $previousPythonPath
}

Write-Host "Ephemeral staging runner installed: $RunnerName"
Write-Host "Receipt: $receipt"
Write-Host 'The runner will unregister after one workflow job. Reinstall it before another physical-certification job.'
