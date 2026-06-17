# Sagar Kerhalkar System Health Monitor Tool

**Version target:** V8.5 Universal Server / port `2278`  
**Windows server folder:** `D:\SagarSystemHealthMonitor`  
**Linux server folder:** `/opt/sagar-system-monitor`  
**Default public URL:** `https://monitor.sagarkerhalkar.com`  
**Local dashboard:** `http://127.0.0.1:2278` or `http://SERVER-IP:2278`  
**Server support:** Windows, Linux, macOS, Docker, Kubernetes, AWS, GCP, Azure  
**Monitoring clients:** Windows and Ubuntu/Linux  
**Client heartbeat:** 5 seconds by default  
**Dashboard refresh:** 5 seconds by default

This application is a cross-platform monitoring platform. The server/dashboard can run on Windows, Linux, macOS, Docker, Kubernetes, AWS, Google Cloud, or Microsoft Azure. Monitoring agents collect Windows and Ubuntu/Linux machine data for classrooms, labs, offices, cyber cafes, campus computer labs, and multi-LAN/VLAN environments.

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
├─ universal_server.py
├─ SERVER_WATCHDOG_2278.ps1
├─ run_server.sh
├─ install_linux_service.sh
├─ uninstall_linux_service.sh
├─ install_macos_service.sh
├─ Dockerfile
├─ docker-compose.yml
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
OS: Windows 10/11, Windows Server, modern Linux, or macOS
Container: Docker or Kubernetes supported
Cloud: AWS, Google Cloud, and Microsoft Azure supported
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


## 2A. Universal server architecture and operating-system choice

The monitoring server is Python standard-library based. The same application logic can run on multiple operating systems, but the automatic-start method is different for each platform.

| Server platform | Recommended supervisor | Starts after power recovery | Persistent storage |
|---|---|---:|---|
| Windows 10/11 or Windows Server | Scheduled Task plus watchdog | Yes | NTFS local disk |
| Ubuntu/Debian/RHEL-family Linux | systemd | Yes | ext4/xfs local disk |
| macOS | launchd | Yes | APFS local disk |
| Docker | Docker restart policy | Yes | bind mount or named volume |
| Kubernetes | Deployment with one replica and PVC | Yes | PersistentVolumeClaim |

> Use exactly one supervisor on a server. Do not run the Windows task, a manual Python process, Docker, and another watchdog at the same time.

### SQLite limitation

The current build stores runtime data in `data/monitor.db`. While SQLite is used:

```text
Kubernetes replicas: 1
Deployment strategy: Recreate
Docker application containers: 1
ECS/Fargate desired tasks: 1
Horizontal autoscaling: disabled
Persistent data volume: mandatory
```

Before running multiple server replicas, migrate the database layer to PostgreSQL or another shared production database.

### Universal server environment variables

```text
CMP_HOST=0.0.0.0
CMP_PORT=2278
CMP_ADMIN_PASSWORD=use-a-strong-customer-specific-password
PYTHON_BIN=python3
```

Never commit the real password, `.env`, tunnel token, cloud key, customer database, or backup file to GitHub.

---

## 2B. Universal manual start

### Windows

```powershell
cd D:\SagarSystemHealthMonitor
python -m py_compile .\server.py .\universal_server.py
python -u .\universal_server.py --host 0.0.0.0 --port 2278
```

### Linux or macOS

```bash
cd /opt/sagar-system-monitor
python3 -m py_compile server.py universal_server.py
chmod +x run_server.sh
./run_server.sh
```

Health check:

```bash
curl -fsSL http://127.0.0.1:2278/api/health
```

Expected universal health fields:

