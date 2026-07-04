# Sagar Kerhalkar System Health Monitor Tool

**Version target:** V8.4 / port `2278`  
**Main server folder:** `D:\SagarSystemHealthMonitor`  
**Default public URL:** `https://monitor.sagarkerhalkar.com`  
**Local dashboard:** `http://127.0.0.1:2278` or `http://SERVER-IP:2278`  
**Client heartbeat:** 5 seconds by default  
**Dashboard refresh:** 5 seconds by default

This application is a Windows + Ubuntu system health monitoring platform for classrooms, labs, offices, cyber cafes, campus computer labs, and multi-LAN/VLAN environments.

It is not only a simple uptime tool. It is designed to collect and show:

- Online/offline machine status
- Hostname, machine ID, OS, local IPs, public IP, ISP
- CPU usage and CPU temperature where available
- RAM usage, total capacity, used capacity
- SSD/HDD/NVMe capacity and usage
- GPU names, GPU memory, usage, temperature where the OS/vendor provides real data
- USB and peripheral inventory: keyboard, mouse, audio, camera, storage, etc.
- Installed software inventory
- Current upload/download traffic
- Daily upload/download totals
- VPN detection
- Human-readable change log
- Notifications and alert rules
- Day history and CSV exports
- Admin messages / client messages
- Deploy page with copy-ready Windows and Ubuntu install/test commands

> Important rule for monitoring data: **do not show fake hardware values.** If Windows/Linux cannot provide an exact value, show `N/A` instead of guessing.

---

## 1. Folder structure

Typical folder:

```text
D:\SagarSystemHealthMonitor
│
├─ server.py
├─ RUN_SERVER_2278.ps1
├─ RUN_SERVER_2278.bat
├─ INSTALL_SERVER_AUTOSTART_TASK.ps1
├─ UNINSTALL_SERVER_AUTOSTART_TASK.ps1
├─ BUILD_WINDOWS_CLIENT_EXE.ps1
├─ CLIENT_IPS.txt
│
├─ public\
│  ├─ index.html
│  ├─ app.js
│  └─ styles.css
│
├─ scripts\
│  ├─ BOOTSTRAP_WINDOWS_CLIENT_2278.ps1
│  ├─ BOOTSTRAP_UBUNTU_CLIENT_2278.sh
│  ├─ client_windows.ps1
│  ├─ client_ubuntu.sh
│  ├─ install_windows_client_2278.ps1
│  ├─ install_ubuntu_client_2278.sh
│  ├─ DIAGNOSE_WINDOWS_CLIENT_2278.ps1
│  ├─ CHECK_WINDOWS_CLIENT_VISIBLE_DATA.ps1
│  ├─ CHECK_WINDOWS_USB_MESSAGES.ps1
│  ├─ CHECK_UBUNTU_CLIENT_VISIBLE_DATA.sh
│  ├─ CHECK_UBUNTU_MESSAGES.sh
│  ├─ UPDATE_WINDOWS_CLIENTS_FROM_SERVER.ps1
│  └─ UPDATE_UBUNTU_CLIENTS_FROM_SERVER.ps1
│
├─ data\
│  ├─ monitor.db
│  ├─ server.log
│  └─ server_isp_cache.json
│
└─ dist\
   ├─ SagarMonitorClientSetup.vbs
   └─ sagar-system-monitor-client_*.deb
```

Main database:

```text
D:\SagarSystemHealthMonitor\data\monitor.db
```

Important tables:

```text
latest
heartbeats
notification_rules
notifications
change_events
notification_state
settings
client_messages
client_message_receipts
users
```

---

## 2. Requirements

### Server machine

Recommended:

```text
OS: Windows 10/11 or Windows Server
Python: 3.10+ recommended
RAM: 8 GB minimum, 16 GB+ recommended
Disk: SSD recommended
Network: static IP preferred
Port: TCP 2278 open
```

The server code mainly uses Python standard library:

```text
sqlite3
http.server
json
csv
threading
subprocess
```

So usually no extra Python packages are required.

### Windows clients

Recommended:

```text
Windows 10/11
PowerShell 5+
Administrator permission for installation
Internet/LAN access to server URL
```

Optional but useful:

```text
nvidia-smi for NVIDIA GPU actual memory/usage/temp
Windows performance counters for OS hardware data
```

### Ubuntu clients

Recommended:

```text
Ubuntu 20.04 / 22.04 / 24.04
sudo access
curl
systemd
```

Installer can install common tools:

```text
curl python3 iproute2 procps coreutils util-linux pciutils usbutils lm-sensors libnotify-bin zenity
```

---

## 3. Start server manually

Open PowerShell as Administrator:

```powershell
cd D:\SagarSystemHealthMonitor
powershell -ExecutionPolicy Bypass -File .\RUN_SERVER_2278.ps1
```

What this does:

```text
- Starts server.py
- Binds to 0.0.0.0
- Uses port 2278
- Adds firewall rule for TCP 2278
```

Local test:

```powershell
Invoke-WebRequest "http://127.0.0.1:2278/api/health" -UseBasicParsing
```

Expected result includes:

```json
{
  "ok": true,
  "app_name": "...",
  "version": "8.4"
}
```

Browser:

```text
http://127.0.0.1:2278
http://SERVER-IP:2278
https://monitor.sagarkerhalkar.com
```

---

## 4. Install server auto-start

Use this so the dashboard starts after restart/power cut.

```powershell
cd D:\SagarSystemHealthMonitor
powershell -ExecutionPolicy Bypass -File .\INSTALL_SERVER_AUTOSTART_TASK.ps1
```

Scheduled task created:

```text
SagarSystemMonitor_Server_2278
```

Check task:

```powershell
Get-ScheduledTask -TaskName "SagarSystemMonitor_Server_2278"
```

Start task manually:

```powershell
Start-ScheduledTask -TaskName "SagarSystemMonitor_Server_2278"
```

Stop task manually:

```powershell
Stop-ScheduledTask -TaskName "SagarSystemMonitor_Server_2278"
```

Uninstall server auto-start:

```powershell
cd D:\SagarSystemHealthMonitor
powershell -ExecutionPolicy Bypass -File .\UNINSTALL_SERVER_AUTOSTART_TASK.ps1
```

---

## 5. Login

Default admin login from original build:

```text
Username: admin
Password: Admin@12345
```

Change the password from the Settings page after installation.

If login page opens but the button does nothing:

```text
1. Press Ctrl + Shift + R
2. Try Incognito
3. Open browser console with F12 and check red JavaScript errors
4. Test login API directly from PowerShell
```

Login API test:

```powershell
$Pass = "Admin@12345"

$body = @{
  username = "admin"
  password = $Pass
} | ConvertTo-Json

Invoke-WebRequest "http://127.0.0.1:2278/api/auth/login" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body `
  -UseBasicParsing
```

---

## 6. Public URL / domain

Default public URL:

```text
https://monitor.sagarkerhalkar.com
```

You can also use IP fallback:

```text
http://156.156.40.51:2278
```

For another campus, use one of these:

```text
Option A: Fixed public IP + DNS A record
Option B: Cloudflare Tunnel
Option C: VPN/MPLS private campus network
Option D: Local-only LAN server without public internet
```

Recommended domain format:

```text
monitor-campusname.yourdomain.com
```

After changing the URL, update:

```text
- Deploy page Windows install command
- Deploy page Ubuntu install command
- FileServerUrl
- Client ServerUrl
```

Always test:

```powershell
Invoke-WebRequest "https://YOUR-DOMAIN/api/health" -UseBasicParsing
```

or:

```bash
curl -fsSL https://YOUR-DOMAIN/api/health
```

---

## 7. Windows client install / update

Run on each Windows client as Administrator.

Current recommended Windows install/update command:

```powershell
mkdir C:\Temp -Force
Remove-Item C:\Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 -Force -ErrorAction SilentlyContinue

iwr "https://monitor.sagarkerhalkar.com/scripts/BOOTSTRAP_WINDOWS_CLIENT_2278.ps1?strictgpu=v1" -OutFile C:\Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1

powershell -ExecutionPolicy Bypass -File C:\Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 -ServerUrl "https://monitor.sagarkerhalkar.com" -FileServerUrl "https://monitor.sagarkerhalkar.com" -IntervalSeconds 5
```

IP fallback:

```powershell
mkdir C:\Temp -Force
Remove-Item C:\Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 -Force -ErrorAction SilentlyContinue

iwr "http://156.156.40.51:2278/scripts/BOOTSTRAP_WINDOWS_CLIENT_2278.ps1?strictgpu=v1" -OutFile C:\Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1

powershell -ExecutionPolicy Bypass -File C:\Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 -ServerUrl "http://156.156.40.51:2278" -FileServerUrl "http://156.156.40.51:2278" -IntervalSeconds 5
```

What the Windows bootstrap does:

```text
Downloads latest:
- client_windows.ps1
- install_windows_client_2278.ps1
- DIAGNOSE_WINDOWS_CLIENT_2278.ps1
- CHECK_WINDOWS_CLIENT_VISIBLE_DATA.ps1
- CHECK_WINDOWS_USB_MESSAGES.ps1

Installs scheduled task:
- SagarSystemMonitor_Client_2278

Client folder:
- C:\ProgramData\SagarSystemMonitor

Temporary downloaded scripts:
- C:\Temp\SagarSystemMonitor
```

Windows client scheduled task:

```text
SagarSystemMonitor_Client_2278
```

Check scheduled task:

```powershell
Get-ScheduledTask -TaskName "SagarSystemMonitor_Client_2278"
```

Start client task:

```powershell
Start-ScheduledTask -TaskName "SagarSystemMonitor_Client_2278"
```

Stop client task:

```powershell
Stop-ScheduledTask -TaskName "SagarSystemMonitor_Client_2278"
```

Uninstall Windows client:

```powershell
powershell -ExecutionPolicy Bypass -File C:\Temp\SagarSystemMonitor\uninstall_windows_client.ps1
```

If uninstall script is not in temp, download it:

```powershell
iwr "https://monitor.sagarkerhalkar.com/scripts/uninstall_windows_client.ps1" -OutFile C:\Temp\uninstall_windows_client.ps1
powershell -ExecutionPolicy Bypass -File C:\Temp\uninstall_windows_client.ps1
```

---

## 8. Windows client test / diagnosis

Run on Windows client as Administrator:

```powershell
mkdir C:\Temp -Force

