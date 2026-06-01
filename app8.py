import streamlit as st
import os
import json
import pandas as pd
import time
from datetime import datetime, date

st.set_page_config(page_title="Next Toppers Network Monitor", layout="wide")

# ================= UI ENHANCEMENTS (CUSTOM STYLING) =================
st.markdown("""
<style>
    h1 {
        text-align: center;
        background: -webkit-linear-gradient(45deg, #FF8C00, #FFD700, #00BFFF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 900;
        padding-bottom: 20px;
    }
    h2, h3 {
        background: -webkit-linear-gradient(45deg, #FFD700, #00BFFF);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-weight: 800;
    }
    [data-testid="stDataFrame"] {
        border-radius: 10px;
        overflow: hidden;
        box-shadow: 0 4px 10px rgba(0, 191, 255, 0.1);
        border: 1px solid rgba(0, 191, 255, 0.2);
    }
    [data-testid="stMetricValue"] {
        color: #00BFFF;
        font-weight: 900;
    }
    .stDownloadButton > button {
        background-color: transparent;
        color: #FF8C00;
        border: 2px solid #FF8C00;
        border-radius: 8px;
        font-weight: bold;
        transition: 0.3s;
        width: 100%;
    }
    .stDownloadButton > button:hover {
        box-shadow: 0 0 15px #FFD700;
        background-color: #FFD700;
        color: #000000;
        border-color: #FFD700;
    }
</style>
""", unsafe_allow_html=True)

st.title("🖥️ Next Toppers Network and System Health Status with Inventory")

log_dir = "C:\\CustomMonitor\\logs"
speed_log_path = "C:\\CustomMonitor\\logs\\wan_speed.json"
HISTORY_DIR = "C:\\CustomMonitor\\history"

def format_bytes_value(val):
    mb = val / (1024 * 1024)
    return f"{round(mb / 1024, 2)} GB" if mb > 1024 else f"{round(mb, 1)} MB"

def format_minutes_to_time(m):
    return f"{m // 60}h {m % 60}m" if m >= 60 else f"{m} Mins"

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
                c2.metric("Live Download Speed", f"{dl} Mbps", delta="🟢 HEALTHY" if dl >= 25 else "- LOW", delta_color="normal" if dl >= 25 else "inverse")
                c3.metric("Live Upload Speed", f"{ul} Mbps", delta="🟢 HEALTHY" if ul >= 25 else "- LOW", delta_color="normal" if ul >= 25 else "inverse")
                c4.metric("Last Speed Check", speed_data.get("last_checked", "--:--:--"))
            except Exception: pass
        st.write("---")

if "cached_df" not in st.session_state:
    st.session_state.cached_df = pd.DataFrame()

