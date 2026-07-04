$ErrorActionPreference = 'Continue'
$App = 'D:\SagarSystemHealthMonitor'
$Python = 'C:\Program Files\LibreOffice\program\python.exe'
$ServerPy = Join-Path $App 'server.py'
$DataDir = Join-Path $App 'data'
$BootLog = Join-Path $DataDir 'server_boot_system.log'
$StdOut = Join-Path $DataDir 'server_boot_stdout.log'
$StdErr = Join-Path $DataDir 'server_boot_stderr.log'
New-Item -ItemType Directory -Path $DataDir -Force | Out-Null
Set-Location $App
$env:PYTHONUNBUFFERED = '1'
$env:CMP_ADMIN_PASSWORD = if ($env:CMP_ADMIN_PASSWORD) { $env:CMP_ADMIN_PASSWORD } else { 'Admin@12345' }

try {
  New-NetFirewallRule -DisplayName 'Sagar System Monitor 2278' -Direction Inbound -Protocol TCP -LocalPort 2278 -Action Allow -ErrorAction SilentlyContinue | Out-Null
} catch {}

while ($true) {
  Add-Content -Path $BootLog -Value ("
==== START " + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss') + " as " + [Security.Principal.WindowsIdentity]::GetCurrent().Name + " ====")
  Add-Content -Path $BootLog -Value ("App: $App")
  Add-Content -Path $BootLog -Value ("Python: $Python")
  Add-Content -Path $BootLog -Value ("Server: $ServerPy")
  try {
    & $Python $ServerPy --host 0.0.0.0 --port 2278 1>> $StdOut 2>> $StdErr
    $code = $LASTEXITCODE
    Add-Content -Path $BootLog -Value ("Server exited with code: $code at " + (Get-Date).ToString('yyyy-MM-dd HH:mm:ss'))
  } catch {
    Add-Content -Path $BootLog -Value ("Server crashed: " + $_.Exception.Message)
  }
  Start-Sleep -Seconds 10
}
