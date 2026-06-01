import streamlit as st
import os
import json
import pandas as pd
import time
from datetime import datetime

st.set_page_config(page_title="Network Monitor Dashboard", layout="wide")
st.title("🖥️ Multi-VLAN System Health & Network Usage Dashboard")

log_dir = "C:\\CustomMonitor\\logs"
speed_log_path = "C:\\CustomMonitor\\logs\\wan_speed.json"
DAILY_USAGE_FILE = "C:\\CustomMonitor\\logs\\daily_network_usage.json"

def format_bytes_value(bytes_value):
    mb = bytes_value / (1024 * 1024)
    if mb > 1024: return f"{round(mb / 1024, 2)} GB"
    return f"{round(mb, 1)} MB"

@st.fragment(run_every=10)
def render_internet_speed_banner():
    st.subheader("🌐 Main Gate WAN Internet Status")
    if os.path.exists(speed_log_path):
        try:
            with open(speed_log_path, "r") as f:
                speed_data = json.load(f)
            dl, ul = float(speed_data.get("download", 0)), float(speed_data.get("upload", 0))
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Current ISP Provider", speed_data.get("isp", "Unknown ISP"))
            c2.metric("Live Download Speed", f"{dl} Mbps", delta="🟢 HEALTHY" if dl >= 50 else "- LOW", delta_color="normal" if dl >= 50 else "inverse")
            c3.metric("Live Upload Speed", f"{ul} Mbps", delta="🟢 HEALTHY" if ul >= 50 else "- LOW", delta_color="normal" if ul >= 50 else "inverse")
            c4.metric("Last Speed Check", speed_data.get("last_checked", "--:--:--"))
        except Exception: pass
    st.write("---")

@st.fragment(run_every=10)
def render_dashboard_metrics():
    rows = []
    
    # 1. Pull historical total day calculations database
    daily_db = {}
    total_day_download = 0
    total_day_upload = 0
    
    if os.path.exists(DAILY_USAGE_FILE):
        try:
            with open(DAILY_USAGE_FILE, "r") as f:
                db_data = json.load(f)
                daily_db = db_data.get("devices", {})
                for h in daily_db:
                    total_day_download += daily_db[h].get("daily_rx_bytes", 0)
                    total_day_upload += daily_db[h].get("daily_tx_bytes", 0)
        except Exception: pass

    # Variables to calculate total current live session usage
    total_current_download = 0
    total_current_upload = 0

    # 2. Extract current log files from active nodes
    if os.path.exists(log_dir):
        for filename in os.listdir(log_dir):
            if filename.endswith(".log") and filename != "wan_speed.json":
                filepath = os.path.join(log_dir, filename)
                last_mod = os.path.getmtime(filepath)
                status = "🔴 OFFLINE" if (time.time() - last_mod) > 360 else "🟢 ONLINE"
                
                with open(filepath, "r") as f:
                    try:
                        data = json.load(f)
                        hostname = data.get('hostname', 'Unknown')
                        raw_rx = int(data.get('net_rx_bytes', 0))
                        raw_tx = int(data.get('net_tx_bytes', 0))
                        
                        # Sum up current usage for actively online devices
                        if status == "🟢 ONLINE":
                            total_current_download += raw_rx
                            total_current_upload += raw_tx
                        
                        # Fetch total day accumulated calculation metrics
                        history = daily_db.get(hostname, {})
                        day_rx = history.get("daily_rx_bytes", 0)
                        day_tx = history.get("daily_tx_bytes", 0)
                        
                        adapters = data.get('adapters', [])
                        if isinstance(adapters, dict): adapters = [adapters]
                        parts = [f"{a.get('Name')}: {a.get('IP')}" for a in adapters if isinstance(a, dict) and a.get('IP')]
                        ip_list = " | ".join(parts) if parts else filename.replace(".log", "")

                        rows.append({
                            "Hostname": hostname,
                            "OS": data.get('os', 'Windows'),
                            "Status": status,
                            "CPU %": float(data.get('cpu_load', 0)),
                            "RAM %": float(data.get('ram_used_pct', 0)),
                            "Current Download (Since Boot)": format_bytes_value(raw_rx),
                            "Total Day Download": format_bytes_value(day_rx),
                            "Current Upload (Since Boot)": format_bytes_value(raw_tx),
                            "Total Day Upload": format_bytes_value(day_tx),
                            "IP Addresses": ip_list,
                            "Last Check-in": datetime.fromtimestamp(last_mod).strftime('%H:%M:%S'),
                            "_raw_mtime": last_mod
                        })
                    except Exception: pass

    if rows:
        # Deduplicate zombie data logs cleanly
        df = pd.DataFrame(rows).sort_values(by="_raw_mtime", ascending=False).drop_duplicates(subset=["Hostname"], keep="first").sort_values(by="Hostname")
        online_df = df[df['Status'] == '🟢 ONLINE']
        
        # ============================================================
        # 📊 8-CARD METRIC METADATA MATRIX PANEL (ROW 1)
        # ============================================================
        r1_c1, r1_c2, r1_c3, r1_c4 = st.columns(4)
        r1_c1.metric("Total Active Nodes", f"{len(df)} PCs")
        r1_c2.metric("Online Right Now", f"🟢 {len(online_df)}")
        
        highest_cpu = online_df['CPU %'].max() if not online_df.empty else df['CPU %'].max()
        highest_ram = online_df['RAM %'].max() if not online_df.empty else df['RAM %'].max()
        
        r1_c3.metric("Highest CPU Load", f"{highest_cpu}%")
        r1_c4.metric("Highest RAM Load", f"{highest_ram}%")
        
        st.write("") # Structural layout separation padding
        
        # ============================================================
        # 📅 NETWORK USAGE COMPARISON MATRIX PANEL (ROW 2)
        # ============================================================
        r2_c1, r2_c2, r2_c3, r2_c4 = st.columns(4)
        r2_c1.metric("Network Current Download", format_bytes_value(total_current_download))
        r2_c2.metric("Total Day Download", format_bytes_value(total_day_download))
        r2_c3.metric("Network Current Upload", format_bytes_value(total_current_upload))
        r2_c4.metric("Total Day Upload", format_bytes_value(total_day_upload))
        
        st.write("---")
        
        # ============================================================
        # 📋 CLIENT DEVICE MATRIX GRID TABLE
        # ============================================================
        st.write("## 📊 Multi-VLAN Client Device Matrix")
        display_cols = [c for c in df.columns if c != "_raw_mtime"]
        
        def highlight_high_usage(s):
            return ['background-color: #ffcccc' if (col == 'CPU %' or col == 'RAM %') and val > 78 and s['Status'] == '🟢 ONLINE' else '' for col, val in s.items()]
            
        st.dataframe(df[display_cols].style.apply(highlight_high_usage, axis=1), use_container_width=True)
    else:
        st.warning("Waiting for data logs from client machines...")

render_internet_speed_banner()
render_dashboard_metrics()