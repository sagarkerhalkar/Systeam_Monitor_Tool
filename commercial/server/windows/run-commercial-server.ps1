param()

$ErrorActionPreference = 'Stop'
$InstallRoot = Join-Path $env:ProgramFiles 'SagarMonitorCommercialServer'
$ConfigRoot = Join-Path $env:ProgramData 'SagarMonitorCommercialServer\config'
$PointerFile = Join-Path $InstallRoot 'current.txt'
$ConfigFile = Join-Path $ConfigRoot 'server.json'

if (-not (Test-Path -LiteralPath $PointerFile)) {
    throw "Commercial server version pointer is missing: $PointerFile"
}
$VersionName = (Get-Content -LiteralPath $PointerFile -Raw -Encoding UTF8).Trim([char]0xFEFF).Trim()
if ($VersionName -notmatch '^[A-Za-z0-9._-]+$') {
    throw 'Commercial server version pointer is invalid.'
}
$VersionRoot = Join-Path (Join-Path $InstallRoot 'versions') $VersionName
$Python = Join-Path $VersionRoot 'venv\Scripts\python.exe'
$Entrypoint = Join-Path $VersionRoot 'commercial\tools\run_commercial_server.py'
if (-not (Test-Path -LiteralPath $Python)) { throw "Python runtime is missing: $Python" }
if (-not (Test-Path -LiteralPath $Entrypoint)) { throw "Server entrypoint is missing: $Entrypoint" }
if (-not (Test-Path -LiteralPath $ConfigFile)) { throw "Server configuration is missing: $ConfigFile" }

$env:PYTHONPATH = Join-Path $VersionRoot 'commercial'
& $Python $Entrypoint --config $ConfigFile serve
exit $LASTEXITCODE