```json
{
  "ok": true,
  "version": "8.5.0",
  "runtime": "universal-supervisor"
}
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


## 4A. Windows permanent background watchdog

Use this method when the server must start automatically after restart or power cut and must recover if Python stops responding.

Run PowerShell as Administrator:

```powershell
cd D:\SagarSystemHealthMonitor
powershell -ExecutionPolicy Bypass -File .\INSTALL_SERVER_AUTOSTART_TASK.ps1
```

The task must be named:

```text
SagarSystemMonitor_Server_2278
```

Verify:

```powershell
Get-ScheduledTask -TaskName "SagarSystemMonitor_Server_2278"
Get-ScheduledTaskInfo -TaskName "SagarSystemMonitor_Server_2278"
Get-NetTCPConnection -LocalPort 2278 -State Listen
curl.exe --noproxy "*" http://127.0.0.1:2278/api/health
Get-Content .\data\server_watchdog.log -Tail 100
Get-Content .\data\server_error.log -Tail 100
```

Important Windows production recommendation:

```text
Install Python for all users or place a dedicated Python runtime in a stable machine-wide folder.
Do not depend only on a per-user Python path when the scheduled task runs under SYSTEM.
```

---

## 4B. Linux permanent systemd service

Recommended Linux server folder:

```text
/opt/sagar-system-monitor
```

Ubuntu/Debian prerequisites:

```bash
sudo apt update
sudo apt install -y python3 curl git ca-certificates
```

Copy or clone the complete tested application, then:

```bash
cd /opt/sagar-system-monitor
python3 -m py_compile server.py universal_server.py
chmod +x run_server.sh install_linux_service.sh uninstall_linux_service.sh
sudo ./install_linux_service.sh
```

Verify:

```bash
sudo systemctl is-enabled sagar-system-monitor-server.service
sudo systemctl is-active sagar-system-monitor-server.service
sudo systemctl status sagar-system-monitor-server.service --no-pager
sudo journalctl -u sagar-system-monitor-server.service -n 100 --no-pager
sudo ss -lntp | grep 2278
curl -fsSL http://127.0.0.1:2278/api/health
```

Restart:

```bash
sudo systemctl restart sagar-system-monitor-server.service
```

Uninstall:

```bash
sudo ./uninstall_linux_service.sh
```

Linux firewall using UFW:

```bash
sudo ufw allow 2278/tcp
sudo ufw status
```

Linux firewall using firewalld:

```bash
sudo firewall-cmd --permanent --add-port=2278/tcp
sudo firewall-cmd --reload
```

---

## 4C. macOS launchd service

macOS is suitable for development, demonstrations, and smaller installations. Windows Server or Linux is preferred for a commercial always-on server.

```bash
python3 --version
python3 -m py_compile server.py universal_server.py
chmod +x run_server.sh install_macos_service.sh
./install_macos_service.sh
```

Verify:

```bash
launchctl print gui/$(id -u)/com.sagar.systemmonitor.server
curl -fsSL http://127.0.0.1:2278/api/health
lsof -nP -iTCP:2278 -sTCP:LISTEN
cat data/server_console.log
cat data/server_error.log
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


### 22.8 Server printed “running” but health returned connection refused

This exact failure can occur when an old server process, a manual Python process, and an automatic scheduled task overlap.

Typical symptoms:

```text
The console prints: running on http://0.0.0.0:2278
A listener appears briefly
Invoke-RestMethod and curl return connection refused
An old PID still shows Established connections
More than one Python/server process exists
```

Windows diagnosis:

```powershell
Get-ScheduledTask -TaskName "SagarSystemMonitor_Server_2278" -ErrorAction SilentlyContinue
Get-ScheduledTaskInfo -TaskName "SagarSystemMonitor_Server_2278" -ErrorAction SilentlyContinue

Get-NetTCPConnection -LocalPort 2278 -ErrorAction SilentlyContinue |
  Select-Object LocalAddress,LocalPort,State,OwningProcess

Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -match "server\.py|universal_server\.py|SERVER_WATCHDOG_2278" } |
  Select-Object ProcessId,Name,ExecutablePath,CommandLine

Get-Content D:\SagarSystemHealthMonitor\data\server_watchdog.log -Tail 100 -ErrorAction SilentlyContinue
Get-Content D:\SagarSystemHealthMonitor\data\server_console.log -Tail 100 -ErrorAction SilentlyContinue
Get-Content D:\SagarSystemHealthMonitor\data\server_error.log -Tail 100 -ErrorAction SilentlyContinue
```

Recovery rule:

```text
1. Stop the configured monitor supervisor.
2. Identify only the processes that belong to this application.
3. Stop confirmed duplicate monitor processes.
4. Confirm port 2278 is free.
5. Start exactly one supervisor.
6. Wait for /api/health before testing the domain or clients.
```

Do not start another manual `server.py` after the watchdog task is installed.

### 22.9 Scheduled task says Running but no TCP listener exists

Check:

