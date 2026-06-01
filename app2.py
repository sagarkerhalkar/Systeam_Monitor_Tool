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

# --- WAN Internet Speed Banner ---
@st.fragment(run_every=10)
def render_internet_speed_banner():
    st.subheader("🌐 Main Gate WAN Internet Status")
    
    if os.path.exists(speed_log_path):
        try:
            with open(speed_log_path, "r") as f:
                speed_data = json.load(f)
            
            isp_name = speed_data.get("isp", "Unknown ISP")
            dl = float(speed_data.get("download", 0))
            ul = float(speed_data.get("upload", 0))
            last_checked = speed_data.get("last_checked", "--:--:--")
            
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Current ISP Provider", isp_name)
            
            if dl < 50: c2.metric("Live Download Speed", f"{dl} Mbps", delta="- CRITICAL LOW", delta_color="inverse")
            elif dl < 100: c2.metric("Live Download Speed", f"{dl} Mbps", delta="- WARNING LOW", delta_color="off")
            else: c2.metric("Live Download Speed", f"{dl} Mbps", delta="🟢 HEALTHY")
                
            if ul < 50: c3.metric("Live Upload Speed", f"{ul} Mbps", delta="- CRITICAL LOW", delta_color="inverse")
            elif ul < 100: c3.metric("Live Upload Speed", f"{ul} Mbps", delta="- WARNING LOW", delta_color="off")
            else: c3.metric("Live Upload Speed", f"{ul} Mbps", delta="🟢 HEALTHY")
                
            c4.metric("Last Speed Check", last_checked)
        except Exception:
            st.info("Waiting for background speed test data to finalize...")
    else:
        st.info("⌛ Server is currently calculating the initial internet speed test in the background. It will load right here automatically inside 60 seconds...")
    st.write("---")

# --- Client Metrics Grid & Summary Cards ---
@st.fragment(run_every=10)
def render_dashboard_metrics():
    rows = []
    total_rx_bytes = 0
    total_tx_bytes = 0

    if os.path.exists(log_dir):
        for filename in os.listdir(log_dir):
            if filename.endswith(".log") and filename != "wan_speed.json":
                filepath = os.path.join(log_dir, filename)
                last_mod = os.path.getmtime(filepath)
                
                seconds_ago = time.time() - last_mod
                status = "🔴 OFFLINE" if seconds_ago > 360 else "🟢 ONLINE"
                last_checkin = datetime.fromtimestamp(last_mod).strftime('%H:%M:%S')
                
                with open(filepath, "r") as f:
                    try:
                        data = json.load(f)
                        adapters = data.get('adapters', [])
                        if isinstance(adapters, dict): adapters = [adapters]
                        ip_list = ", ".join([f"{a.get('IP')}" for a in adapters])
                        
                        raw_rx = int(data.get('net_rx_bytes', 0))
                        raw_tx = int(data.get('net_tx_bytes', 0))
                        
                        total_rx_bytes += raw_rx
                        total_tx_bytes += raw_tx
                        
                        def format_bytes(bytes_value):
                            mb = bytes_value / (1024 * 1024)
                            if mb > 1024: return f"{round(mb / 1024, 2)} GB"
                            return f"{round(mb, 1)} MB"

                        rows.append({
                            "Hostname": data.get('hostname'),
                            "OS": data.get('os'),
                            "Status": status,
                            "CPU %": float(data.get('cpu_load', 0)),
                            "RAM %": float(data.get('ram_used_pct', 0)),
                            "Session Download (RX)": format_bytes(raw_rx),
                            "Session Upload (TX)": format_bytes(raw_tx),
                            "Total Combined Traffic": format_bytes(raw_rx + raw_tx),
                            "IP Addresses": ip_list,
                            "Last Check-in": last_checkin
                        })
                    except Exception:
                        pass

    def format_grand_total(total_bytes):
        gb = total_bytes / (1024 * 1024 * 1024)
        if gb >= 1: return f"{round(gb, 2)} GB"
        return f"{round(total_bytes / (1024 * 1024), 1)} MB"

    if rows:
        df = pd.DataFrame(rows)
        
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("Total Monitored", f"{len(df)} PCs")
        col2.metric("Online Right Now", f"🟢 {len(df[df['Status'] == '🟢 ONLINE'])}")
        col3.metric("Network Total Download", format_grand_total(total_rx_bytes))
        col4.metric("Network Total Upload", format_grand_total(total_tx_bytes))
        col5.metric("Highest CPU Load", f"{df['CPU %'].max()}%")
        
        st.write("## 📊 Multi-VLAN Client Device Matrix")
        
        def highlight_high_usage(s):
            return ['background-color: #ffcccc' if (col == 'CPU %' or col == 'RAM %') and val > 78 else '' for col, val in s.items()]
        
        st.dataframe(df.style.apply(highlight_high_usage, axis=1), use_container_width=True)
    else:
        st.warning("Waiting for data logs from client machines...")

render_internet_speed_banner()
render_dashboard_metrics()