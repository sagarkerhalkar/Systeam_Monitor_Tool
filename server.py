from http.server import BaseHTTPRequestHandler, HTTPServer
import os
import json
import threading
import time
from datetime import datetime
import urllib.request
import subprocess
import speedtest

# ==================== CONFIGURATION ZONE ====================
GOOGLE_CHAT_WEBHOOK = "https://chat.googleapis.com/v1/spaces/AAQAvZo1dyo/messages?key=AIzaSyDdI0hCZtE6vySjMm-WEfRq3CPzqKqqsHI&token=HeNQ3EnYzWnDiBeaZ0UMa76wSfaSzQXUYJ3Ig2UKHs0"
SPEED_LOG_PATH = "C:\\CustomMonitor\\logs\\wan_speed.json"
HISTORY_DIR = "C:\\CustomMonitor\\history"
# ============================================================

alert_state = {
    "download_under_50_triggered": False,
    "last_download_2min_alert": 0,
    "upload_under_50_triggered": False,
    "last_upload_2min_alert": 0,
    "last_scheduled_hour_minute": ""
}

usage_lock = threading.Lock()

def get_current_history_file():
    current_date = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(HISTORY_DIR, f"usage_{current_date}.json")

def init_daily_usage_store():
    with usage_lock:
        history_file = get_current_history_file()
        current_date = datetime.now().strftime("%Y-%m-%d")
        if os.path.exists(history_file):
            try:
                with open(history_file, "r") as f:
                    data = json.load(f)
                if data.get("date") == current_date:
                    return
            except Exception as e:
                print(f"[INIT ERROR] {e}")
        
        blank_store = {"date": current_date, "devices": {}}
        os.makedirs(HISTORY_DIR, exist_ok=True)
        with open(history_file, "w") as f:
            json.dump(blank_store, f, indent=4)

def update_daily_usage(hostname, current_rx, current_tx, hardware_payload=None):
    init_daily_usage_store()
    with usage_lock:
        history_file = get_current_history_file()
        try:
            with open(history_file, "r") as f:
                store = json.load(f)
                
            devices = store.setdefault("devices", {})
            now_ts = time.time()
            clean_host = str(hostname).strip().upper()
            
            if clean_host in devices:
                last_rx = devices[clean_host].get("last_raw_rx", current_rx)
                last_tx = devices[clean_host].get("last_raw_tx", current_tx)

                if current_rx >= last_rx:
                    delta_rx = current_rx - last_rx
                else:
                    delta_rx = current_rx

                if current_tx >= last_tx:
                    delta_tx = current_tx - last_tx
                else:
                    delta_tx = current_tx

                devices[clean_host]["daily_rx_bytes"] = devices[clean_host].get("daily_rx_bytes", 0) + delta_rx
                devices[clean_host]["daily_tx_bytes"] = devices[clean_host].get("daily_tx_bytes", 0) + delta_tx
            else:
                devices[clean_host] = {
                    "daily_rx_bytes": current_rx,
                    "daily_tx_bytes": current_tx,
                    "online_minutes": 0,
                    "offline_minutes": 0
                }
                
            devices[clean_host]["last_raw_rx"] = current_rx
            devices[clean_host]["last_raw_tx"] = current_tx
            devices[clean_host]["last_seen_timestamp"] = now_ts

            if hardware_payload:
                devices[clean_host]["cpu_name"] = hardware_payload.get("cpu_name", "Generic Processor")
                devices[clean_host]["cpu_serial"] = hardware_payload.get("cpu_serial", "N/A")
                devices[clean_host]["ram_total_gb"] = hardware_payload.get("ram_total_gb", 0.0)
                devices[clean_host]["storage"] = hardware_payload.get("storage", [])
                devices[clean_host]["peripherals"] = hardware_payload.get("peripherals", [])
                devices[clean_host]["gpu_primary"] = hardware_payload.get("gpu_primary", "Integrated Graphics")
                devices[clean_host]["gpu_vram_gb"] = hardware_payload.get("gpu_vram_gb", 0.0)
            
            with open(history_file, "w") as f:
                json.dump(store, f, indent=4)
        except Exception as e:
            print(f"[ACCUMULATOR ERROR] Database write failure: {e}")

