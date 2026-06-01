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
DAILY_USAGE_FILE = "C:\\CustomMonitor\\logs\\daily_network_usage.json"
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

# Thread safety lock for concurrent client data writes
usage_lock = threading.Lock()

def init_daily_usage_store():
    """Ensures the historical database exists for the current date."""
    with usage_lock:
        current_date = datetime.now().strftime("%Y-%m-%d")
        if os.path.exists(DAILY_USAGE_FILE):
            try:
                with open(DAILY_USAGE_FILE, "r") as f:
                    data = json.load(f)
                if data.get("date") == current_date:
                    return
            except Exception:
                pass
        
        # Reset database for a brand-new calendar day
        blank_store = {"date": current_date, "devices": {}}
        os.makedirs(os.path.dirname(DAILY_USAGE_FILE), exist_ok=True)
        with open(DAILY_USAGE_FILE, "w") as f:
            json.dump(blank_store, f, indent=4)

def update_daily_usage(hostname, current_rx, current_tx):
    """Calculates true delta differences and adds to cumulative daily historical logs."""
    init_daily_usage_store()
    with usage_lock:
        try:
            with open(DAILY_USAGE_FILE, "r") as f:
                store = json.load(f)
                
            devices = store.setdefault("devices", {})
            
            if hostname in devices:
                last_rx = devices[hostname].get("last_raw_rx", current_rx)
                last_tx = devices[hostname].get("last_raw_tx", current_tx)
                
                # Compute difference. If machine restarts, the count drops; count delta as 0 for that interval
                delta_rx = current_rx - last_rx if current_rx >= last_rx else 0
                delta_tx = current_tx - last_tx if current_tx >= last_tx else 0
                
                devices[hostname]["daily_rx_bytes"] = devices[hostname].get("daily_rx_bytes", 0) + delta_rx
                devices[hostname]["daily_tx_bytes"] = devices[hostname].get("daily_tx_bytes", 0) + delta_tx
            else:
                # First data reporting interval of the day for this computer
                devices[hostname] = {
                    "daily_rx_bytes": 0,
                    "daily_tx_bytes": 0
                }
                
            # Keep current interface parameters bookmarked for the next evaluation loop
            devices[hostname]["last_raw_rx"] = current_rx
            devices[hostname]["last_raw_tx"] = current_tx
            
            with open(DAILY_USAGE_FILE, "w") as f:
                json.dump(store, f, indent=4)
        except Exception as e:
            print(f"[ACCUMULATOR ERROR] Failed updating daily network database: {e}")

