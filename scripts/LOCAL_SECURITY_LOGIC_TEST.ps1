param([string]$RepoPath = "D:\SagarSystemHealthMonitor")
$ErrorActionPreference = "Stop"
cd $RepoPath
python -m py_compile server.py
if (Get-Command node -ErrorAction SilentlyContinue) { node --check public\app.js }
python tests\security_logic_static_test.py
Write-Host "LOCAL SECURITY LOGIC TEST OK" -ForegroundColor Green