```powershell
Get-ScheduledTaskInfo -TaskName "SagarSystemMonitor_Server_2278"
python --version
Test-Path D:\SagarSystemHealthMonitor\universal_server.py
Get-Content D:\SagarSystemHealthMonitor\data\server_watchdog.log -Tail 100
Get-Content D:\SagarSystemHealthMonitor\data\server_error.log -Tail 100
```

Common causes:

```text
Python executable changed or was removed
Python was installed only for one user but task runs as SYSTEM
application folder was moved
watchdog points to the wrong runner
port is occupied
antivirus quarantined a script
SYSTEM cannot write to data directory
```

### 22.10 Linux service fails after reboot

```bash
sudo systemctl status sagar-system-monitor-server.service --no-pager
sudo journalctl -u sagar-system-monitor-server.service -n 200 --no-pager
sudo systemctl cat sagar-system-monitor-server.service
command -v python3
ls -la /opt/sagar-system-monitor
namei -l /opt/sagar-system-monitor/data
```

### 22.11 Docker container continuously restarts

```bash
docker compose ps
docker compose logs --tail=300 monitor
docker inspect sagar-system-monitor --format '{{json .State.Health}}'
ls -ld data public scripts
```

Common causes:

```text
CMP_ADMIN_PASSWORD missing from .env
data folder not writable by container user
port already mapped by another process
public/scripts folder missing
database is read-only or corrupt
```

### 22.12 Kubernetes pod is CrashLoopBackOff or PVC is Pending

```bash
kubectl -n sagar-monitor get pods,pvc,svc,ingress
kubectl -n sagar-monitor describe pod -l app=sagar-monitor
kubectl -n sagar-monitor logs -l app=sagar-monitor --previous --tail=300
kubectl -n sagar-monitor get events --sort-by=.lastTimestamp
```

Check image-pull access, secret existence, StorageClass/PVC binding, volume ownership, health-probe port/path, and that only one replica uses the SQLite data volume.

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

---

## 28. Kubernetes complete implementation

### 28.1 Build and publish the container

Example using GitHub Container Registry:

```bash
docker build -t ghcr.io/YOUR_GITHUB_USERNAME/sagar-system-monitor:8.5.0 .
docker login ghcr.io
docker push ghcr.io/YOUR_GITHUB_USERNAME/sagar-system-monitor:8.5.0
```

### 28.2 Kubernetes manifest

Save as `kubernetes/sagar-monitor.yaml` and replace the image and password before applying.

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: sagar-monitor
---
apiVersion: v1
kind: Secret
metadata:
  name: sagar-monitor-secret
  namespace: sagar-monitor
type: Opaque
stringData:
  CMP_ADMIN_PASSWORD: "CHANGE-ME-BEFORE-APPLY"
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: sagar-monitor-data
  namespace: sagar-monitor
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 20Gi
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: sagar-monitor
  namespace: sagar-monitor
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: sagar-monitor
  template:
    metadata:
      labels:
        app: sagar-monitor
    spec:
      terminationGracePeriodSeconds: 30
      securityContext:
        runAsNonRoot: true
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
      containers:
        - name: monitor
          image: ghcr.io/YOUR_GITHUB_USERNAME/sagar-system-monitor:8.5.0
          imagePullPolicy: IfNotPresent
          ports:
            - name: http
              containerPort: 2278
          env:
            - name: CMP_HOST
              value: "0.0.0.0"
            - name: CMP_PORT
              value: "2278"
            - name: CMP_ADMIN_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: sagar-monitor-secret
                  key: CMP_ADMIN_PASSWORD
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "2"
              memory: 2Gi
          startupProbe:
            httpGet:
              path: /api/health
              port: http
            periodSeconds: 5
            failureThreshold: 30
          readinessProbe:
            httpGet:
              path: /api/health
              port: http
            initialDelaySeconds: 5
            periodSeconds: 10
            timeoutSeconds: 3
            failureThreshold: 3
          livenessProbe:
            httpGet:
              path: /api/health
              port: http
            initialDelaySeconds: 20
            periodSeconds: 20
            timeoutSeconds: 5
            failureThreshold: 3
          volumeMounts:
            - name: data
              mountPath: /app/data
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop:
                - ALL
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: sagar-monitor-data
---
apiVersion: v1
kind: Service
metadata:
  name: sagar-monitor
  namespace: sagar-monitor
spec:
  selector:
    app: sagar-monitor
  ports:
    - name: http
      port: 80
      targetPort: 2278
  type: ClusterIP
