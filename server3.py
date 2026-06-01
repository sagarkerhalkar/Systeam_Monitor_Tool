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

def send_chat_notification(text_message):
    """Utility wrapper to push strings into Google Chat Space with explicit error tracking."""
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
    """Runs the speed test safely. If the ISP blocks it, the error is isolated."""
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
            if (current_time - alert_state["last_download_2min_alert"] >= 120):  # 120 seconds = 2 Minutes
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
            if (current_time - alert_state["last_upload_2min_alert"] >= 120):  # 120 seconds = 2 Minutes
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
    """Clock thread looking specifically for target daily schedules."""
    print("[SPEEDTEST] Clock scheduler thread online.")
    scheduled_times = ["10:00", "14:00", "16:50", "19:45"]
    
    while True:
        try:
            now = datetime.now()
            time_string = now.strftime("%H:%M")
            
            if time_string in scheduled_times and alert_state["last_scheduled_hour_minute"] != time_string:
                print(f"[SCHEDULE] Match found ({time_string}). Spawning speedtest thread...")
                t = threading.Thread(target=run_speed_test_worker)
                t.start()
                alert_state["last_scheduled_hour_minute"] = time_string
        except Exception as e:
            print(f"[ERROR] Scheduler error: {e}")
            
        time.sleep(1)

def continuous_alert_evaluation_loop():
    """Triggers an alert loop execution every 5 minutes asynchronously."""
    print("[SPEEDTEST] Live diagnostic interval loops active.")
    while True:
        t = threading.Thread(target=run_speed_test_worker)
        t.start()
        time.sleep(300)

def process_client_metrics_async(post_data, client_ip):
    """Processes client logs safely with fallback formatting."""
    try:
        if not post_data or len(post_data.strip()) == 0:
            print("[METRICS WARNING] Received empty network packet.")
            return

        payload = json.loads(post_data)
        hostname = payload.get('hostname', 'Unknown-PC')
        
        cpu = float(payload.get('cpu_load', 0.0))
        ram = float(payload.get('ram_used_pct', 0.0))
        
        adapters = payload.get('adapters', [])
        if isinstance(adapters, dict): adapters = [adapters]
        ip_address = adapters[0].get('IP', client_ip) if adapters else client_ip
        
        print(f"[DATA RECEIVED] Node Metrics -> {hostname} - CPU: {cpu}% | RAM: {ram}%")
        
        if (cpu > 78.0 and ram > 78.0) or (hostname == "CRITICAL-TEST-NODE"):
            print(f"[ALERT CONDITION MET] Firing alert card to Google Chat channel for {hostname}")
            alert_msg = (
                "⚠️ *HIGH RESOURCE UTILIZATION ALERT* ⚠️\n\n"
                f"*Host Machine:* {str(hostname)}\n"
                f"*Network IP:* {str(ip_address)}\n"
                f"*CPU Load:* {str(round(cpu, 1))}%\n"
                f"*RAM Footprint:* {str(round(ram, 1))}%"
            )
            send_chat_notification(alert_msg)
            
    except Exception as e:
        print(f"[FALLBACK] Parsing mismatch handled safely: {e}")

class MetricReceiver(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        
        # Extract raw IP address
        client_ip = self.client_address[0]
        
        # FIX: Strip out IPv6-to-IPv4 mapping prefixes so filenames are valid
        if client_ip == "::1" or client_ip == "::ffff:127.0.0.1": 
            client_ip = "127.0.0.1"
        elif client_ip.startswith("::ffff:"):
            client_ip = client_ip.replace("::ffff:", "")
        
        # Save the telemetry log safely
        log_path = os.path.join("C:\\CustomMonitor\\logs", f"{client_ip}.log")
        with open(log_path, "w") as f:
            f.write(post_data)
            
        # Spin up the background alert check thread
        alert_worker = threading.Thread(target=process_client_metrics_async, args=(post_data, client_ip))
        alert_worker.start()

        self.send_response(200)
        self.end_headers()
if __name__ == "__main__":
    import subprocess
    
    scheduler_thread = threading.Thread(target=monitor_internet_speed_loop, daemon=True)
    scheduler_thread.start()
    
    alert_thread = threading.Thread(target=continuous_alert_evaluation_loop, daemon=True)
    alert_thread.start()
    
    print("[DIAGNOSTIC] Firing initial verification string to Space channel...")
    send_chat_notification("🚨 *SERVER CONFIGURATION UPDATED* 🚨\nNew custom speed rules applied:\n▪️ Warning: < 50 Mbps\n▪️ Critical: < 25 Mbps (Repeats every 2 mins)")
    
    print("[SYSTEM] Starting Streamlit GUI Dashboard process...")
    streamlit_cmd = [
        r"C:\Users\Pc\AppData\Local\Python\pythoncore-3.14-64\python.exe",
        "-m", "streamlit", "run",
        r"C:\CustomMonitor\app.py",
        "--server.port", "8501",
        "--server.headless", "true"
    ]
    subprocess.Popen(streamlit_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    server = HTTPServer(('0.0.0.0', 8080), MetricReceiver)
    print("Receiver system online on port 8080...")
    server.serve_forever()