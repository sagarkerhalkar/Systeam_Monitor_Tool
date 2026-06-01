#!/bin/bash
# Next Toppers Universal Linux Agent (Systemd Fixed Execution Version)

SERVER_URL="http://156.156.40.51:8080"
INSTALL_DIR="/opt/nexttoppers"
SCRIPT_PATH="$INSTALL_DIR/client.sh"

if [ "$EUID" -ne 0 ]; then
  echo "CRITICAL: Please run this script with sudo privileges."
  exit 1
fi

# ================= 1. INFINITE LOOP PAYLOAD =================
if [ "$1" == "--loop" ]; then
    HOSTNAME=$(hostname)
    OS_NAME=$(grep PRETTY_NAME /etc/os-release | cut -d '"' -f 2)
    CPU_NAME=$(lscpu | grep "Model name:" | sed -e 's/Model name:[[:space:]]*//' | xargs)
    [ -z "$CPU_NAME" ] && CPU_NAME="Universal Linux Environment Processor Subsystem"
    
    CPU_SR=$(dmidecode -t processor | grep "ID:" | head -n 1 | awk '{$1=""; print $0}' | xargs || echo "N/A")
    RAM_TOTAL=$(free -g | awk '/^Mem:/{print $2}')
    RAM_USED_PCT=$(free | awk '/Mem/{printf("%.1f"), $3/$2 * 100}')
    
    STORAGE_JSON="[]"
    SSD_PCT=0
    HDD_PCT=0
    
    while read -r line; do
        dev=$(echo "$line" | awk '{print $1}')
        size=$(echo "$line" | awk '{print $2}')
        pct=$(echo "$line" | awk '{print $5}' | tr -d '%')
        
        drive_base=$(basename "$dev")
        drive_name=$(basename "$(readlink -f "/sys/class/block/$drive_base")" 2>/dev/null | tr -d '0-9')
        [ -z "$drive_name" ] && drive_name=$(echo "$drive_base" | tr -d '0-9')
        
        rotational=$(cat "/sys/block/$drive_name/queue/rotational" 2>/dev/null)
        type="SSD"
        if [ "$rotational" == "1" ]; then
            type="HDD"
            [ "$pct" -gt "$HDD_PCT" ] && HDD_PCT=$pct
        else
            [ "$pct" -gt "$SSD_PCT" ] && SSD_PCT=$pct
        fi
        STORAGE_JSON=$(echo $STORAGE_JSON | jq ". += [{\"Model\":\"Disk $dev\",\"Type\":\"$type\",\"Size\":\"$size\",\"Used_Pct\":$pct}]")
    done < <(df -h | grep -E '^/dev/')

    NET_RX=$(cat /sys/class/net/e*/statistics/rx_bytes 2>/dev/null | head -n 1 || echo 0)
    NET_TX=$(cat /sys/class/net/e*/statistics/tx_bytes 2>/dev/null | head -n 1 || echo 0)
    
    MAC_JSON="["
    for IFACE in $(ls /sys/class/net/ | grep -v lo); do
        IP=$(ip -4 addr show $IFACE 2>/dev/null | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n1)
        if [ ! -z "$IP" ]; then
            MAC_JSON="$MAC_JSON {\"Interface\": \"$IFACE\", \"IP\": \"$IP\"},"
        fi
    done
    MAC_JSON=$(echo $MAC_JSON | sed 's/,$//')"]"
    [ "$MAC_JSON" == "]" ] && MAC_JSON="[]"

    CPU_LOAD=$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1}')

JSON_PAYLOAD=$(jq -n \
  --arg hn "$HOSTNAME" --arg os "$OS_NAME" --arg cn "$CPU_NAME" --arg cs "$CPU_SR" --argjson rt "$RAM_TOTAL" \
  --argjson cl "${CPU_LOAD:-0}" --argjson rm "${RAM_USED_PCT:-0}" --argjson rx "$NET_RX" --argjson tx "$NET_TX" \
  --argjson ssd "$SSD_PCT" --argjson hdd "$HDD_PCT" \
  --argjson st "$STORAGE_JSON" --argjson ad "$MAC_JSON" \
  '{hostname: $hn, os: $os, cpu_name: $cn, cpu_serial: $cs, ram_total_gb: $rt, storage: $st, gpus: [], adapters: $ad, peripherals: [], cpu_load: $cl, ram_used_pct: $rm, gpu_primary: "Linux Default Video Driver Subsystem", gpu_load_pct: 0.0, ssd_used_pct: $ssd, hdd_used_pct: $hdd, net_rx_bytes: $rx, net_tx_bytes: $tx}')

    curl -s -X POST -H "Content-Type: application/json" -d "$JSON_PAYLOAD" $SERVER_URL > /dev/null
    exit 0
fi

# ================= 2. INSTALLATION PHASE =================
echo "Purging old configuration files..."
crontab -l 2>/dev/null | grep -v 'sysreport.sh' | crontab -

echo "Validating tool dependencies..."
if command -v apt-get &>/dev/null; then
    apt-get update -y -qq && apt-get install -y -qq curl jq dmidecode iproute2 bc
elif command -v yum &>/dev/null; then
    yum install -y -q curl jq dmidecode iproute2 bc
fi

mkdir -p "$INSTALL_DIR"
cp "$(readlink -f "$0")" "$SCRIPT_PATH"
chmod +x "$SCRIPT_PATH"

echo "Rebuilding Systemd service loop..."
cat <<EOF > /etc/systemd/system/nexttoppers-monitor.service
[Unit]
Description=Next Toppers Network Monitoring Agent
After=network-online.target Wants=network-online.target

[Service]
Type=simple
ExecStartPre=/bin/sleep 30
ExecStart=/bin/bash -c "while true; do $SCRIPT_PATH --loop; sleep 120; done"
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable nexttoppers-monitor.service
systemctl restart nexttoppers-monitor.service

echo "✅ Persistent Linux Agent deployment completed cleanly!"