```

Apply and test:

```bash
kubectl apply -f kubernetes/sagar-monitor.yaml
kubectl -n sagar-monitor rollout status deployment/sagar-monitor
kubectl -n sagar-monitor get pods,pvc,svc
kubectl -n sagar-monitor logs deployment/sagar-monitor --tail=100
kubectl -n sagar-monitor port-forward service/sagar-monitor 2278:80
curl -fsSL http://127.0.0.1:2278/api/health
```

### 28.3 Kubernetes Ingress example

An Ingress controller and TLS secret must already exist.

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: sagar-monitor
  namespace: sagar-monitor
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "20m"
spec:
  ingressClassName: nginx
  tls:
    - hosts:
        - monitor.example.com
      secretName: monitor-example-tls
  rules:
    - host: monitor.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: sagar-monitor
                port:
                  number: 80
```

### 28.4 Kubernetes update and rollback

```bash
kubectl -n sagar-monitor set image deployment/sagar-monitor monitor=ghcr.io/YOUR_GITHUB_USERNAME/sagar-system-monitor:8.5.1
kubectl -n sagar-monitor rollout status deployment/sagar-monitor
kubectl -n sagar-monitor rollout history deployment/sagar-monitor
kubectl -n sagar-monitor rollout undo deployment/sagar-monitor
```

### 28.5 Kubernetes backup

For the current SQLite edition, use a maintenance window and a disk/CSI snapshot:

```bash
kubectl -n sagar-monitor scale deployment/sagar-monitor --replicas=0
# Create the cloud-provider or CSI VolumeSnapshot here.
kubectl -n sagar-monitor scale deployment/sagar-monitor --replicas=1
```

Verify health and client heartbeat after the snapshot.

---

## 29. AWS deployment

### 29.1 Recommended current option: EC2 Linux plus Docker Compose

Suggested starting design:

```text
EC2: Ubuntu 24.04 LTS or Amazon Linux
Size: t3.medium or larger for a small/medium installation
Storage: encrypted 30-100 GB gp3 EBS
IP: Elastic IP when a stable direct endpoint is required
Security Group:
  SSH 22 from administrator CIDR only
  HTTPS 443 from required users/networks
  HTTP 80 only when needed
  TCP 2278 only from private LAN/VPN or restricted sources
```

Install Docker on Ubuntu EC2:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker
```

Deploy:

```bash
git clone --branch universal-server-v8.5 https://github.com/sagarkerhalkar/Systeam_Monitor_Tool.git
cd Systeam_Monitor_Tool
cp .env.example .env
nano .env
docker compose up -d --build
curl -fsSL http://127.0.0.1:2278/api/health
```

Use EBS snapshots and an encrypted off-instance copy of `data/monitor.db`. Test restoration on another instance.

### 29.2 AWS EC2 Windows Server

1. Create a Windows Server instance.
2. Restrict RDP to administrator IP ranges.
3. Attach an encrypted EBS data volume.
4. Install Python for all users.
5. Copy the application to `D:\SagarSystemHealthMonitor`.
6. Install the Windows watchdog task.
7. Open only required Security Group and Windows Firewall ports.
8. Test reboot and power recovery.

### 29.3 AWS ECS Fargate

The current SQLite build requires:

```text
Desired tasks: 1
Persistent /app/data: EFS
Health path: /api/health
Container port: 2278
Public entry: Application Load Balancer HTTPS 443
Password storage: Secrets Manager or Parameter Store
```

Test SQLite locking on EFS before commercial use. Do not run multiple tasks against the same SQLite file. Migrate to PostgreSQL before horizontal scaling.

### 29.4 AWS EKS

1. Create EKS and a managed node group.
2. Configure the EBS CSI driver.
3. Push the image to ECR.
4. Apply the Kubernetes manifest.
5. Confirm the PVC binds to an EBS-backed StorageClass.
6. Keep one replica and Recreate strategy.
7. Use AWS Load Balancer Controller or another Ingress with TLS.
8. Configure EBS snapshots and database backups.

ECR example:

```bash
aws ecr create-repository --repository-name sagar-system-monitor
aws ecr get-login-password --region YOUR_REGION | docker login --username AWS --password-stdin YOUR_ACCOUNT.dkr.ecr.YOUR_REGION.amazonaws.com
docker build -t sagar-system-monitor:8.5.0 .
docker tag sagar-system-monitor:8.5.0 YOUR_ACCOUNT.dkr.ecr.YOUR_REGION.amazonaws.com/sagar-system-monitor:8.5.0
docker push YOUR_ACCOUNT.dkr.ecr.YOUR_REGION.amazonaws.com/sagar-system-monitor:8.5.0
```

AWS troubleshooting:

```bash
curl -fsSL http://127.0.0.1:2278/api/health
docker compose logs --tail=200 monitor
kubectl -n sagar-monitor get events --sort-by=.lastTimestamp
```

Check Security Group, NACL, route table, subnet, load-balancer target health, EBS/EFS mount, IAM, DNS, and certificate.

---

## 30. Google Cloud deployment

### 30.1 Recommended current option: Compute Engine plus Docker Compose

Suggested design:

```text
Image: Ubuntu 24.04 LTS
Machine: e2-medium or larger
Disk: 30-100 GB balanced Persistent Disk
IP: reserved static IP when direct DNS is required
Firewall:
  SSH from administrator IP only
  HTTPS from required users/networks
  TCP 2278 private or restricted only
