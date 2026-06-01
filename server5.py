from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import json
import threading
import time
from datetime import datetime
import urllib.request
import speedtest

# ==================== CONFIGURATION ZONE ====================
GOOGLE_CHAT_WEBHOOK = "https://chat.googleapis.com/v1/spaces/AAQAvZo1dyo/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=HeNQ3EnYzWnDiBeaZ0UMa76wSfaSzQXUYJ3Ig2UKHs0"
HISTORY_DIR = "C:\\CustomMonitor\\history"
# ============================================================

alert_state = {
    "download_under_50_triggered": False,
    "download_under_25_triggered": False,
    "last_download_2min_alert": 0,
    
    "upload_under_50_triggered": False,
    "upload_under_25_triggered": False,
    "last_upload_2min_alert": 0,
    
    "last_scheduled_hour_minute": ""
}

usage_lock = threading.Lock()

def get_daily_history_filepath():
    """Generates a unique database file path for the current date."""
    current_date = datetime.now().strftime("%Y-%m-%d")
    os.makedirs(HISTORY_DIR, exist_ok=True)
    return os.path.join(HISTORY_DIR, f"usage_{current_date}.json")

def init_daily_usage_store():
    """Ensures a clean historical database exists for the current calendar day."""
    filepath = get_daily_history_filepath()
    with usage_lock:
        if not os.path.exists(filepath):
            blank_store = {"date": datetime.now().strftime("%Y-%m-%d"), "devices": {}}
            with open(filepath, "w") as f:
                json.dump(blank_store, f, indent=4)

def update_daily_usage(hostname, current_rx, current_tx):
    """Calculates byte deltas and logs active timestamps for timeline monitoring."""
    init_daily_usage_store()
    filepath = get_daily_history_filepath()
    
    with usage_lock:
        try:
            with open(filepath, "r") as f:
                store = json.load(f)
                
            devices = store.setdefault("devices", {})
            now_ts = time.time()
            
            if hostname in devices:
                last_rx = devices[hostname].get("last_raw_rx", current_rx)
                last_tx = devices[hostname].get("last_raw_tx", current_tx)
                
                delta_rx = current_rx - last_rx if current_rx >= last_rx else 0
                delta_tx = current_tx - last_tx if current_tx >= last_tx else 0
                
                devices[hostname]["daily_rx_bytes"] = devices[hostname].get("daily_rx_bytes", 0) + delta_rx
                devices[hostname]["daily_tx_bytes"] = devices[hostname].get("daily_tx_bytes", 0) + delta_tx
            else:
                # First time seeing this workstation today
                devices[hostname] = {
                    "daily_rx_bytes": 0,
                    "daily_tx_bytes": 0,
                    "online_minutes": 0,
                    "offline_minutes": 0
                }
                
            # Update metrics trackers and state markers
            devices[hostname]["last_raw_rx"] = current_rx
            devices[hostname]["last_raw_tx"] = current_tx
            devices[hostname]["last_seen_timestamp"] = now_ts
            
            with open(filepath, "w") as f:
                json.dump(store, f, indent=4)
        except Exception as e:
            print(f"[DATABASE ERROR] Failed updating dynamic daily logs: {e}")

def timeline_uptime_accumulation_loop():
    """Background clock thread running every 5 minutes to accumulate true timeline metrics."""
    print("[TIMELINE ENGINE] Automated Uptime/Downtime background tracker online.")
    while True:
        time.sleep(300) # Run audit cycle every 5 minutes
        filepath = get_daily_history_filepath()
        if not os.path.exists(filepath):
            continue
            
        with usage_lock:
            try:
                with open(filepath, "r") as f:
                    store = json.load(f)
                    
                devices = store.get("devices", {})
                now_ts = time.time()
                
                for hostname, dev_data in devices.items():
                    last_seen = dev_data.get("last_seen_timestamp", 0)
                    
                    # If checked in within the last 6 minutes, add 5 minutes to uptime. Otherwise, it is offline downtime.
                    if (now_ts - last_seen) <= 360:
                        dev_data["online_minutes"] = dev_data.get("online_minutes", 0) + 5
                    else:
                        dev_data["offline_minutes"] = dev_data.get("offline_minutes", 0) + 5
                        
                with open(filepath, "w") as f:
                    json.dump(store, f, indent=4)
            except Exception as e:
                print(f"[TIMELINE ERROR] Audit computation loop failure: {e}")

