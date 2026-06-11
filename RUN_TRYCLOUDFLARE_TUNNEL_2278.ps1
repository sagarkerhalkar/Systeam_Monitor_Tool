# Free temporary public URL for Sagar Kerhalkar System Monitor Tool.
# Requires cloudflared.exe installed on this Windows server.
# This creates a random trycloudflare.com URL. Keep this window open while using the public URL.
$ErrorActionPreference='Stop'
$cmd = Get-Command cloudflared.exe -ErrorAction SilentlyContinue
if(-not $cmd){
  Write-Host "cloudflared.exe not found." -ForegroundColor Red
  Write-Host "Install Cloudflare Tunnel client from official Cloudflare downloads, then run this script again." -ForegroundColor Yellow
  exit 1
}
Write-Host "Starting public tunnel to http://localhost:2278" -ForegroundColor Cyan
Write-Host "Dashboard still requires admin login. CSV downloads are blocked from public URL." -ForegroundColor Green
cloudflared tunnel --url http://localhost:2278
