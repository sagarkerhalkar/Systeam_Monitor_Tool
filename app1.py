import streamlit as st
import os
import json
import pandas as pd
import time
from datetime import datetime

st.set_page_config(page_title="Network Monitor Dashboard", layout="wide")
st.title("🖥️ Multi-VLAN System Health & Network Usage Dashboard")

log_dir = "C:\\CustomMonitor\\logs"
rows = []

# Read files dynamically
if os.path.exists(log_dir):
    for filename in os.listdir(log_dir):
        if filename.endswith(".log"):
            filepath = os.path.join(log_dir, filename)
            last_mod = os.path.getmtime(filepath)
            
            # Highlight machines that haven't updated in over 6 minutes (360 seconds)
            seconds_ago = time.time() - last_mod
            status = "🔴 OFFLINE" if seconds_ago > 360 else "🟢 ONLINE"
            
            last_checkin = datetime.fromtimestamp(last_mod).strftime('%H:%M:%S')
            
            with open(filepath, "r") as f:
                try:
                    data = json.load(f)
                    adapters = data.get('adapters', [])
                    if isinstance(adapters, dict): adapters = [adapters]
                    ip_list = ", ".join([f"{a.get('IP')}" for a in adapters])
                    
                    rows.append({
                        "Hostname": data.get('hostname'),
                        "OS": data.get('os'),
                        "Status": status,
                        "CPU %": float(data.get('cpu_load', 0)),
                        "RAM %": float(data.get('ram_used_pct', 0)),
                        "Data RX (MB)": round(int(data.get('net_rx_bytes', 0)) / (1024 * 1024), 1),
                        "Data TX (MB)": round(int(data.get('net_tx_bytes', 0)) / (1024 * 1024), 1),
                        "IP Addresses": ip_list,
                        "Last Update": last_checkin
                    })
                except Exception:
                    pass

if rows:
    df = pd.DataFrame(rows)
    
    # Quick Stats Widgets
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Monitored Machines", len(df))
    col2.metric("Online Right Now", len(df[df['Status'] == "🟢 ONLINE"]))
    col3.metric("Highest CPU Load", f"{df['CPU %'].max()}% ({df.loc[df['CPU %'].idxmax(), 'Hostname']})")
    col4.metric("Total Data Down", f"{round(df['Data RX (MB)'].sum() / 1024, 2)} GB")
    
    st.write("---")
    
    st.subheader("Live Device Matrix (Auto-Refreshes every 10 seconds)")
    
    # Highlight high resource utilization in red (>80%)
    def highlight_high_usage(s):
        return ['background-color: #ffcccc' if (col == 'CPU %' or col == 'RAM %') and val > 80 else '' for col, val in s.items()]
    
    st.dataframe(df.style.apply(highlight_high_usage, axis=1), use_container_width=True)
    
else:
    st.warning("Waiting for data logs from client machines...")

# --- Native Auto-Rerun Loop Execution ---
# Wait 10 seconds, then cleanly force the dashboard to refresh its own data
time.sleep(10)
st.rerun()