Copy-Item C:\ProgramData\SagarSystemMonitor\last_payload.json C:\Temp\last_payload_copy.json -Force -ErrorAction SilentlyContinue
Copy-Item C:\ProgramData\SagarSystemMonitor\client_status.json C:\Temp\client_status_copy.json -Force -ErrorAction SilentlyContinue
Copy-Item C:\ProgramData\SagarSystemMonitor\server_messages.log C:\Temp\server_messages_copy.log -Force -ErrorAction SilentlyContinue

Write-Host "`n=== CLIENT STATUS ===" -ForegroundColor Cyan
type C:\Temp\client_status_copy.json

Write-Host "`n=== LAST PAYLOAD ===" -ForegroundColor Cyan
type C:\Temp\last_payload_copy.json

Write-Host "`n=== GPU DATA CHECK ===" -ForegroundColor Cyan
Select-String -Path C:\Temp\last_payload_copy.json -Pattern "gpus|gpu|memory_total_mb|dedicated_memory_mb|shared_memory_mb|usage_percent|temperature_c|source"

Write-Host "`n=== SERVER MESSAGES ===" -ForegroundColor Cyan
type C:\Temp\server_messages_copy.log

Write-Host "`n=== VISIBLE DATA CHECK ===" -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File C:\Temp\SagarSystemMonitor\CHECK_WINDOWS_CLIENT_VISIBLE_DATA.ps1 -ServerUrl "https://monitor.sagarkerhalkar.com"

Write-Host "`n=== USB MESSAGE CHECK ===" -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File C:\Temp\SagarSystemMonitor\CHECK_WINDOWS_USB_MESSAGES.ps1 -ServerUrl "https://monitor.sagarkerhalkar.com"

Write-Host "`n=== FULL DIAGNOSE ===" -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File C:\Temp\SagarSystemMonitor\DIAGNOSE_WINDOWS_CLIENT_2278.ps1 -ServerUrl "https://monitor.sagarkerhalkar.com"
```

Important output files:

```text
C:\ProgramData\SagarSystemMonitor\client_status.json
C:\ProgramData\SagarSystemMonitor\last_payload.json
C:\ProgramData\SagarSystemMonitor\client_error.log
C:\ProgramData\SagarSystemMonitor\server_messages.log
```

---

## 9. Ubuntu client install / update

Run on Ubuntu client:

```bash
PUBLIC_URL="https://monitor.sagarkerhalkar.com"
curl -fsSL "$PUBLIC_URL/scripts/BOOTSTRAP_UBUNTU_CLIENT_2278.sh?restore=v84fixed" -o /tmp/bootstrap.sh
sudo SERVER_URL="$PUBLIC_URL" FILE_SERVER_URL="$PUBLIC_URL" INTERVAL_SECONDS=5 bash /tmp/bootstrap.sh
```

IP fallback:

```bash
PUBLIC_URL="http://156.156.40.51:2278"
curl -fsSL "$PUBLIC_URL/scripts/BOOTSTRAP_UBUNTU_CLIENT_2278.sh?restore=v84fixed" -o /tmp/bootstrap.sh
sudo SERVER_URL="$PUBLIC_URL" FILE_SERVER_URL="$PUBLIC_URL" INTERVAL_SECONDS=5 bash /tmp/bootstrap.sh
```

What Ubuntu bootstrap does:

```text
Checks /api/health
Downloads:
- client_ubuntu.sh
- install_ubuntu_client_2278.sh
- CHECK_UBUNTU_CLIENT_VISIBLE_DATA.sh
- CHECK_UBUNTU_MESSAGES.sh

Installs systemd service:
- sagar-system-monitor-client.service
```

Ubuntu client paths:

```text
Client script:
  /opt/sagar-system-monitor/client_ubuntu.sh

Data folder:
  /var/lib/commercial-monitor-pro

Service:
  sagar-system-monitor-client.service
```

---

## 10. Ubuntu client test / diagnosis

Run on Ubuntu client:

```bash
sudo mkdir -p /tmp/sagar-monitor-test

sudo cp /var/lib/commercial-monitor-pro/client_status.json /tmp/sagar-monitor-test/client_status.json 2>/dev/null || true
sudo cp /var/lib/commercial-monitor-pro/last_payload.json /tmp/sagar-monitor-test/last_payload.json 2>/dev/null || true
sudo cp /var/lib/commercial-monitor-pro/server_messages.log /tmp/sagar-monitor-test/server_messages.log 2>/dev/null || true

echo ""
echo "=== CLIENT STATUS ==="
sudo cat /tmp/sagar-monitor-test/client_status.json

echo ""
echo "=== LAST PAYLOAD ==="
sudo cat /tmp/sagar-monitor-test/last_payload.json

echo ""
echo "=== SERVER MESSAGES ==="
sudo cat /tmp/sagar-monitor-test/server_messages.log

