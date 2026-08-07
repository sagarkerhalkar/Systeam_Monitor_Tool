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

$resolvedToken = (Resolve-Path -LiteralPath $OutputPath).Path
$currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
& icacls.exe $resolvedToken /inheritance:r /grant:r "${currentIdentity}:(R,W)" 'SYSTEM:(F)' 'BUILTIN\Administrators:(F)' | Out-Null
if ($LASTEXITCODE -ne 0) {
    Remove-Item -LiteralPath $resolvedToken -Force -ErrorAction SilentlyContinue
    throw 'Unable to apply a restricted ACL to the runner token file; the token file was deleted.'
}

Write-Host "Runner token written to protected file: $resolvedToken"
Write-Host 'The token value was not printed. Delete the file immediately after runner registration.'