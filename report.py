import os, json

log_dir = "C:\\CustomMonitor\\logs"
print("\n=== SYSTEM HEALTH & DETAILED ADAPTER REPORT ===")
# Added columns for Downloaded (Net RX) and Uploaded (Net TX) data
print(f"{'Hostname':<15} | {'OS':<12} | {'CPU %':<5} | {'RAM %':<6} | {'Data RX':<10} | {'Data TX':<10} | {'Adapter Name':<20} | {'IP Address':<15}")
print("-" * 115)

for filename in os.listdir(log_dir):
    if filename.endswith(".log"):
        with open(os.path.join(log_dir, filename), "r") as f:
            try:
                data = json.load(f)
                hostname = data.get('hostname', 'Unknown')
                os_name = data.get('os', 'Unknown')
                cpu = data.get('cpu_load', 0)
                ram = data.get('ram_used_pct', 0)
                adapters = data.get('adapters', [])
                
                # --- NEW: Convert Raw Bytes to Megabytes (MB) ---
                raw_rx = int(data.get('net_rx_bytes', 0))
                raw_tx = int(data.get('net_tx_bytes', 0))
                net_rx = f"{round(raw_rx / (1024 * 1024), 1)} MB"
                net_tx = f"{round(raw_tx / (1024 * 1024), 1)} MB"

                if isinstance(adapters, dict):
                    adapters = [adapters]

                if adapters:
                    first = adapters[0]
                    # Printing system specs along with the Calculated Network Usage
                    print(f"{hostname:<15} | {os_name:<12} | {cpu:<5} | {ram:<6} | {net_rx:<10} | {net_tx:<10} | {first.get('Name', 'N/A'):<20} | {first.get('IP', 'N/A'):<15}")
                    
                    for extra in adapters[1:]:
                        print(f"{'':<15} | {'':<12} | {'':<5} | {'':<6} | {'':<10} | {'':<10} | {extra.get('Name', 'N/A'):<20} | {extra.get('IP', 'N/A'):<15}")
                else:
                    print(f"{hostname:<15} | {os_name:<12} | {cpu:<5} | {ram:<6} | {net_rx:<10} | {net_tx:<10} | {'No Active Adapters':<20} | {'N/A':<15}")
                
                print("-" * 115)
            except Exception as e:
                pass