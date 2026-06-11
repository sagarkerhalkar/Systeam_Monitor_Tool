param([string]$IpListPath='.\CLIENT_IPS_CLEAN.txt')
$ErrorActionPreference='Stop'
$ips = Get-Content $IpListPath | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' }
Enable-PSRemoting -Force | Out-Null
$current = (Get-Item WSMan:\localhost\Client\TrustedHosts).Value
$list = @()
if($current){ $list += $current.Split(',') | Where-Object {$_} }
$list += $ips
$new = ($list | Sort-Object -Unique) -join ','
Set-Item WSMan:\localhost\Client\TrustedHosts -Value $new -Force
Write-Host "TrustedHosts updated for $($ips.Count) IPs" -ForegroundColor Green