```

Deploy:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker
git clone --branch universal-server-v8.5 https://github.com/sagarkerhalkar/Systeam_Monitor_Tool.git
cd Systeam_Monitor_Tool
cp .env.example .env
nano .env
docker compose up -d --build
curl -fsSL http://127.0.0.1:2278/api/health
```

### 30.2 Google Cloud Run

Cloud Run is not recommended for the current SQLite build because container-local storage is not a durable database strategy.

Use Cloud Run only after:

```text
SQLite is migrated to Cloud SQL PostgreSQL
sessions/shared state are externalized
container becomes stateless
backups/exports use durable object storage
concurrency and timeout behavior are tested
```

### 30.3 Google Kubernetes Engine

1. Create a GKE cluster.
2. Push the image to Artifact Registry.
3. Apply the Kubernetes manifest.
4. Use a Persistent Disk StorageClass.
5. Keep one replica while using SQLite.
6. Use GKE Ingress/Gateway or another Ingress with TLS.
7. Configure disk snapshots and database backups.

Artifact Registry example:

```bash
gcloud artifacts repositories create sagar-monitor --repository-format=docker --location=YOUR_REGION
gcloud auth configure-docker YOUR_REGION-docker.pkg.dev
docker build -t YOUR_REGION-docker.pkg.dev/YOUR_PROJECT/sagar-monitor/server:8.5.0 .
docker push YOUR_REGION-docker.pkg.dev/YOUR_PROJECT/sagar-monitor/server:8.5.0
```

GCP troubleshooting:

```bash
gcloud compute instances list
gcloud compute firewall-rules list
docker compose logs --tail=200 monitor
kubectl -n sagar-monitor get pods,pvc,svc,ingress
kubectl -n sagar-monitor get events --sort-by=.lastTimestamp
```

Check VPC firewall, network tags, external IP, load-balancer health, Persistent Disk/PVC, IAM/Workload Identity, DNS, and TLS.

---

## 31. Microsoft Azure deployment

### 31.1 Recommended current option: Azure Linux VM plus Docker Compose

Suggested design:

```text
Image: Ubuntu Server 24.04 LTS
Size: Standard_B2s or larger
Disk: encrypted managed SSD
IP: static public IP when direct DNS is needed
NSG:
  SSH from administrator IP only
  HTTPS from required users/networks
  TCP 2278 only from private/restricted sources
```

Deploy:

```bash
sudo apt update
sudo apt install -y ca-certificates curl git
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
newgrp docker
git clone --branch universal-server-v8.5 https://github.com/sagarkerhalkar/Systeam_Monitor_Tool.git
cd Systeam_Monitor_Tool
cp .env.example .env
nano .env
docker compose up -d --build
curl -fsSL http://127.0.0.1:2278/api/health
```

### 31.2 Azure Windows VM

1. Create Windows Server VM.
2. Restrict RDP to administrator IP.
3. Attach a managed data disk.
4. Install Python for all users.
5. Copy application to `D:\SagarSystemHealthMonitor`.
6. Install the watchdog scheduled task.
7. Configure NSG and Windows Firewall.
8. Test restart and power recovery.

### 31.3 Azure Container Apps

For SQLite:

```text
minimum replicas: 1
maximum replicas: 1
persistent Azure Files mount: required
CMP_ADMIN_PASSWORD stored as a secret
HTTPS ingress enabled
health path: /api/health
```

