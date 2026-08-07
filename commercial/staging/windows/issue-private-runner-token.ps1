param(
    [Parameter(Mandatory = $true)]
    [string]$TargetRepository,

    [Parameter(Mandatory = $true)]
    [string]$OutputPath,

    [string]$RepositoryRoot,
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

$previousPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = Join-Path $RepositoryRoot 'commercial'
    & $PythonExe $cli issue-runner-token `
        --repository $TargetRepository `
        --output $OutputPath `
        --repository-root $RepositoryRoot
    if ($LASTEXITCODE -ne 0) {
        throw "Runner token creation failed with exit code $LASTEXITCODE."
    }
}
finally {
    $env:PYTHONPATH = $previousPythonPath
}

Write-Host "Runner token written to protected file: $OutputPath"
Write-Host 'The token value was not printed. Delete the file immediately after runner registration.'