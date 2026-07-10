
param(
  [string]$RepoPath = "D:\SagarSystemHealthMonitor"
)

$ErrorActionPreference = "Stop"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Quarantine = Join-Path $RepoPath "_cleanup_quarantine\$Stamp"
$ReportDir = Join-Path $RepoPath "reports\final_v2"
$Manifest = Join-Path $ReportDir "MANUAL_CLEANUP_QUARANTINE_$Stamp.txt"

New-Item -ItemType Directory -Force -Path $Quarantine | Out-Null
New-Item -ItemType Directory -Force -Path $ReportDir | Out-Null

"SAFE CLEANUP QUARANTINE MANIFEST" | Set-Content $Manifest -Encoding UTF8
"Time: $(Get-Date)" | Add-Content $Manifest -Encoding UTF8
"Quarantine: $Quarantine" | Add-Content $Manifest -Encoding UTF8
"" | Add-Content $Manifest -Encoding UTF8

$patterns = @(
  "*.bak_*",
  "*.bak",
  "*.tmp",
  "*.old",
  "*.pyc"
)

foreach($pat in $patterns){
  Get-ChildItem -Path $RepoPath -Recurse -File -Filter $pat -ErrorAction SilentlyContinue |
    Where-Object {
      $_.FullName -notmatch "\\.git\\" -and
      $_.FullName -notmatch "\\data\\" -and
      $_.FullName -notmatch "_cleanup_quarantine"
    } |
    ForEach-Object {
      $rel = Resolve-Path -Path $_.FullName -Relative
      $dest = Join-Path $Quarantine ($rel -replace "^[.\\\/]+","")
      New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
      Move-Item $_.FullName $dest -Force
      "MOVED FILE: $rel -> $dest" | Add-Content $Manifest -Encoding UTF8
    }
}

Get-ChildItem -Path $RepoPath -Recurse -Directory -ErrorAction SilentlyContinue |
  Where-Object {
    ($_.Name -in @("__pycache__", ".pytest_cache")) -and
    $_.FullName -notmatch "\\.git\\" -and
    $_.FullName -notmatch "_cleanup_quarantine"
  } |
  ForEach-Object {
    $rel = Resolve-Path -Path $_.FullName -Relative
    $dest = Join-Path $Quarantine ($rel -replace "^[.\\\/]+","")
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Move-Item $_.FullName $dest -Force
    "MOVED DIR: $rel -> $dest" | Add-Content $Manifest -Encoding UTF8
  }

Write-Host "Safe cleanup completed. Files moved to quarantine, not deleted." -ForegroundColor Green
Write-Host "Manifest: $Manifest" -ForegroundColor Yellow