@st.fragment(run_every=10)
def render_dashboard_metrics():
    rows = []
    hardware_inventory = {}
    daily_db = {}
    total_day_download = 0
    total_day_upload = 0
    
    history_file = os.path.join(HISTORY_DIR, f"usage_{date_str}.json")
    if os.path.exists(history_file):
        try:
            with open(history_file, "r") as f:
                daily_db = json.load(f).get("devices", {})
                for k, v in daily_db.items():
                    total_day_download += v.get("daily_rx_bytes", 0)
                    total_day_upload += v.get("daily_tx_bytes", 0)
        except Exception: pass

    total_current_download = 0
    total_current_upload = 0

    if os.path.exists(log_dir):
        for filename in os.listdir(log_dir):
            if filename.endswith(".log") and filename != "wan_speed.json":
                filepath = os.path.join(log_dir, filename)
                last_mod = os.path.getmtime(filepath)
                
                with open(filepath, "r") as f:
                    try:
                        data = json.load(f)
                        hostname = data.get('hostname', 'Unknown').strip()
                        lookup_key = hostname.upper()
                        
                        status = "🟢 ONLINE" if (time.time() - last_mod) <= 240 and is_today else "🔴 OFFLINE"
                        if not is_today: status = "⌛ ARCHIVED"

                        raw_rx = int(data.get('net_rx_bytes', 0))
                        raw_tx = int(data.get('net_tx_bytes', 0))

                        if status == "🟢 ONLINE":
                            total_current_download += raw_rx
                            total_current_upload += raw_tx

                        history = daily_db.get(lookup_key, {})
                        
                        ssd_p = float(data.get('ssd_used_pct', 0.0))
                        hdd_p = float(data.get('hdd_used_pct', 0.0))
                        gpu_load = float(data.get('gpu_load_pct', 0.0))
                        gpu_name = data.get('gpu_primary', 'Integrated GPU')

                        rows.append({
                            "Hostname": hostname,
                            "OS": data.get('os', 'Windows'),
                            "Status": status,
                            "CPU %": float(data.get('cpu_load', 0.0)),
                            "RAM %": float(data.get('ram_used_pct', 0.0)),
                            "SSD Used %": ssd_p,
                            "HDD Used %": hdd_p,
                            "GPU Name": gpu_name,
                            "GPU Load %": gpu_load,
                            "Current Boot Download": format_bytes_value(raw_rx),
                            "Total Day Download": format_bytes_value(history.get("daily_rx_bytes", 0)),
                            "Current Boot Upload": format_bytes_value(raw_tx),
                            "Total Day Upload": format_bytes_value(history.get("daily_tx_bytes", 0)),
                            "Time Online (Uptime)": format_minutes_to_time(history.get("online_minutes", 0)),
                            "Time Offline (Downtime)": format_minutes_to_time(history.get("offline_minutes", 0)),
                            "IP Addresses": ", ".join([f"{a.get('IP')}" for a in data.get('adapters', [])]) if isinstance(data.get('adapters'), list) else data.get('adapters', {}).get('IP', filename.replace(".log", "")),
                            "_raw_mtime": last_mod
                        })
                        hardware_inventory[lookup_key] = data
                    except Exception: pass

    if rows:
        df = pd.DataFrame(rows).sort_values(by="_raw_mtime", ascending=False).drop_duplicates(subset=["Hostname"], keep="first").sort_values(by="Hostname")
        st.session_state.cached_df = df 
        
        online_df = df[df['Status'] == '🟢 ONLINE']
        
        row1_col1, row1_col2, row1_col3, row1_col4 = st.columns(4)
        row1_col1.metric("Total Active Nodes", f"{len(df)} PCs")
        row1_col2.metric("Online Right Now", f"🟢 {len(online_df)}" if is_today else "⌛ ARCHIVED")
        row1_col3.metric("Highest CPU Load", f"{df['CPU %'].max()}%")
        row1_col4.metric("Highest RAM Load", f"{df['RAM %'].max()}%")
        
        st.write("") 
        
        row2_col1, row2_col2, row2_col3, row2_col4 = st.columns(4)
        row2_col1.metric("Network Current Download", format_bytes_value(total_current_download))
        row2_col2.metric("Total Day Download", format_bytes_value(total_day_download))
        row2_col3.metric("Network Current Upload", format_bytes_value(total_current_upload))
        row2_col4.metric("Total Day Upload", format_bytes_value(total_day_upload))
        
        st.write("---")
        
        # --- FIXED: ADDED SEPARATE DEDICATED MATRIX TABLE EXPORT BUTTON HERE ---
        matrix_cols = st.columns([3, 1])
        with matrix_cols[0]:
            st.write("### 📊 Workstation Live Status Matrix")
        with matrix_cols[1]:
            display_cols = [c for c in df.columns if c != "_raw_mtime"]
            matrix_csv = df[display_cols].to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Download Live Matrix (.CSV)",
                data=matrix_csv,
                file_name=f"Next_Toppers_Live_Matrix_{date_str}.csv",
                mime="text/csv",
                key="live_matrix_download_btn"
            )
        
        def highlight_high_usage(s):
            return ['background-color: #ffcccc' if col in ['CPU %', 'RAM %', 'SSD Used %'] and val >= 85.0 else '' for col, val in s.items()]
            
        st.dataframe(df[display_cols].style.apply(highlight_high_usage, axis=1), use_container_width=True)
        
        st.write("---")
        st.write("## 🔍 Deep Hardware Asset Management Explorer")
        target_pc = st.selectbox("Select Target Workstation to Inspect Hardware Inventory Specifications:", sorted(hardware_inventory.keys()))
        if target_pc:
            hw = hardware_inventory[target_pc]
            st.write(f"**Processor Type Name:** {hw.get('cpu_name', 'N/A')} | **CPU Core ID Serial:** {hw.get('cpu_serial', 'N/A')} | **Total Installed RAM:** {hw.get('ram_total_gb', 'N/A')} GB")
            c1, c2 = st.columns(2)
            c1.markdown("**Storage Subsystem Array:**")
            c1.dataframe(pd.DataFrame(hw.get('storage', [])), use_container_width=True, hide_index=True)
            c2.markdown("**Connected USB Input Peripherals:**")
            c2.dataframe(pd.DataFrame(hw.get('peripherals', [])), use_container_width=True, hide_index=True)
    else:
        st.warning("No data logged.")

