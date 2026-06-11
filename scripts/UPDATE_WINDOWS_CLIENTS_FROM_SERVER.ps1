param(
  [Parameter(Mandatory=$true)][string]$ServerUrl,
  [string]$IpListPath='.\CLIENT_IPS_CLEAN.txt',
  [string]$FileServerUrl=''
)
$ErrorActionPreference='Continue'
if(-not $FileServerUrl){
  # V5.6 single-port mode: main server on 2278 also serves /scripts. No 8511 window required.
  $FileServerUrl = $ServerUrl
}
$ips = Get-Content $IpListPath | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' }
foreach($ip in $ips){
  Write-Host "`n==== WINDOWS $ip ====" -ForegroundColor Cyan
  $portOpen = Test-NetConnection -ComputerName $ip -Port 5985 -InformationLevel Quiet -WarningAction SilentlyContinue
  if(-not $portOpen){ Write-Host "WinRM 5985 closed. Use manual bootstrap on this PC once." -ForegroundColor Yellow; continue }
  try{
    Invoke-Command -ComputerName $ip -ScriptBlock {
      param($ServerUrl,$FileServerUrl)
      $Temp='C:\Temp\CommercialMonitorPro'; New-Item -ItemType Directory -Force -Path $Temp | Out-Null
      Invoke-WebRequest "$($FileServerUrl.TrimEnd('/'))/scripts/BOOTSTRAP_WINDOWS_CLIENT_2278.ps1" -OutFile "$Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1"
      powershell -ExecutionPolicy Bypass -File "$Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1" -ServerUrl $ServerUrl -FileServerUrl $FileServerUrl
    } -ArgumentList $ServerUrl,$FileServerUrl
    Write-Host "Updated" -ForegroundColor Green
  } catch { Write-Host "FAILED: $($_.Exception.Message)" -ForegroundColor Red }
}
