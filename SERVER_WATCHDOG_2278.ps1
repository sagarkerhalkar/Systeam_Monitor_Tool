$ErrorActionPreference = "Continue"
$App = Split-Path -Parent $MyInvocation.MyCommand.Path
$Port = 2278
$DataDir = Join-Path $App "data"
New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
$WatchdogLog = Join-Path $DataDir "server_watchdog.log"
$ConsoleLog = Join-Path $DataDir "server_console.log"
$ErrorLog = Join-Path $DataDir "server_error.log"
function Log([string]$Message) { Add-Content -Path $WatchdogLog -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message" -Encoding UTF8 }
function Find-Python {
  foreach ($name in @("python.exe","py.exe")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
  }
  return $null
}
function Port-Healthy {
  try { $c = New-Object Net.Sockets.TcpClient; $a=$c.BeginConnect("127.0.0.1",$Port,$null,$null); $ok=$a.AsyncWaitHandle.WaitOne(2500,$false); if($ok){$c.EndConnect($a)}; $c.Close(); return $ok } catch { return $false }
}
Log "Watchdog started"
while ($true) {
  try {
    if (Port-Healthy) { Start-Sleep 10; continue }
    Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "SagarSystemHealthMonitor.*(server|universal_server)\.py" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    $python = Find-Python
    if (-not $python) { Log "Python not found"; Start-Sleep 30; continue }
    Log "Starting server with $python"
    Start-Process -FilePath $python -ArgumentList @("-u",(Join-Path $App "universal_server.py"),"--host","0.0.0.0","--port","2278") -WorkingDirectory $App -WindowStyle Hidden -RedirectStandardOutput $ConsoleLog -RedirectStandardError $ErrorLog | Out-Null
    Start-Sleep 8
    if (-not (Port-Healthy)) { Log "Server did not become healthy; retrying" }
  } catch { Log "Watchdog error: $($_.Exception.Message)" }
  Start-Sleep 10
}