render_internet_speed_banner()
render_dashboard_metrics()

st.markdown("---")
st.subheader(f"📥 Export Complete Hardware Inventory ({date_str})")

def generate_inventory_csv(target_date_str):
    filepath = os.path.join(HISTORY_DIR, f"usage_{target_date_str}.json")
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
        devices = data.get("devices", {})
        
        export_list = []
        for host, info in devices.items():
            storage_list = info.get("storage", [])
            storage_str = " | ".join([f"{s.get('Model','')} ({s.get('Type','')}) Size: {s.get('Size','')} Used: {s.get('Used_Pct',0)}%" for s in storage_list])
            
            periph_list = info.get("peripherals", [])
            periph_str = ", ".join([p.get("Name", "Device") for p in periph_list]) if periph_list else "None"

            # FIXED BULLETPROOF FALLBACK: Reads directly from live log if the history tracking file does not have the key yet
            gpu_hardware = info.get("gpu_primary")
            if not gpu_hardware or gpu_hardware == "Integrated Graphics" or gpu_hardware == "N/A":
                log_file = os.path.join(log_dir, f"{host.upper()}.log")
                if os.path.exists(log_file):
                    try:
                        with open(log_file, "r") as lf:
                            log_data = json.load(lf)
                            gpu_hardware = log_data.get("gpu_primary", "Integrated Graphics")
                    except Exception: pass

            export_list.append({
                "Computer Name": host,
                "Processor (CPU)": info.get("cpu_name", "N/A"),
                "CPU Serial ID": info.get("cpu_serial", "N/A"),
                "Total RAM (GB)": f"{info.get('ram_total_gb', 0.0)} GB",
                "Primary GPU Hardware": gpu_hardware, 
                "Storage Breakdown Log": storage_str if storage_str else "N/A",
                "Connected Input Peripherals": periph_str,
                "Total Day Download": format_bytes_value(info.get("daily_rx_bytes", 0)),
                "Total Day Upload": format_bytes_value(info.get("daily_tx_bytes", 0)),
                "Time Online (Uptime)": format_minutes_to_time(info.get("online_minutes", 0)),
                "Time Offline (Downtime)": format_minutes_to_time(info.get("offline_minutes", 0))
            })
            
        df = pd.DataFrame(export_list)
        return df.to_csv(index=False).encode('utf-8')
    except Exception:
        return None

csv_file = generate_inventory_csv(date_str)
if csv_file:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.download_button(
            label=f"💾 Download Inventory Report (.CSV)",
            data=csv_file,
            file_name=f"Next_Toppers_Inventory_{date_str}.csv",
            mime="text/csv",
        )
else:
    st.info("Waiting for initial data to generate inventory report...")