Validate SQLite locking on shared storage. Prefer Azure VM, AKS with Azure Disk, or PostgreSQL migration for commercial scale.

### 31.4 Azure Kubernetes Service

1. Create AKS.
2. Push image to Azure Container Registry.
3. Attach ACR to AKS or configure image pull access.
4. Apply the Kubernetes manifest.
5. Confirm PVC uses Azure Disk CSI.
6. Keep one replica and Recreate strategy.
7. Configure Ingress and TLS.
8. Configure managed-disk snapshots and database backups.

ACR example:

```bash
az acr create --resource-group YOUR_RG --name YOUR_ACR --sku Basic
az acr login --name YOUR_ACR
docker build -t YOUR_ACR.azurecr.io/sagar-system-monitor:8.5.0 .
docker push YOUR_ACR.azurecr.io/sagar-system-monitor:8.5.0
```

Azure troubleshooting:

```bash
az vm list -d -o table
az network nsg rule list --resource-group YOUR_RG --nsg-name YOUR_NSG -o table
docker compose logs --tail=200 monitor
kubectl -n sagar-monitor get pods,pvc,svc,ingress
kubectl -n sagar-monitor get events --sort-by=.lastTimestamp
```

Check NSG, route, public IP, load-balancer probe, managed identity, ACR access, Azure Disk PVC, DNS, and certificate.

---

## 32. Move the application to another server or customer

### Step 1: Record current configuration

```text
old server IP/domain
new server IP/domain
application folder
client count
heartbeat interval
database size
tunnel/reverse-proxy configuration
backup location
rollback owner and window
```

### Step 2: Create full and database backups

Use the SQLite backup API and a full application archive.

### Step 3: Install the new server without changing production DNS

Test the new server by IP or a temporary hostname.

### Step 4: Validate all functions

```text
health
login
Machine Fleet
Machine 360
hardware
software
USB
network/VPN
history
notifications
messages
Deploy page
one Windows client
one Ubuntu client
```

### Step 5: Roll out clients in stages

```text
1 Windows + 1 Ubuntu
10 test machines
one lab/VLAN
full customer site
```

### Step 6: Change DNS/tunnel and retain rollback

Do not delete or overwrite the old server until new heartbeats, login, exports, and backups are confirmed.

---

## 33. Cloud and Kubernetes production security

```text
Use HTTPS only for public access.
Store passwords in cloud secret managers or Kubernetes Secrets managed securely.
Restrict SSH/RDP to administrator CIDRs.
Do not expose port 2278 publicly when a load balancer/reverse proxy is available.
Encrypt disks, snapshots, and backups.
Enable cloud audit logs.
Use least-privilege IAM.
Rotate credentials and tunnel tokens.
Protect the administrator dashboard with an identity-aware access layer where possible.
Run vulnerability and secret scans in CI.
Keep customer data separated by customer/environment.
```

---

## 34. Official platform references

Cloud platforms and managed services change. Verify implementation against the current official documentation:

```text
AWS EC2:
https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/EC2_GetStarted.html

AWS ECS Fargate:
https://docs.aws.amazon.com/AmazonECS/latest/developerguide/getting-started-fargate.html

AWS EKS:
https://docs.aws.amazon.com/eks/latest/userguide/getting-started.html

Google Compute Engine:
https://cloud.google.com/compute/docs/instances/create-start-instance

Google Cloud Run:
https://cloud.google.com/run/docs/deploying

Google Kubernetes Engine:
https://cloud.google.com/kubernetes-engine/docs/deploy-app-cluster

Azure Virtual Machines:
https://learn.microsoft.com/azure/virtual-machines/linux/quick-create-cli

Azure Container Apps:
https://learn.microsoft.com/azure/container-apps/get-started

Azure Kubernetes Service:
https://learn.microsoft.com/azure/aks/learn/quick-kubernetes-deploy-cli

Kubernetes Deployments:
https://kubernetes.io/docs/concepts/workloads/controllers/deployment/

Kubernetes Services:
https://kubernetes.io/docs/concepts/services-networking/service/

Kubernetes Persistent Volumes:
https://kubernetes.io/docs/concepts/storage/persistent-volumes/

Kubernetes probes:
https://kubernetes.io/docs/concepts/workloads/pods/probes/
```