echo ""
echo "=== SERVICE STATUS ==="
sudo systemctl status sagar-system-monitor-client.service --no-pager

echo ""
echo "=== CLIENT JOURNAL ==="
sudo journalctl -u sagar-system-monitor-client.service -n 80 --no-pager

echo ""
echo "=== SERVER HEALTH ==="
curl -fsSL https://monitor.sagarkerhalkar.com/api/health
```

IP fallback health test:

```bash
curl -fsSL http://156.156.40.51:2278/api/health
```

Restart Ubuntu client:

```bash
sudo systemctl restart sagar-system-monitor-client.service
```

Stop Ubuntu client:

```bash
sudo systemctl stop sagar-system-monitor-client.service
```

Uninstall Ubuntu client:

```bash
curl -fsSL https://monitor.sagarkerhalkar.com/scripts/uninstall_ubuntu_client.sh -o /tmp/uninstall_ubuntu_client.sh
chmod +x /tmp/uninstall_ubuntu_client.sh
sudo /tmp/uninstall_ubuntu_client.sh
```

---

## 11. Deploy page usage

Open dashboard:

```text
Deploy
```

Use the Deploy page for:

```text
- Windows install/update
- Windows IP fallback
- Windows test/diagnosis
- Ubuntu install/update
- Ubuntu IP fallback
- Ubuntu test/diagnosis
```

When client code changes:

```text
1. Restart server so latest /scripts are served.
2. Open Deploy page.
3. Copy Windows or Ubuntu install/update command.
4. Run again on already-installed clients.
5. No uninstall needed.
```

Admin can edit Deploy commands from dashboard if the custom Deploy page patch is installed.

Recommended command version tags:

```text
Windows strict GPU client:
?strictgpu=v1

Ubuntu V8.4 fixed:
?restore=v84fixed
```

These query tags force browser/client cache refresh. They do not change server logic by themselves.

---

## 12. Notifications

Notification rules are managed in:

```text
Notifications page
```

Common rules:

```text
CPU high
RAM high
Disk high
CPU temperature high
GPU temperature high
WAN download/upload
Machine offline
USB change
Hardware change
Software change
IP change
VPN change
```

To disable offline notification:

```text
Notifications page -> Rules -> Machine offline -> disable
```

Direct database method:

```powershell
cd D:\SagarSystemHealthMonitor

@"
import sqlite3
from pathlib import Path

db = Path("data/monitor.db")
con = sqlite3.connect(db)
cur = con.cursor()
cur.execute("""
UPDATE notification_rules
SET enabled = 0
WHERE id = 'offline' OR metric = 'offline_minutes'
""")
con.commit()
con.close()
print("Offline notification disabled.")
"@ | Set-Content C:\Temp\disable_offline_notification.py -Encoding UTF8

python C:\Temp\disable_offline_notification.py
```

Enable again:

```powershell
cd D:\SagarSystemHealthMonitor

@"
import sqlite3
from pathlib import Path

db = Path("data/monitor.db")
con = sqlite3.connect(db)
cur = con.cursor()
cur.execute("""
UPDATE notification_rules
SET enabled = 1
WHERE id = 'offline' OR metric = 'offline_minutes'
""")
con.commit()
con.close()
print("Offline notification enabled.")
"@ | Set-Content C:\Temp\enable_offline_notification.py -Encoding UTF8

python C:\Temp\enable_offline_notification.py
```

---

## 13. Backup plan

### 13.1 Full application backup

Run on server:

```powershell
$App = "D:\SagarSystemHealthMonitor"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = "D:\SagarSystemHealthMonitor_BACKUP_$Stamp"

robocopy $App $Backup /E /XD ".git" "__pycache__" /XF "*.pyc"

Write-Host "Full backup created:"
Write-Host $Backup
```

This backs up:

```text
server.py
public UI
scripts
data/monitor.db
data/server.log
dist
backup folders
```

### 13.2 Database-only backup

Safer SQLite backup using Python:

```powershell
cd D:\SagarSystemHealthMonitor

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Out = "D:\SagarSystemHealthMonitor_DB_BACKUP_$Stamp.db"

python - << "PY"
import sqlite3, sys
src = "data/monitor.db"
dst = sys.argv[1]
src_con = sqlite3.connect(src)
dst_con = sqlite3.connect(dst)
src_con.backup(dst_con)
dst_con.close()
src_con.close()
print("DB backup:", dst)
PY $Out
```

### 13.3 Before every patch

Before changing server/UI/client scripts:

```powershell
$App = "D:\SagarSystemHealthMonitor"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = "$App\BACKUP_MANUAL_$Stamp"

New-Item -ItemType Directory -Path $Backup -Force | Out-Null

Copy-Item "$App\server.py" "$Backup\server.py" -Force -ErrorAction SilentlyContinue
Copy-Item "$App\public\index.html" "$Backup\index.html" -Force -ErrorAction SilentlyContinue
Copy-Item "$App\public\app.js" "$Backup\app.js" -Force -ErrorAction SilentlyContinue
Copy-Item "$App\public\styles.css" "$Backup\styles.css" -Force -ErrorAction SilentlyContinue
Copy-Item "$App\scripts\client_windows.ps1" "$Backup\client_windows.ps1" -Force -ErrorAction SilentlyContinue
Copy-Item "$App\scripts\client_ubuntu.sh" "$Backup\client_ubuntu.sh" -Force -ErrorAction SilentlyContinue

