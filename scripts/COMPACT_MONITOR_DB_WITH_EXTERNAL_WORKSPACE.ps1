param(
  [string]$App = "D:\SagarSystemHealthMonitor",
  [Parameter(Mandatory=$true)][string]$Workspace,
  [switch]$NoOldDbBackup
)

$ErrorActionPreference = "Stop"
$Db = Join-Path $App "data\monitor.db"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Work = Join-Path $Workspace "SagarMonitorCompact_$Stamp"
New-Item -ItemType Directory -Path $Work -Force | Out-Null

$Compact = Join-Path $Work "monitor_compact.db"
$OldBackup = Join-Path $Work "monitor_old_before_compact.db"

Write-Host "Final DB will remain on server: $Db" -ForegroundColor Green
Write-Host "External/local workspace: $Work" -ForegroundColor Yellow

$drive = Get-PSDrive -Name ((Resolve-Path $Workspace).Path.Substring(0,1))
Write-Host "Workspace free GB: $([math]::Round($drive.Free/1GB,2))" -ForegroundColor Cyan

Write-Host "Stopping main 2278..." -ForegroundColor Cyan
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match [regex]::Escape($App) -and $_.CommandLine -match "server\.py" -and $_.CommandLine -match "2278" } |
  ForEach-Object {
    Write-Host "Stopping PID $($_.ProcessId): $($_.CommandLine)"
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
  }
Start-Sleep -Seconds 3

$Py = @"
import sqlite3, sys, json
from pathlib import Path
src=Path(r"$Db")
dst=Path(r"$Compact")
if dst.exists():
    dst.unlink()
con=sqlite3.connect(str(src), timeout=120)
cur=con.cursor()
cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
cur.execute("VACUUM INTO ?", (str(dst),))
con.close()
con=sqlite3.connect(str(dst))
ok=con.execute("PRAGMA integrity_check").fetchone()[0]
con.close()
print(json.dumps({"compact_db":str(dst), "integrity_check":ok, "size_bytes":dst.stat().st_size}, indent=2))
sys.exit(0 if ok=="ok" else 2)
"@
$PyFile = Join-Path $Work "compact_db.py"
[System.IO.File]::WriteAllText($PyFile, $Py, [System.Text.UTF8Encoding]::new($false))
python $PyFile
if ($LASTEXITCODE -ne 0) { throw "Compaction failed or integrity check failed. Old DB was not replaced." }

if (-not (Test-Path $Compact)) { throw "Compact DB missing." }

if (-not $NoOldDbBackup) {
  Write-Host "Moving old DB to workspace backup. This frees server D drive before copying compact DB back." -ForegroundColor Cyan
  Move-Item $Db $OldBackup -Force
} else {
  Write-Host "NoOldDbBackup selected. Deleting old DB after compact integrity check." -ForegroundColor Yellow
  Remove-Item $Db -Force
}

Copy-Item $Compact $Db -Force

Write-Host "Starting main 2278..." -ForegroundColor Cyan
Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass -File `"$App\RUN_SERVER_2278.ps1`"" -WorkingDirectory $App

Write-Host "COMPACT DONE. Final DB is back on server: $Db" -ForegroundColor Green
Write-Host "Workspace contains compact copy and old backup if enabled: $Work" -ForegroundColor Yellow
