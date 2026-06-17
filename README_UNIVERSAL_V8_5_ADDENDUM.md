# Universal Server V8.5 Addendum

This update does not replace or delete the existing `main` or `master` branch. Publish it first to a separate branch named `universal-server-v8.5`, test it, then merge only after approval.

## Supported server operating systems

- Windows 10/11 and Windows Server: Scheduled Task plus watchdog
- Linux with systemd: `install_linux_service.sh`
- macOS: launchd using `install_macos_service.sh`
- Docker: `docker compose up -d --build`

## Windows power-cut recovery

Run as Administrator:

```powershell
powershell -ExecutionPolicy Bypass -File .\INSTALL_SERVER_AUTOSTART_TASK.ps1
```

The task runs as SYSTEM at startup, without login. The watchdog checks port 2278 and restarts the server when it is not healthy.

## Incident: server printed Running but health returned Connection Refused

This was caused by conflicting startup methods or stale duplicate server processes. The permanent rule is to use exactly one supervisor. Do not run the manual server and the scheduled task at the same time.

Diagnosis:

```powershell
Get-ScheduledTask -TaskName "SagarSystemMonitor_Server_2278"
Get-NetTCPConnection -LocalPort 2278 -ErrorAction SilentlyContinue
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -match "server\.py|universal_server\.py|SERVER_WATCHDOG_2278" } | Select-Object ProcessId,Name,CommandLine
Get-Content .\data\server_watchdog.log -Tail 100
Get-Content .\data\server_error.log -Tail 100
```

Safe recovery is to stop the task, reboot once if duplicate ownership remains, and let only the configured task start the server.

## Linux

```bash
chmod +x run_server.sh install_linux_service.sh uninstall_linux_service.sh
sudo ./install_linux_service.sh
sudo systemctl status sagar-system-monitor-server.service --no-pager
curl -fsSL http://127.0.0.1:2278/api/health
```

## macOS

```bash
chmod +x run_server.sh install_macos_service.sh
./install_macos_service.sh
launchctl print gui/$(id -u)/com.sagar.systemmonitor.server
curl -fsSL http://127.0.0.1:2278/api/health
```

## Docker

Create `.env`:

```text
CMP_ADMIN_PASSWORD=replace-with-a-strong-password
```

Then:

```bash
docker compose up -d --build
docker compose logs --tail=100 monitor
curl -fsSL http://127.0.0.1:2278/api/health
```

## Commercial release checklist

- Change the default password.
- Use HTTPS and a customer-specific domain.
- Keep credentials and customer databases out of Git.
- Test boot, power-cut recovery, health checks, and one Windows and one Ubuntu client.
- Back up `data/monitor.db`.
- Perform staged rollout and load testing.
