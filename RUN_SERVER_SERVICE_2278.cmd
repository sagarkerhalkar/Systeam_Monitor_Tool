@echo off
cd /d D:\SagarSystemHealthMonitor
"C:\Users\Pc\AppData\Local\Python\pythoncore-3.14-64\python.exe" -u "D:\SagarSystemHealthMonitor\server.py" --host 0.0.0.0 --port 2278 1>>"D:\SagarSystemHealthMonitor\data\server_console.log" 2>>"D:\SagarSystemHealthMonitor\data\server_error.log"