Write-Host "Patch backup created:"
Write-Host $Backup
```

---

## 14. Restore plan

### 14.1 Restore UI only

Use this when login or dashboard JavaScript breaks:

```powershell
$App = "D:\SagarSystemHealthMonitor"
$Backup = "D:\SagarSystemHealthMonitor\BACKUP_FOLDER_NAME"

Copy-Item "$Backup\index.html" "$App\public\index.html" -Force
Copy-Item "$Backup\app.js" "$App\public\app.js" -Force
Copy-Item "$Backup\styles.css" "$App\public\styles.css" -Force

Restart-Computer
```

Then browser:

```text
Ctrl + Shift + R
```

### 14.2 Restore Windows client only

```powershell
$App = "D:\SagarSystemHealthMonitor"
$Backup = "D:\SagarSystemHealthMonitor\BACKUP_FOLDER_NAME"

Copy-Item "$Backup\client_windows.ps1" "$App\scripts\client_windows.ps1" -Force
```

Then restart server and run Windows install/update command again on clients.

### 14.3 Restore server.py only

```powershell
$App = "D:\SagarSystemHealthMonitor"
$Backup = "D:\SagarSystemHealthMonitor\BACKUP_FOLDER_NAME"

Copy-Item "$Backup\server.py" "$App\server.py" -Force

Restart-Computer
```

### 14.4 Restore full folder

```powershell
$Backup = "D:\SagarSystemHealthMonitor_BACKUP_YYYYMMDD_HHMMSS"
$App = "D:\SagarSystemHealthMonitor"

Stop-ScheduledTask -TaskName "SagarSystemMonitor_Server_2278" -ErrorAction SilentlyContinue

robocopy $Backup $App /E

Restart-Computer
```

---

## 15. Server self-test / CI check

Run before and after any patch:

```powershell
cd D:\SagarSystemHealthMonitor

python -m py_compile .\server.py

Invoke-WebRequest "http://127.0.0.1:2278/api/health" -UseBasicParsing
```

Check important files:

```powershell
Test-Path .\server.py
Test-Path .\public\index.html
Test-Path .\public\app.js
Test-Path .\public\styles.css
Test-Path .\scripts\client_windows.ps1
Test-Path .\scripts\client_ubuntu.sh
```

Optional JavaScript syntax check if Node.js is installed:

```powershell
node --check .\public\app.js
```

Check server process:

```powershell
Get-NetTCPConnection -LocalPort 2278 -ErrorAction SilentlyContinue
```

Check firewall rule:

```powershell
Get-NetFirewallRule | Where-Object DisplayName -match "Sagar|2278"
```

---

## 16. Client self-test checklist

### Windows machine should show

```text
C:\ProgramData\SagarSystemMonitor\client_status.json exists
C:\ProgramData\SagarSystemMonitor\last_payload.json exists
Scheduled task SagarSystemMonitor_Client_2278 exists
/api/health reachable from client
Dashboard Last Seen updates every few seconds
```

Windows quick check:

```powershell
Get-ScheduledTask -TaskName "SagarSystemMonitor_Client_2278"

Invoke-WebRequest "https://monitor.sagarkerhalkar.com/api/health" -UseBasicParsing

Copy-Item C:\ProgramData\SagarSystemMonitor\last_payload.json C:\Temp\last_payload_copy.json -Force -ErrorAction SilentlyContinue
type C:\Temp\last_payload_copy.json
```

### Ubuntu machine should show

```text
/var/lib/commercial-monitor-pro/client_status.json exists
/var/lib/commercial-monitor-pro/last_payload.json exists
sagar-system-monitor-client.service active
/api/health reachable from client
Dashboard Last Seen updates every few seconds
```

Ubuntu quick check:

```bash
sudo systemctl status sagar-system-monitor-client.service --no-pager
curl -fsSL https://monitor.sagarkerhalkar.com/api/health
sudo cat /var/lib/commercial-monitor-pro/client_status.json
```

---

## 17. New campus installation plan

### Step 1: Prepare server

On new campus server:

```powershell
mkdir D:\SagarSystemHealthMonitor
```

Copy the full application folder into:

```text
D:\SagarSystemHealthMonitor
```

Install Python.

Test:

```powershell
python --version
```

Start server:

```powershell
cd D:\SagarSystemHealthMonitor
powershell -ExecutionPolicy Bypass -File .\RUN_SERVER_2278.ps1
```

Test local:

```powershell
Invoke-WebRequest "http://127.0.0.1:2278/api/health" -UseBasicParsing
```

Install auto-start:

```powershell
cd D:\SagarSystemHealthMonitor
powershell -ExecutionPolicy Bypass -File .\INSTALL_SERVER_AUTOSTART_TASK.ps1
```

### Step 2: Network / domain

Choose campus URL:

```text
https://monitor-campus1.example.com
```

or local-only:

```text
http://SERVER-LAN-IP:2278
```

Open firewall:

```powershell
New-NetFirewallRule -DisplayName "Sagar System Monitor 2278" -Direction Inbound -Protocol TCP -LocalPort 2278 -Action Allow
```

Test from another PC:

```powershell
Invoke-WebRequest "http://SERVER-LAN-IP:2278/api/health" -UseBasicParsing
```

### Step 3: Update Deploy page commands

In dashboard:

```text
Deploy -> Edit Commands
```

Replace:

```text
https://monitor.sagarkerhalkar.com
```

with campus URL:

```text
https://monitor-campus1.example.com
```

Save commands.

### Step 4: Install clients

Windows:

```powershell
mkdir C:\Temp -Force
Remove-Item C:\Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 -Force -ErrorAction SilentlyContinue

