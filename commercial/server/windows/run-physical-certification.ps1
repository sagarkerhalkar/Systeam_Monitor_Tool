param(
    [string]$PythonExe = 'python',
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$CertificationArguments
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

$RepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..\..')).Path
$CommercialRoot = Join-Path $RepositoryRoot 'commercial'
$Entrypoint = Join-Path $CommercialRoot 'tools\run_physical_certification.py'
if (-not (Test-Path -LiteralPath $Entrypoint)) {
    throw "Physical certification entrypoint is missing: $Entrypoint"
}

$oldPythonPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = $CommercialRoot
    & $PythonExe $Entrypoint @CertificationArguments
    $exitCode = $LASTEXITCODE
} finally {
    $env:PYTHONPATH = $oldPythonPath
}
exit $exitCode
