$ErrorActionPreference = 'Stop'
Set-Location 'D:\SagarSystemHealthMonitor'
try { New-NetFirewallRule -DisplayName 'Sagar System Monitor 2278' -Direction Inbound -Protocol TCP -LocalPort 2278 -Action Allow -ErrorAction SilentlyContinue | Out-Null } catch {}
$pyCmd = Get-Command py.exe -ErrorAction SilentlyContinue
if ($pyCmd) {
  & $pyCmd.Source -3 'D:\SagarSystemHealthMonitor\server.py' --host 0.0.0.0 --port 2278
} else {
  $pythonCmd = Get-Command python.exe -ErrorAction Stop
  & $pythonCmd.Source 'D:\SagarSystemHealthMonitor\server.py' --host 0.0.0.0 --port 2278
}