iwr "https://monitor-campus1.example.com/scripts/BOOTSTRAP_WINDOWS_CLIENT_2278.ps1?strictgpu=v1" -OutFile C:\Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1

powershell -ExecutionPolicy Bypass -File C:\Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 -ServerUrl "https://monitor-campus1.example.com" -FileServerUrl "https://monitor-campus1.example.com" -IntervalSeconds 5
```

Ubuntu:

```bash
PUBLIC_URL="https://monitor-campus1.example.com"
curl -fsSL "$PUBLIC_URL/scripts/BOOTSTRAP_UBUNTU_CLIENT_2278.sh?restore=v84fixed" -o /tmp/bootstrap.sh
sudo SERVER_URL="$PUBLIC_URL" FILE_SERVER_URL="$PUBLIC_URL" INTERVAL_SECONDS=5 bash /tmp/bootstrap.sh
```

### Step 5: Verify dashboard

Check pages:

```text
Machine Fleet
Machine 360
Hardware
Software
USB + Peripherals
Network + VPN
Day History
Notifications
Client Messages
Deploy
```

---

## 18. Bulk rollout to many clients

### Windows bulk rollout

Requirements:

```text
- WinRM enabled on clients
- Server can reach client IPs
- CLIENT_IPS_CLEAN.txt contains one IP per line
```

Prepare IP list:

```powershell
cd D:\SagarSystemHealthMonitor\scripts
powershell -ExecutionPolicy Bypass -File .\CLEAN_CLIENT_IP_LIST.ps1
```

Enable WinRM once on each Windows client:

```powershell
powershell -ExecutionPolicy Bypass -File .\ENABLE_WINRM_ON_WINDOWS_CLIENT_ONE_TIME.ps1
```

Prepare trusted hosts on server:

```powershell
powershell -ExecutionPolicy Bypass -File .\PREPARE_SERVER_TRUSTEDHOSTS.ps1
```

Run bulk Windows update:

```powershell
cd D:\SagarSystemHealthMonitor\scripts
powershell -ExecutionPolicy Bypass -File .\UPDATE_WINDOWS_CLIENTS_FROM_SERVER.ps1 `
  -ServerUrl "https://monitor.sagarkerhalkar.com" `
  -FileServerUrl "https://monitor.sagarkerhalkar.com" `
  -IpListPath ".\CLIENT_IPS_CLEAN.txt"
```

### Ubuntu bulk rollout

Requirements:

```text
- SSH access to Ubuntu clients
- sudo permission
- CLIENT_IPS_CLEAN.txt contains Ubuntu IPs
```

Run:

```powershell
cd D:\SagarSystemHealthMonitor\scripts
powershell -ExecutionPolicy Bypass -File .\UPDATE_UBUNTU_CLIENTS_FROM_SERVER.ps1 `
  -ServerUrl "https://monitor.sagarkerhalkar.com" `
  -FileServerUrl "https://monitor.sagarkerhalkar.com" `
  -LinuxUser "YOUR_LINUX_USERNAME" `
  -IpListPath ".\CLIENT_IPS_CLEAN.txt"
```

### Important for very large deployments

For thousands of clients, do not update all machines at once.

Use staged batches:

```text
Batch 1: 10 machines
Batch 2: 50 machines
Batch 3: 200 machines
Batch 4: one lab / one VLAN
Batch 5: full campus
```

Recommended for very large fleets:

```text
- Use 15/30/60 second client interval instead of 5 seconds if server load is high
- Use one monitoring server per campus or per major VLAN
- Keep database on SSD
- Back up data/monitor.db daily
- Keep old backup before every client/server update
```

A single Python + SQLite server can work well for small/medium labs, but **10,000+ Windows clients plus 10,000+ Ubuntu clients at 5-second heartbeat needs proper load testing and likely a scaled architecture**. Do not promise 100% production scale without testing the real network, disk, and server CPU/RAM.

---

## 19. Docker server deployment

Docker is useful for the **server/dashboard**.

Important:

```text
Docker does not replace Windows/Ubuntu client installation.
Hardware data still comes from client scripts running on each real machine.
```

### Dockerfile

Create `Dockerfile` in the app folder:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY . /app

EXPOSE 2278

