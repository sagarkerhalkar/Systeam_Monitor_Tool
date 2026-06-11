param([string]$InputPath='.\CLIENT_IPS.txt',[string]$OutputPath='.\CLIENT_IPS_CLEAN.txt')
$ErrorActionPreference='Stop'
$raw = Get-Content $InputPath -ErrorAction Stop
$ips = New-Object System.Collections.Generic.List[string]
foreach($line in $raw){
  if($line.Trim().StartsWith('#')){ continue }
  [regex]::Matches($line,'\b(?:\d{1,3}\.){3}\d{1,3}\b') | ForEach-Object {
    $ip=$_.Value
    $parts=$ip.Split('.') | ForEach-Object {[int]$_}
    if(($parts | Where-Object {$_ -gt 255}).Count -gt 0){ return }
    if($ip -match '^(127|169\.254|224|255)\.'){ return }
    if($ip -in @('10.0.2.15','172.17.0.1','192.168.56.1','192.168.0.1')){ return }
    if(-not $ips.Contains($ip)){ $ips.Add($ip) }
  }
}
$ips | Set-Content $OutputPath -Encoding ASCII
Write-Host "Clean IP count: $($ips.Count)" -ForegroundColor Green
Write-Host "Saved: $OutputPath" -ForegroundColor Cyan
