
param(
  [string]$RepoPath = "D:\SagarSystemHealthMonitor",
  [string]$Url = "http://localhost:2278"
)

$ErrorActionPreference = "Continue"

Write-Host "Running startup check..." -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File (Join-Path $RepoPath "scripts\startup_check.ps1") -RepoPath $RepoPath

Write-Host "Running security scan..." -ForegroundColor Cyan
$py = Get-Command python -ErrorAction SilentlyContinue
if(-not $py){ $py = Get-Command py -ErrorAction SilentlyContinue }
if($py){
  & $py.Source (Join-Path $RepoPath "scripts\security_scan.py") $RepoPath
}else{
  Write-Host "Python not found. Security scan skipped." -ForegroundColor Yellow
}

Write-Host "Running HTTP/running check..." -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File (Join-Path $RepoPath "scripts\running_check.ps1") -RepoPath $RepoPath -Url $Url

Write-Host "All checks completed. See reports\final_v2." -ForegroundColor Green
