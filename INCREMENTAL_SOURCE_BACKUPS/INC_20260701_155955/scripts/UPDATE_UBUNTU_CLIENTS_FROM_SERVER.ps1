param(
  [Parameter(Mandatory=$true)][string]$ServerUrl,
  [Parameter(Mandatory=$true)][string]$LinuxUser,
  [string]$IpListPath='.\CLIENT_IPS_CLEAN.txt',
  [string]$FileServerUrl=''
)
if(-not $FileServerUrl){ $FileServerUrl = $ServerUrl }
$ips = Get-Content $IpListPath | Where-Object { $_ -match '^\d+\.\d+\.\d+\.\d+$' }
foreach($ip in $ips){
  Write-Host "`n==== UBUNTU $ip ====" -ForegroundColor Cyan
  ssh "$LinuxUser@$ip" "mkdir -p /tmp/cmp && curl -fsSL $FileServerUrl/scripts/BOOTSTRAP_UBUNTU_CLIENT_2278.sh -o /tmp/cmp/BOOTSTRAP_UBUNTU_CLIENT_2278.sh && chmod +x /tmp/cmp/BOOTSTRAP_UBUNTU_CLIENT_2278.sh && sudo SERVER_URL=$ServerUrl FILE_SERVER_URL=$FileServerUrl bash /tmp/cmp/BOOTSTRAP_UBUNTU_CLIENT_2278.sh"
}
