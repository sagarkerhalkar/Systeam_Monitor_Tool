Sagar Kerhalkar System Health Monitor Tool V8.4

Run server:
cd C:\Users\Pc\Downloads\Sagar_Kerhalkar_System_Monitor_Tool_V8_4\SagarMonitor_V8_4
powershell -ExecutionPolicy Bypass -File .\RUN_SERVER_2278.ps1

Default login:
Username: admin
Password: Admin@12345

Client live timing:
Windows/Ubuntu heartbeat: 5 seconds
Dashboard polling: 5 seconds
Offline detection: about 12 seconds by default to avoid false offline from one missed heartbeat.

Downloads are admin-only. Viewer users can see data but cannot download.

Use Deploy page after every client-code change.
Press Ctrl + F5 after updating server UI.

PUBLIC FIXED DOMAIN + AUTOSTART
Read PUBLIC_FIXED_DOMAIN_SETUP_README.txt
Main script:
  powershell -ExecutionPolicy Bypass -File .\INSTALL_PUBLIC_DOMAIN_AND_AUTOSTART.ps1 -DuckDomain YOURNAME -DuckToken YOURTOKEN -Port 2278