def timeline_uptime_accumulation_loop():
    while True:
        time.sleep(300)
        history_file = get_current_history_file()
        if not os.path.exists(history_file): continue
        with usage_lock:
            try:
                with open(history_file, "r") as f: store = json.load(f)
                devices = store.get("devices", {})
                now_ts = time.time()
                for hostname, dev_data in devices.items():
                    last_seen = dev_data.get("last_seen_timestamp", 0)
                    if (now_ts - last_seen) <= 450:
                        dev_data["online_minutes"] = dev_data.get("online_minutes", 0) + 5
                    else:
                        dev_data["offline_minutes"] = dev_data.get("offline_minutes", 0) + 5
                with open(history_file, "w") as f: json.dump(store, f, indent=4)
            except Exception as e:
                print(f"[UPTIME LOOP ERROR] {e}")

def send_chat_notification(text_message):
    payload = {"text": str(text_message)}
    try:
        req = urllib.request.Request(
            GOOGLE_CHAT_WEBHOOK,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json; charset=UTF-8', 'User-Agent': 'Mozilla/5.0'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=5): pass
    except Exception as e:
        print(f"[CHAT ALERT ERROR] {e}")

# ================= FIXED: NO MORE FAKE PING LOGIC =================
def run_speed_test_worker():
    isp_title = "Scanning Multi-WAN Routing Engine..."
    try:
        st_engine = speedtest.Speedtest()
        st_engine.get_best_server()
        
        isp_title = st_engine.results.client.get("isp", "Unknown ISP")
        
        # Calculate real link download/upload metrics via speedtest-cli natively
        download_speed = round(st_engine.download() / 1000000, 2)
        upload_speed = round(st_engine.upload() / 1000000, 2)
        
        speed_log = {
            "isp": isp_title,
            "download": download_speed,
            "upload": upload_speed,
            "last_checked": datetime.now().strftime("%H:%M:%S")
        }
    except Exception as e:
        print(f"[SPEED TEST ERROR] Real extraction failed: {e}")
        speed_log = {
            "isp": "Interfaces Disconnected / Timeout",
            "download": 0.0,
            "upload": 0.0,
            "last_checked": datetime.now().strftime("%H:%M:%S")
        }
    
    try:
        os.makedirs(os.path.dirname(SPEED_LOG_PATH), exist_ok=True)
        with open(SPEED_LOG_PATH, "w") as sf: 
            json.dump(speed_log, sf, indent=4)
    except Exception as e:
        print(f"[SPEED TEST FILE WRITE ERROR] {e}")

def monitor_internet_speed_loop():
    while True:
        run_speed_test_worker()
        # Changed to 5 minutes (300 seconds) so real tests don't saturate your local bandwidth network
        time.sleep(300)

class MetricReceiver(BaseHTTPRequestHandler):
    def log_message(self, format, *args): return
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        try:
            payload = json.loads(post_data)
            hostname = payload.get('hostname', 'Unknown-PC').strip().upper()
            
            storage_array = payload.get('storage', [])
            ssd_pct = 0.0
            hdd_pct = 0.0
            for drive in storage_array:
                drive_letter = str(drive.get('DriveLetter', '')).upper().strip()
                dtype = str(drive.get('Type', '')).upper()
                used = float(drive.get('Used_Pct', 0.0))
                
                if drive_letter == "C:":
                    if "SSD" in dtype: ssd_pct = used
                    else: hdd_pct = used
                    break

            payload['ssd_used_pct'] = ssd_pct
            payload['hdd_used_pct'] = hdd_pct

            os.makedirs("C:\\CustomMonitor\\logs", exist_ok=True)
            log_path = os.path.join("C:\\CustomMonitor\\logs", f"{hostname}.log")
            with open(log_path, "w") as f: json.dump(payload, f, indent=4)
            
            raw_rx = int(payload.get('net_rx_bytes', 0))
            raw_tx = int(payload.get('net_tx_bytes', 0))
            
            threading.Thread(target=update_daily_usage, args=(hostname, raw_rx, raw_tx, payload)).start()
        except Exception as e:
            print(f"[RECEIVER POST ERROR] Payload break: {e}")
            
        self.send_response(200)
        self.end_headers()

if __name__ == "__main__":
    init_daily_usage_store()
    threading.Thread(target=timeline_uptime_accumulation_loop, daemon=True).start()
    threading.Thread(target=monitor_internet_speed_loop, daemon=True).start()
    print("Receiver server online on port 8080...")
    HTTPServer(('0.0.0.0', 8080), MetricReceiver).serve_forever()