CMD ["python", "server.py", "--host", "0.0.0.0", "--port", "2278"]
```

Build image:

```bash
docker build -t sagar-system-monitor:8.4 .
```

Run container:

```bash
docker run -d \
  --name sagar-system-monitor \
  -p 2278:2278 \
  -v sagar_monitor_data:/app/data \
  sagar-system-monitor:8.4
```

Check:

```bash
curl -fsSL http://127.0.0.1:2278/api/health
```

### docker-compose.yml

```yaml
services:
  sagar-system-monitor:
    build: .
    container_name: sagar-system-monitor
    restart: unless-stopped
    ports:
      - "2278:2278"
    volumes:
      - ./data:/app/data
      - ./public:/app/public
      - ./scripts:/app/scripts
```

Start:

```bash
docker compose up -d --build
```

Logs:

```bash
docker logs -f sagar-system-monitor
```

Stop:

```bash
docker compose down
```

Backup Docker data:

```bash
tar -czf sagar-monitor-data-backup.tar.gz data
```

### Docker production notes

For production:

```text
- Put Nginx/Caddy/Cloudflare Tunnel in front for HTTPS
- Mount data volume
- Do not store monitor.db only inside disposable container layer
- Keep scripts volume mounted if you edit client scripts often
- Test client downloads from /scripts after deployment
```

Client install commands must use the Docker server URL:

```text
https://your-docker-domain.example.com
```

---

## 20. CI/CD workflow

Recommended Git workflow:

```bash
git checkout -b feature/safe-change-name
git status
git add .
git commit -m "Safe change: describe exact issue"
git push
```

Before commit, run:

```powershell
cd D:\SagarSystemHealthMonitor

python -m py_compile .\server.py

if (Get-Command node -ErrorAction SilentlyContinue) {
  node --check .\public\app.js
}

Invoke-WebRequest "http://127.0.0.1:2278/api/health" -UseBasicParsing
```

Suggested GitHub Actions file:

```yaml
name: Sagar Monitor CI

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: windows-latest

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Python compile
        run: python -m py_compile server.py

      - name: JavaScript syntax check
        run: node --check public/app.js

      - name: Check important files
        shell: pwsh
        run: |
          Test-Path .\public\index.html
          Test-Path .\public\app.js
          Test-Path .\public\styles.css
          Test-Path .\scripts\client_windows.ps1
          Test-Path .\scripts\client_ubuntu.sh
          Test-Path .\scripts\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1
          Test-Path .\scripts\BOOTSTRAP_UBUNTU_CLIENT_2278.sh
```

---

## 21. Data accuracy rules

### GPU data

Correct policy:

```text
NVIDIA:
- Use nvidia-smi for actual memory, used memory, usage, temperature.

Intel / AMD integrated:
- Use exact OS-provided data only.
- If exact usage/memory is not available, show N/A.
- Do not fake memory as RAM / 2.
- Do not show global counter as per-GPU usage if it is not reliable.

Dashboard:
- Show source field when useful.
- Old payload data may remain until client sends fresh heartbeat.
```

### Internet speed

Current upload/download is adapter traffic, not always full ISP capacity speed test.

Meaning:

```text
Current Down/Up = live traffic currently used by the machine.
ISP speed test = separate active probe if configured.
```

### Software install date

Windows registry date may come as:

```text
20260601
```

Display should show:

```text
01-06-2026
```

### Offline status

Offline detection is based on last heartbeat time.

Default behavior:

```text
Client heartbeat: 5 seconds
Offline detection: about 12 seconds by default
```

If network is unstable, increase offline threshold or client interval.

---

## 22. Troubleshooting

### 22.1 Domain does not resolve

Windows:

```powershell
Resolve-DnsName monitor.sagarkerhalkar.com -Server 1.1.1.1
Resolve-DnsName monitor.sagarkerhalkar.com -Server 8.8.8.8
Resolve-DnsName monitor.sagarkerhalkar.com
```

Flush DNS:

```powershell
ipconfig /flushdns
Clear-DnsClientCache
```

Use IP fallback if needed:

```text
http://156.156.40.51:2278
```

### 22.2 Server health works locally but not from client

Check firewall:

```powershell
New-NetFirewallRule -DisplayName "Sagar System Monitor 2278" -Direction Inbound -Protocol TCP -LocalPort 2278 -Action Allow
```

Check listener:

```powershell
Get-NetTCPConnection -LocalPort 2278
```

Client test:

```powershell
Test-NetConnection SERVER-IP -Port 2278
```

### 22.3 Windows client not updating

Run install/update command again.

Check:

```powershell
Get-ScheduledTask -TaskName "SagarSystemMonitor_Client_2278"
type C:\ProgramData\SagarSystemMonitor\client_error.log
type C:\ProgramData\SagarSystemMonitor\client_status.json
```

### 22.4 Ubuntu client not updating

Check:

```bash
sudo systemctl status sagar-system-monitor-client.service --no-pager
sudo journalctl -u sagar-system-monitor-client.service -n 100 --no-pager
curl -fsSL https://monitor.sagarkerhalkar.com/api/health
```

Restart:

```bash
sudo systemctl restart sagar-system-monitor-client.service
```

### 22.5 Login page opens but cannot login

Test API directly:

```powershell
$body = @{ username="admin"; password="Admin@12345" } | ConvertTo-Json

