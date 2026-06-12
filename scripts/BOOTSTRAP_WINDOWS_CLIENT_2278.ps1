param(
  [Parameter(Mandatory=$true)][string]$ServerUrl,
  [string]$FileServerUrl = "",
  [int]$IntervalSeconds = 5
)
$ErrorActionPreference='Stop'
if([string]::IsNullOrWhiteSpace($FileServerUrl)){ $FileServerUrl = $ServerUrl }
$ServerUrl = $ServerUrl.TrimEnd('/')
$FileServerUrl = $FileServerUrl.TrimEnd('/')
$Temp='C:\Temp\SagarSystemMonitor'
New-Item -ItemType Directory -Force -Path $Temp | Out-Null
Write-Host "Downloading latest Windows client files from $FileServerUrl" -ForegroundColor Cyan
$CacheTag = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
Invoke-WebRequest "$FileServerUrl/scripts/client_windows.ps1?v=$CacheTag" -OutFile "$Temp\client_windows.ps1" -Headers @{"Cache-Control"="no-cache"}
Invoke-WebRequest "$FileServerUrl/scripts/install_windows_client_2278.ps1?v=$CacheTag" -OutFile "$Temp\install_windows_client_2278.ps1" -Headers @{"Cache-Control"="no-cache"}
Invoke-WebRequest "$FileServerUrl/scripts/DIAGNOSE_WINDOWS_CLIENT_2278.ps1?v=$CacheTag" -OutFile "$Temp\DIAGNOSE_WINDOWS_CLIENT_2278.ps1" -Headers @{"Cache-Control"="no-cache"} -ErrorAction Stop
Invoke-WebRequest "$FileServerUrl/scripts/CHECK_WINDOWS_CLIENT_VISIBLE_DATA.ps1?v=$CacheTag" -OutFile "$Temp\CHECK_WINDOWS_CLIENT_VISIBLE_DATA.ps1" -Headers @{"Cache-Control"="no-cache"} -ErrorAction Stop
Invoke-WebRequest "$FileServerUrl/scripts/CHECK_WINDOWS_USB_MESSAGES.ps1?v=$CacheTag" -OutFile "$Temp\CHECK_WINDOWS_USB_MESSAGES.ps1" -Headers @{"Cache-Control"="no-cache"} -ErrorAction Stop
Write-Host "Downloaded client, installer and diagnostic checker to $Temp" -ForegroundColor Green
powershell -ExecutionPolicy Bypass -File "$Temp\install_windows_client_2278.ps1" -ServerUrl $ServerUrl -IntervalSeconds $IntervalSeconds
