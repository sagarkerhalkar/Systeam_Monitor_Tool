param(
  [Parameter(Mandatory=$true)][string]$OldBuildFolder
)
$ErrorActionPreference='Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$OldData = Join-Path $OldBuildFolder 'data'
$NewData = Join-Path $Here 'data'
if(!(Test-Path $OldData)){ throw "Old data folder not found: $OldData" }
New-Item -ItemType Directory -Force -Path $NewData | Out-Null
Copy-Item -Force -Recurse (Join-Path $OldData '*') $NewData
Write-Host "Copied old data from $OldData to $NewData" -ForegroundColor Green
Write-Host "Now start RUN_SERVER_2278.ps1 again." -ForegroundColor Cyan
