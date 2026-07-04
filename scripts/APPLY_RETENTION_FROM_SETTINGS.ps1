param(
  [string]$App = "D:\SagarSystemHealthMonitor",
  [int]$KeepDays = 0,
  [switch]$NoStop
)

$ErrorActionPreference = "Stop"
$Db = Join-Path $App "data\monitor.db"
$Settings = Join-Path $App "data\retention_settings.json"
$ReportDir = Join-Path $App "RETENTION_REPORTS"
New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null

if ($KeepDays -le 0) {
  if (Test-Path $Settings) {
    try {
      $j = Get-Content $Settings -Raw | ConvertFrom-Json
      $KeepDays = [int]$j.keep_days
    } catch { $KeepDays = 5 }
  } else { $KeepDays = 5 }
}
if ($KeepDays -lt 1) { $KeepDays = 5 }

Write-Host "Main 2278 retention: keep last $KeepDays days" -ForegroundColor Cyan

if (-not $NoStop) {
  Write-Host "Stopping main 2278 server process only..." -ForegroundColor Cyan
  Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match [regex]::Escape($App) -and $_.CommandLine -match "server\.py" -and $_.CommandLine -match "2278" } |
    ForEach-Object {
      Write-Host "Stopping PID $($_.ProcessId): $($_.CommandLine)"
      Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
  Start-Sleep -Seconds 2
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Py = @"
import sqlite3, json, datetime, os, sys
from pathlib import Path

db = Path(r"$Db")
keep_days = int("$KeepDays")
cutoff = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=keep_days)).isoformat()
report = {
    "ok": False,
    "db": str(db),
    "keep_days": keep_days,
    "cutoff_utc": cutoff,
    "deleted": {},
    "errors": [],
    "notes": []
}

def size(p):
    try: return Path(p).stat().st_size
    except Exception: return 0

report["db_size_before_bytes"] = size(db)
report["free_before_bytes"] = os.statvfs(str(db.parent)).f_bavail * os.statvfs(str(db.parent)).f_frsize if hasattr(os, "statvfs") else None

con = sqlite3.connect(str(db), timeout=60)
cur = con.cursor()

# Low-space friendly pragmas. This is not used for compaction.
try:
    cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    report["notes"].append("wal_checkpoint_before_ok")
except Exception as e:
    report["notes"].append("wal_checkpoint_before_failed:" + str(e))

try:
    cur.execute("PRAGMA journal_mode=OFF")
    report["notes"].append("journal_off")
except Exception as e:
    report["notes"].append("journal_off_failed:" + str(e))

def table_exists(t):
    return cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None

def delete_chunked(table, col, extra=""):
    if not table_exists(table):
        return 0
    total = 0
    while True:
        sql = f"DELETE FROM {table} WHERE rowid IN (SELECT rowid FROM {table} WHERE {col} < ? {extra} LIMIT 25000)"
        cur.execute(sql, (cutoff,))
        n = cur.rowcount if cur.rowcount is not None else 0
        con.commit()
        if n <= 0:
            break
        total += n
    return total

try:
    report["deleted"]["heartbeats"] = delete_chunked("heartbeats", "received_at")
    report["deleted"]["notifications"] = delete_chunked("notifications", "created_at")
    report["deleted"]["change_events"] = delete_chunked("change_events", "created_at")
    report["deleted"]["client_message_receipts"] = delete_chunked("client_message_receipts", "delivered_at")
    if table_exists("client_messages"):
        total = 0
        while True:
            cur.execute("DELETE FROM client_messages WHERE rowid IN (SELECT rowid FROM client_messages WHERE created_at < ? AND COALESCE(status,'') NOT IN ('pending','broadcast') LIMIT 25000)", (cutoff,))
            n = cur.rowcount if cur.rowcount is not None else 0
            con.commit()
            if n <= 0: break
            total += n
        report["deleted"]["client_messages"] = total
    try:
        cur.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        report["notes"].append("wal_checkpoint_after_ok")
    except Exception as e:
        report["notes"].append("wal_checkpoint_after_failed:" + str(e))
    report["ok"] = True
except Exception as e:
    report["errors"].append(str(e))
finally:
    try: con.close()
    except Exception: pass

report["db_size_after_bytes"] = size(db)
print(json.dumps(report, indent=2))
Path(r"$ReportDir\RETENTION_KEEP_DAYS_$Stamp.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
sys.exit(0 if report["ok"] else 1)
"@

$Tmp = Join-Path $env:TEMP "main2278_retention_from_settings_$Stamp.py"
[System.IO.File]::WriteAllText($Tmp, $Py, [System.Text.UTF8Encoding]::new($false))

try {
  python $Tmp
  if ($LASTEXITCODE -ne 0) { throw "Retention python failed" }
}
finally {
  if (-not $NoStop) {
    Write-Host "Restarting main 2278..." -ForegroundColor Cyan
    Start-Process powershell.exe -ArgumentList "-ExecutionPolicy Bypass -File `"$App\RUN_SERVER_2278.ps1`"" -WorkingDirectory $App
  }
}
