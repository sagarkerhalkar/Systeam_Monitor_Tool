param(
  [string]$App = "D:\SagarSystemHealthMonitor",
  [string]$BackupRoot = ""
)

$ErrorActionPreference = "Stop"
if (-not $BackupRoot) { $BackupRoot = Join-Path $App "INCREMENTAL_SOURCE_BACKUPS" }
New-Item -ItemType Directory -Path $BackupRoot -Force | Out-Null

$StateFile = Join-Path $BackupRoot "manifest_latest.json"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Out = Join-Path $BackupRoot "INC_$Stamp"
New-Item -ItemType Directory -Path $Out -Force | Out-Null

$patterns = @("*.py","*.ps1","*.bat","*.cmd","*.html","*.css","*.js","*.json","*.md","*.txt","*.sh","*.yml","*.yaml")
$excludeDirs = @("\data\", "\__pycache__\", "\INCREMENTAL_SOURCE_BACKUPS\", "\RETENTION_REPORTS\", "\BACKUP_", "\dist\")
$old = @{}
if (Test-Path $StateFile) {
  try {
    (Get-Content $StateFile -Raw | ConvertFrom-Json).psobject.Properties | ForEach-Object { $old[$_.Name] = $_.Value }
  } catch {}
}
$new = @{}
$changed = 0
$scanned = 0

Get-ChildItem $App -Recurse -File -Include $patterns -ErrorAction SilentlyContinue | ForEach-Object {
  $full = $_.FullName
  foreach ($ex in $excludeDirs) {
    if ($full -like "*$ex*") { return }
  }
  $rel = $full.Substring($App.Length).TrimStart("\")
  $scanned++
  $hash = (Get-FileHash $full -Algorithm SHA256).Hash
  $new[$rel] = $hash
  if (-not $old.ContainsKey($rel) -or $old[$rel] -ne $hash) {
    $dest = Join-Path $Out $rel
    New-Item -ItemType Directory -Path (Split-Path $dest -Parent) -Force | Out-Null
    Copy-Item $full $dest -Force
    $changed++
  }
}

($new | ConvertTo-Json -Depth 5) | Set-Content $StateFile -Encoding UTF8

$report = [ordered]@{
  ok = $true
  app = $App
  backup = $Out
  scanned = $scanned
  changed_copied = $changed
  created_at = (Get-Date).ToString("o")
}
$report | ConvertTo-Json -Depth 5 | Tee-Object -FilePath (Join-Path $Out "incremental_backup_report.json")