Invoke-WebRequest "http://127.0.0.1:2278/api/auth/login" `
  -Method POST `
  -ContentType "application/json" `
  -Body $body `
  -UseBasicParsing
```

If API works but UI does not:

```text
- Press Ctrl + Shift + R
- Clear site data
- Check browser console
- Restore public/app.js from backup
```

### 22.6 Day History hangs

Do not load very large heartbeat samples in browser automatically.

Use:

```text
- smaller date range
- CSV export
- database backup before cleanup
```

### 22.7 Mojibake symbols like â† / â€¢

This is frontend encoding/symbol issue.

Use plain ASCII labels:

```text
Down
Up
-
```

Avoid special arrows and bullets in dashboard text.

---

## 23. Safe update method

Use this process every time:

```text
1. Backup current app folder or changed files.
2. Apply patch to test copy first.
3. Run py_compile and node --check.
4. Start server locally.
5. Test /api/health.
6. Test login.
7. Test one Windows client.
8. Test one Ubuntu client.
9. Check dashboard pages.
10. Roll out to more clients in batches.
```

Never change all of these at the same time:

```text
server.py
client_windows.ps1
client_ubuntu.sh
public/app.js
database schema
```

Change one area, test it, then continue.

---

## 24. Release checklist

Before calling a release stable:

```text
[ ] Server starts on port 2278
[ ] /api/health local works
[ ] /api/health public works
[ ] Login works admin/viewer
[ ] Machine Fleet loads
[ ] Machine 360 loads
[ ] Network + VPN loads
[ ] Hardware loads
[ ] Software loads
[ ] USB + Peripherals loads
[ ] Day History loads
[ ] Client Messages loads
[ ] Notifications loads
[ ] Deploy commands copy correctly
[ ] Windows install/update works on one test PC
[ ] Ubuntu install/update works on one test PC
[ ] Windows test command passes
[ ] Ubuntu test command passes
[ ] Backup folder created
[ ] Rollback command tested
```

---

## 25. Important safety notes

- Keep the GitHub repository as source of truth.
- Keep backups before every patch.
- Do not depend on one long chat for project memory.
- Do not fake hardware values.
- Do not run old patches blindly after restoring backups.
- Do not change Windows and Ubuntu clients together unless required.
- Use Deploy page after every client-code change.
- Use staged rollout for many machines.
- For 10,000+ clients, perform real load testing before production.

---

## 26. Quick command summary

### Server start

```powershell
cd D:\SagarSystemHealthMonitor
powershell -ExecutionPolicy Bypass -File .\RUN_SERVER_2278.ps1
```

### Server auto-start

```powershell
cd D:\SagarSystemHealthMonitor
powershell -ExecutionPolicy Bypass -File .\INSTALL_SERVER_AUTOSTART_TASK.ps1
```

### Health test

```powershell
Invoke-WebRequest "http://127.0.0.1:2278/api/health" -UseBasicParsing
Invoke-WebRequest "https://monitor.sagarkerhalkar.com/api/health" -UseBasicParsing
```

### Windows install/update

```powershell
mkdir C:\Temp -Force
Remove-Item C:\Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 -Force -ErrorAction SilentlyContinue
iwr "https://monitor.sagarkerhalkar.com/scripts/BOOTSTRAP_WINDOWS_CLIENT_2278.ps1?strictgpu=v1" -OutFile C:\Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1
powershell -ExecutionPolicy Bypass -File C:\Temp\BOOTSTRAP_WINDOWS_CLIENT_2278.ps1 -ServerUrl "https://monitor.sagarkerhalkar.com" -FileServerUrl "https://monitor.sagarkerhalkar.com" -IntervalSeconds 5
```

### Ubuntu install/update

```bash
PUBLIC_URL="https://monitor.sagarkerhalkar.com"
curl -fsSL "$PUBLIC_URL/scripts/BOOTSTRAP_UBUNTU_CLIENT_2278.sh?restore=v84fixed" -o /tmp/bootstrap.sh
sudo SERVER_URL="$PUBLIC_URL" FILE_SERVER_URL="$PUBLIC_URL" INTERVAL_SECONDS=5 bash /tmp/bootstrap.sh
```

### Backup

```powershell
$App = "D:\SagarSystemHealthMonitor"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Backup = "D:\SagarSystemHealthMonitor_BACKUP_$Stamp"
robocopy $App $Backup /E /XD ".git" "__pycache__" /XF "*.pyc"
```

### Disable offline notification

```powershell
cd D:\SagarSystemHealthMonitor
python - << "PY"
import sqlite3
con = sqlite3.connect("data/monitor.db")
cur = con.cursor()
cur.execute("UPDATE notification_rules SET enabled=0 WHERE id='offline' OR metric='offline_minutes'")
con.commit()
con.close()
print("Offline notification disabled.")
PY
```

---

## 27. Maintainer note

This application should be maintained using this rule:

```text
Preserve working flow.
Patch one issue at a time.
Back up first.
Self-test before rollout.
Do not fake hardware values.
Roll out to clients only after server is stable.
```