def send_chat_notification(text_message):
    payload = {"text": str(text_message)}
    try:
        req = urllib.request.Request(
            GOOGLE_CHAT_WEBHOOK,
            data=json.dumps(payload).encode('utf-8'),
            headers={
                'Content-Type': 'application/json; charset=UTF-8',
                'User-Agent': 'Mozilla/5.0'
            },
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            print(f"[GOOGLE CHAT SUCCESS] Alert delivered. Status: {response.getcode()}")
    except urllib.error.HTTPError as e:
        print(f"[GOOGLE CHAT API ERROR] Google rejected message! Status: {e.code}")
    except Exception as e:
        print(f"[GOOGLE CHAT NETWORK ERROR] Failed connecting to API: {e}")

def run_speed_test_worker():
    try:
        print("[SPEEDTEST ENGINE] Running active speed verification...")
        st = speedtest.Speedtest()
        try:
            st.get_best_server()
        except Exception as e:
            print(f"[SPEEDTEST SERVER ERROR] Could not fetch nearest server: {e}. Skipping this check.")
            return
            
        download_speed = st.download() / 1_000_000
        upload_speed = st.upload() / 1_000_000
        isp_name = st.config['client']['isp']
        current_time = time.time()
        
        speed_log = {
            "isp": isp_name,
            "download": round(download_speed, 1),
            "upload": round(upload_speed, 1),
            "last_checked": datetime.now().strftime("%H:%M:%S")
        }
        os.makedirs("C:\\CustomMonitor\\logs", exist_ok=True)
        with open("C:\\CustomMonitor\\logs\\wan_speed.json", "w") as sf:
            json.dump(speed_log, sf)
            
        print(f"[SPEEDTEST ENGINE] Complete: {round(download_speed, 1)} Mbps down / {round(upload_speed, 1)} Mbps up")

        # ==================== DOWNLOAD THRESHOLDS ====================
        if download_speed < 25.0:
            alert_state["download_under_50_triggered"] = True
            if (current_time - alert_state["last_download_2min_alert"] >= 120):
                send_chat_notification(f"🚨 *CRITICAL DOWNLOAD DEGRADATION (< 25 Mbps)* 🚨\n⚠️ Download speed has dropped dangerously low!\n▪️ *Current Download:* {round(download_speed, 1)} Mbps\n⏳ Repeats every 2 mins.")
                alert_state["last_download_2min_alert"] = current_time
        elif download_speed < 50.0:
            if not alert_state["download_under_50_triggered"]:
                send_chat_notification(f"⚠️ *DOWNLOAD SPEED WARNING (< 50 Mbps)* ⚠️\n▪️ *Current Download:* {round(download_speed, 1)} Mbps")
                alert_state["download_under_50_triggered"] = True
        else:
            if alert_state["download_under_50_triggered"]:
                send_chat_notification(f"✅ *DOWNLOAD SPEED RECOVERED* ✅\n▪️ *Current Download:* {round(download_speed, 1)} Mbps")
            alert_state["download_under_50_triggered"] = False

        # ==================== UPLOAD THRESHOLDS ====================
        if upload_speed < 25.0:
            alert_state["upload_under_50_triggered"] = True
            if (current_time - alert_state["last_upload_2min_alert"] >= 120):
                send_chat_notification(f"🚨 *CRITICAL UPLOAD DEGRADATION (< 25 Mbps)* 🚨\n⚠️ Upload speed has dropped dangerously low!\n▪️ *Current Upload:* {round(upload_speed, 1)} Mbps\n⏳ Repeats every 2 mins.")
                alert_state["last_upload_2min_alert"] = current_time
        elif upload_speed < 50.0:
            if not alert_state["upload_under_50_triggered"]:
                send_chat_notification(f"⚠️ *UPLOAD SPEED WARNING (< 50 Mbps)* ⚠️\n▪️ *Current Upload:* {round(upload_speed, 1)} Mbps")
                alert_state["upload_under_50_triggered"] = True
        else:
            if alert_state["upload_under_50_triggered"]:
                send_chat_notification(f"✅ *UPLOAD SPEED RECOVERED* ✅\n▪️ *Current Upload:* {round(upload_speed, 1)} Mbps")
            alert_state["upload_under_50_triggered"] = False
            
    except Exception as e:
        print(f"[SPEEDTEST WORKER EXCEPTION] Error bypassed safely: {e}")

def monitor_internet_speed_loop():
    print("[SPEEDTEST] Clock scheduler thread online.")
    scheduled_times = ["10:00", "14:00", "16:50", "19:45"]
    while True:
        try:
            now = datetime.now()
            time_string = now.strftime("%H:%M")
            if time_string in scheduled_times and alert_state["last_scheduled_hour_minute"] != time_string:
                t = threading.Thread(target=run_speed_test_worker)
                t.start()
                alert_state["last_scheduled_hour_minute"] = time_string
        except Exception as e:
            print(f"[ERROR] Scheduler error: {e}")
        time.sleep(1)

def continuous_alert_evaluation_loop():
    print("[SPEEDTEST] Live diagnostic interval loops active.")
    while True:
        t = threading.Thread(target=run_speed_test_worker)
        t.start()
        time.sleep(300)

def process_client_metrics_async(post_data, client_ip):
    """Processes client logs dynamically by converting both dictionary and array structures safely."""
    try:
        if not post_data or len(post_data.strip()) == 0:
            return

        payload = json.loads(post_data)
        hostname = payload.get('hostname', 'Unknown-PC')
        cpu = float(payload.get('cpu_load', 0.0))
        ram = float(payload.get('ram_used_pct', 0.0))
        raw_rx = int(payload.get('net_rx_bytes', 0))
        raw_tx = int(payload.get('net_tx_bytes', 0))
        
        # --- FIXED: Updates historical delta tracking on the server ---
        update_daily_usage(hostname, raw_rx, raw_tx)
        
        # --- SERVER-SIDE SCHEMA NORMALIZATION ENGINE ---
        adapters = payload.get('adapters', [])
        if isinstance(adapters, dict):
            adapters = [adapters]
        elif not isinstance(adapters, list):
            adapters = []
            
        adapter_strings = []
        for a in adapters:
            if isinstance(a, dict):
                name = a.get('Name', 'Port')
                ip = a.get('IP', '')
                if ip:
                    adapter_strings.append(f"{name}: {ip}")
        
        ports_display = ", ".join(adapter_strings) if adapter_strings else client_ip
        print(f"[DATA RECEIVED] Node: {hostname} | CPU: {cpu}% | RAM: {ram}% | Ports: {ports_display}")
        
        if (cpu > 78.0 and ram > 78.0) or (hostname == "CRITICAL-TEST-NODE"):
            print(f"[ALERT CONDITION MET] Firing Google Chat alert card for {hostname}")
            alert_msg = (
                "⚠️ *HIGH RESOURCE UTILIZATION ALERT* ⚠️\n\n"
                f"*Host Machine:* {str(hostname)}\n"
                f"*Detected Network Ports:* {str(ports_display)}\n"
                f"*CPU Load:* {str(round(cpu, 1))}%\n"
                f"*RAM Footprint:* {str(round(ram, 1))}%"
            )
            send_chat_notification(alert_msg)
            
    except Exception as e:
        print(f"[METRICS WORKER ERROR] Failed verification check: {e}")

class MetricReceiver(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        client_ip = self.client_address[0]
        if client_ip == "::1" or client_ip == "::ffff:127.0.0.1": 
            client_ip = "127.0.0.1"
        elif client_ip.startswith("::ffff:"):
            client_ip = client_ip.replace("::ffff:", "")
        
        log_path = os.path.join("C:\\CustomMonitor\\logs", f"{client_ip}.log")
        with open(log_path, "w") as f:
            f.write(post_data)
            
        alert_worker = threading.Thread(target=process_client_metrics_async, args=(post_data, client_ip))
        alert_worker.start()

        self.send_response(200)
        self.end_headers()

if __name__ == "__main__":
    import subprocess
    
    # Initialize the running database file on startup
    init_daily_usage_store()
    
    scheduler_thread = threading.Thread(target=monitor_internet_speed_loop, daemon=True)
    scheduler_thread.start()
    
    alert_thread = threading.Thread(target=continuous_alert_evaluation_loop, daemon=True)
    alert_thread.start()
    
    print("[SYSTEM] Starting Streamlit GUI Dashboard process...")
    streamlit_cmd = [
        r"C:\Users\Pc\AppData\Local\Python\pythoncore-3.14-64\python.exe",
        "-m", "streamlit", "run",
        r"C:\CustomMonitor\app.py",
        "--server.port", "8501",
        "--server.headless", "true",
        "--browser.gatherUsageStats", "false"
    ]
    subprocess.Popen(streamlit_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    server = HTTPServer(('0.0.0.0', 8080), MetricReceiver)
    print("Receiver system online on port 8080...")
    server.serve_forever()