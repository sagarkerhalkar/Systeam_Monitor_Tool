import streamlit as st
import os
import json
import pandas as pd
import time
from datetime import datetime, date

st.set_page_config(page_title="Network Monitor Dashboard", layout="wide")
st.title("🖥️ Multi-VLAN System Health & Network Usage Dashboard")

log_dir = "C:\\CustomMonitor\\logs"
speed_log_path = "C:\\CustomMonitor\\logs\\wan_speed.json"
HISTORY_DIR = "C:\\CustomMonitor\\history"

def format_bytes_value(bytes_value):
    mb = bytes_value / (1024 * 1024)
    if mb > 1024: return f"{round(mb / 1024, 2)} GB"
    return f"{round(mb, 1)} MB"

def format_minutes_to_time(total_minutes):
    if total_minutes <= 0: return "0 Mins"
    hours = total_minutes // 60
    mins = total_minutes % 60
    if hours > 0:
        return f"{hours}h {mins}m"
    return f"{mins} Mins"

# --- SIDEBAR FILTER ---
st.sidebar.header("🔍 Historical Filter Controls")
selected_date = st.sidebar.date_input("Select Audit Date", date.today())
is_today = (selected_date == date.today())
date_str = selected_date.strftime("%Y-%m-%d")

@st.fragment(run_every=10)
def render_internet_speed_banner():
    if is_today:
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
    
    # 1. Load history database with strict case-insensitive fallback logic
    daily_db = {}
    total_day_download = 0
    total_day_upload = 0
    
    history_file = os.path.join(HISTORY_DIR, f"usage_{date_str}.json")
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                db_data = json.load(f)
                raw_devices = db_data.get("devices", {})
                # Normalize history data names by removing spaces and forcing uppercase strings
                for k, v in raw_devices.items():
                    daily_db[str(k).strip().upper()] = v
                    total_day_download += v.get("daily_rx_bytes", 0)
                    total_day_upload += v.get("daily_tx_bytes", 0)
        except Exception: pass

    total_current_download = 0
    total_current_upload = 0

    # 2. Extract current logs
    if os.path.exists(log_dir):
        for filename in os.listdir(log_dir):
            if filename.endswith(".log") and filename != "wan_speed.json":
                filepath = os.path.join(log_dir, filename)
                last_mod = os.path.getmtime(filepath)
                
                if is_today:
                    status = "🔴 OFFLINE" if (time.time() - last_mod) > 360 else "🟢 ONLINE"
                else:
                    status = "⌛ ARCHIVED"
                
                with open(filepath, "r") as f:
                    try:
                        data = json.load(f)
                        # Fallback parsing check to find the computer name regardless of capitalization
                        hostname = data.get('hostname', data.get('Hostname', data.get('host', 'Unknown'))).strip()
                        
                        lookup_key = hostname.upper()
                        if not is_today and lookup_key not in daily_db:
                            continue
                            
                        raw_rx = int(data.get('net_rx_bytes', 0))
                        raw_tx = int(data.get('net_tx_bytes', 0))
                        
                        if status == "🟢 ONLINE":
                            total_current_download += raw_rx
                            total_current_upload += raw_tx
                        
                        # Match records using the normalized key name
                        history = daily_db.get(lookup_key, {})
                        day_rx = history.get("daily_rx_bytes", 0)
                        day_tx = history.get("daily_tx_bytes", 0)
                        online_mins = history.get("online_minutes", 0)
                        offline_mins = history.get("offline_minutes", 0)
                        
                        adapters = data.get('adapters', [])
                        if isinstance(adapters, dict): adapters = [adapters]
                        parts = [f"{a.get('Name')}: {a.get('IP')}" for a in adapters if isinstance(a, dict) and a.get('IP')]
                        ip_list = " | ".join(parts) if parts else filename.replace(".log", "")

                        rows.append({
                            "Hostname": hostname,
                            "OS": data.get('os', 'Windows'),
                            "Status": status,
                            "CPU %": float(data.get('cpu_load', 0)) if is_today else 0.0,
                            "RAM %": float(data.get('ram_used_pct', 0)) if is_today else 0.0,
                            "Current Boot Download": format_bytes_value(raw_rx) if is_today else "--",
                            "Total Day Download": format_bytes_value(day_rx),
                            "Current Boot Upload": format_bytes_value(raw_tx) if is_today else "--",
                            "Total Day Upload": format_bytes_value(day_tx),
                            "Time Online (Uptime)": format_minutes_to_time(online_mins),
                            "Time Offline (Downtime)": format_minutes_to_time(offline_mins),
                            "IP Addresses": ip_list,
                            "Last Check-in": datetime.fromtimestamp(last_mod).strftime('%H:%M:%S'),
                            "_raw_mtime": last_mod
                        })
                    except Exception: pass

    st.write(f"## 📅 Summary Matrix Report for Date: **{date_str}**")
    
    if rows:
        df = pd.DataFrame(rows).sort_values(by="_raw_mtime", ascending=False).drop_duplicates(subset=["Hostname"], keep="first").sort_values(by="Hostname")
        online_df = df[df['Status'] == '🟢 ONLINE']
        
        # Display the 8-card grid panels cleanly
        row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
        row1_col1.metric("Total Active Nodes", f"{len(df)} PCs")
        row1_col2.metric("Online Right Now", f"🟢 {len(online_df)}" if is_today else "⌛ ARCHIVED")
        
        highest_cpu = online_df['CPU %'].max() if not online_df.empty else df['CPU %'].max()
        highest_ram = online_df['RAM %'].max() if not online_df.empty else df['RAM %'].max()
        row1_col3.metric("Highest CPU Load", f"{highest_cpu}%" if is_today else "--")
        row1_col4.metric("Highest RAM Load", f"{highest_ram}%" if is_today else "--")
        
        st.write("") 
        
        row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
        row2_col1.metric("Network Current Download", format_bytes_value(total_current_download))
        row2_col2.metric("Total Day Download", format_bytes_value(total_day_download))
        row2_col3.metric("Network Current Upload", format_bytes_value(total_current_upload))
        row2_col4.metric("Total Day Upload", format_bytes_value(total_day_upload))
        
        st.write("---")
        
        st.write("### 📊 Workstation Timeline Data Feed Matrix")
        display_cols = [c for c in df.columns if c != "_raw_mtime"]
        if not is_today:
            display_cols = [c for c in display_cols if "Current" not in c and "Check-in" not in c and "%" not in c]
            
        def highlight_high_usage(s):
            if not is_today: return [''] * len(s)
            return ['background-color: #ffcccc' if (col == 'CPU %' or col == 'RAM %') and val > 78 and s['Status'] == '🟢 ONLINE' else '' for col, val in s.items()]
            
        st.dataframe(df[display_cols].style.apply(highlight_high_usage, axis=1), use_container_width=True)
    else:
        st.warning(f"No log data found for date: {date_str}")

render_internet_speed_banner()
render_dashboard_metrics()