def send_chat_notification(text_message):
    payload = {"text": str(text_message)}
    try:
        req = urllib.request.Request(
            GOOGLE_CHAT_WEBHOOK,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json; charset=UTF-8', 'User-Agent': 'Mozilla/5.0'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            pass
    except Exception:
        pass

def run_speed_test_worker():
    try:
        print("[SPEEDTEST ENGINE] Running active speed verification...")
        st = speedtest.Speedtest()
        try: st.get_best_server()
        except Exception: return
            
        download_speed = st.download() / 1_000_000
        upload_speed = st.upload() / 1_000_000
        current_time = time.time()
        
        speed_log = {
            "isp": st.config['client']['isp'],
            "download": round(download_speed, 1),
            "upload": round(upload_speed, 1),
            "last_checked": datetime.now().strftime("%H:%M:%S")
        }
        os.makedirs("C:\\CustomMonitor\\logs", exist_ok=True)
        with open("C:\\CustomMonitor\\logs\\wan_speed.json", "w") as sf:
            json.dump(speed_log, sf)

        if download_speed < 25.0:
            alert_state["download_under_50_triggered"] = True
            if (current_time - alert_state["last_download_2min_alert"] >= 120):
                send_chat_notification(f"🚨 *CRITICAL DOWNLOAD DEGRADATION (< 25 Mbps)* 🚨\n⚠️ Speed: {round(download_speed, 1)} Mbps\n⏳ Repeats every 2 mins.")
                alert_state["last_download_2min_alert"] = current_time
        elif download_speed < 50.0:
            if not alert_state["download_under_50_triggered"]:
                send_chat_notification(f"⚠️ *DOWNLOAD SPEED WARNING (< 50 Mbps)* ⚠️\n▪️ Speed: {round(download_speed, 1)} Mbps")
                alert_state["download_under_50_triggered"] = True
        else:
            alert_state["download_under_50_triggered"] = False

        if upload_speed < 25.0:
            alert_state["upload_under_50_triggered"] = True
            if (current_time - alert_state["last_upload_2min_alert"] >= 120):
                send_chat_notification(f"🚨 *CRITICAL UPLOAD DEGRADATION (< 25 Mbps)* 🚨\n⚠️ Speed: {round(upload_speed, 1)} Mbps\n⏳ Repeats every 2 mins.")
                alert_state["last_upload_2min_alert"] = current_time
        elif upload_speed < 50.0:
            if not alert_state["upload_under_50_triggered"]:
                send_chat_notification(f"⚠️ *UPLOAD SPEED WARNING (< 50 Mbps)* ⚠️\n▪️ Speed: {round(upload_speed, 1)} Mbps")
                alert_state["upload_under_50_triggered"] = True
        else:
            alert_state["upload_under_50_triggered"] = False
    except Exception:
        pass

def monitor_internet_speed_loop():
    scheduled_times = ["10:00", "14:00", "16:50", "19:45"]
    while True:
        try:
            time_string = datetime.now().strftime("%H:%M")
            if time_string in scheduled_times and alert_state["last_scheduled_hour_minute"] != time_string:
                t = threading.Thread(target=run_speed_test_worker)
                t.start()
                alert_state["last_scheduled_hour_minute"] = time_string
        except Exception: pass
        time.sleep(1)

def continuous_alert_evaluation_loop():
    while True:
        t = threading.Thread(target=run_speed_test_worker)
        t.start()
        time.sleep(300)

def process_client_metrics_async(post_data, client_ip):
    try:
        if not post_data or len(post_data.strip()) == 0: return
        payload = json.loads(post_data)
        hostname = payload.get('hostname', 'Unknown-PC')
        cpu = float(payload.get('cpu_load', 0.0))
        ram = float(payload.get('ram_used_pct', 0.0))
        raw_rx = int(payload.get('net_rx_bytes', 0))
        raw_tx = int(payload.get('net_tx_bytes', 0))
        
        update_daily_usage(hostname, raw_rx, raw_tx)
        
        adapters = payload.get('adapters', [])
        if isinstance(adapters, dict): adapters = [adapters]
        
        adapter_strings = []
        for a in adapters:
            if isinstance(a, dict) and a.get('IP'):
                adapter_strings.append(f"{a.get('Name')}: {a.get('IP')}")
        
        ports_display = ", ".join(adapter_strings) if adapter_strings else client_ip
        print(f"[DATA RECEIVED] Node: {hostname} | CPU: {cpu}% | RAM: {ram}%")
        
        if (cpu > 78.0 and ram > 78.0) or (hostname == "CRITICAL-TEST-NODE"):
            alert_msg = f"⚠️ *HIGH RESOURCE UTILIZATION ALERT* ⚠️\n\n*Host:* {hostname}\n*CPU:* {round(cpu, 1)}%\n*RAM:* {round(ram, 1)}%"
            send_chat_notification(alert_msg)
    except Exception as e:
        print(f"[ERROR] {e}")

class MetricReceiver(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        client_ip = self.client_address[0]
        if client_ip in ["::1", "::ffff:127.0.0.1"]: client_ip = "127.0.0.1"
        elif client_ip.startswith("::ffff:"): client_ip = client_ip.replace("::ffff:", "")
        
        log_path = os.path.join("C:\\CustomMonitor\\logs", f"{client_ip}.log")
        with open(log_path, "w") as f: f.write(post_data)
            
        threading.Thread(target=process_client_metrics_async, args=(post_data, client_ip)).start()
        self.send_response(200)
        self.end_headers()

if __name__ == "__main__":
    import subprocess
    init_daily_usage_store()
    
    # Start the automated 5-minute timeline sampling loop
    threading.Thread(target=timeline_uptime_accumulation_loop, daemon=True).start()
    
    threading.Thread(target=monitor_internet_speed_loop, daemon=True).start()
    threading.Thread(target=continuous_alert_evaluation_loop, daemon=True).start()
    
    streamlit_cmd = [
        r"C:\Users\Pc\AppData\Local\Python\pythoncore-3.14-64\python.exe", "-m", "streamlit", "run",
        r"C:\CustomMonitor\app.py", "--server.port", "8501", "--server.headless", "true", "--browser.gatherUsageStats", "false"
    ]
    subprocess.Popen(streamlit_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    print("Receiver system online on port 8080...")
    HTTPServer(('0.0.0.0', 8080), MetricReceiver).serve_forever()