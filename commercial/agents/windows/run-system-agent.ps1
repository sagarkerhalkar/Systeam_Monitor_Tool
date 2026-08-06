$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root 'venv\Scripts\python.exe'
$Config = Join-Path $Root 'config\agent.json'
$Launcher = Join-Path $Root 'commercial\tools\run_edge_agent.py'
$LogDirectory = Join-Path $env:ProgramData 'SagarMonitorCommercialAgent\logs'
$LogFile = Join-Path $LogDirectory 'system-agent.log'

New-Item -ItemType Directory -Force -Path $LogDirectory | Out-Null
$env:PYTHONPATH = Join-Path $Root 'commercial'

while ($true) {
    try {
        & $Python $Launcher --config $Config service *>> $LogFile
        $ExitCode = $LASTEXITCODE
    }
    catch {
        "$(Get-Date -Format o) runner error: $($_.Exception.Message)" | Add-Content -LiteralPath $LogFile
        $ExitCode = 1
    }
    "$(Get-Date -Format o) agent exited with code $ExitCode; restarting in 30 seconds" | Add-Content -LiteralPath $LogFile
    Start-Sleep -Seconds 30
}
