$ErrorActionPreference = 'SilentlyContinue'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root 'venv\Scripts\pythonw.exe'
$Config = Join-Path $Root 'config\agent.json'
$Launcher = Join-Path $Root 'commercial\tools\run_edge_agent.py'
$env:PYTHONPATH = Join-Path $Root 'commercial'

if ((Test-Path -LiteralPath $Python) -and (Test-Path -LiteralPath $Config)) {
    & $Python $Launcher --config $Config notifier
}
