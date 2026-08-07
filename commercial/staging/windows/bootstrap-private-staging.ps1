param(
    [Parameter(Mandatory = $true)]
    [string]$TargetRepository,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9a-fA-F]{40}$')]
    [string]$ExpectedSourceCommit,

    [string]$SourceRepository = 'sagarkerhalkar/Systeam_Monitor_Tool',
    [string]$RepositoryRoot,
    [string]$ReportPath,
    [switch]$DryRun,
    [string]$PythonExe = 'python'
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if (-not $RepositoryRoot) {
    $RepositoryRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
}
$cli = Join-Path $RepositoryRoot 'commercial\tools\run_staging_lab.py'
if (-not (Test-Path -LiteralPath $cli -PathType Leaf)) {
    throw "Staging CLI is missing: $cli"
}
if (-not $ReportPath) {
    $ReportPath = Join-Path ([Environment]::GetFolderPath('CommonApplicationData')) 'SagarMonitorStaging\private-mirror-report.json'
}
New-Item -ItemType Directory -Path (Split-Path -Parent $ReportPath) -Force | Out-Null

$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $RepositoryRoot 'commercial'
    $arguments = @(
        $cli,
        'private-mirror-sync',
        '--repository-root', $RepositoryRoot,
        '--source-repository', $SourceRepository,
        '--target-repository', $TargetRepository,
        '--expected-source-commit', $ExpectedSourceCommit,
        '--output', $ReportPath
    )
    if ($DryRun) { $arguments += '--dry-run' }
    & $PythonExe @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Private staging mirror bootstrap failed with exit code $LASTEXITCODE."
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}

Write-Host "Private staging mirror verification report: $ReportPath"
Write-Host 'No production deployment was performed.'