#!/bin/bash

# Ensure the script is run with sudo privileges
if [ "$EUID" -ne 0 ]; then
  echo "Please run this script using sudo!"
  exit 1
fi

echo "=== STEP 1: Updating packages and installing tools ==="
apt update && apt install -y jq curl

echo "=== STEP 2: Creating the monitoring script in /bin/sysreport.sh ==="
# We write directly to /bin/sysreport.sh using a 'Here Document' block 
cat << 'EOF' > /bin/sysreport.sh
#!/bin/bash
# Point to your Windows Server IP
SERVER="http://156.156.40.51:8080"
HOSTNAME=$(hostname)

# 1. Get CPU Health
CPU_LOAD=$(top -bn1 | grep "Cpu(s)" | sed "s/.*, *\([0-9.]*\)%* id.*/\1/" | awk '{print 100 - $1}')

# 2. Get RAM Health
RAM_USED=$(free | grep Mem | awk '{print $3/$2 * 100.0}')

# 3. Get Network Usage
NET_STATS=$(ip -o link show | awk -F': ' '{print $2}')
NET_RX=$(cat /sys/class/net/$(echo $NET_STATS | awk '{print $1}')/statistics/rx_bytes 2>/dev/null || echo 0)
NET_TX=$(cat /sys/class/net/$(echo $NET_STATS | awk '{print $1}')/statistics/tx_bytes 2>/dev/null || echo 0)

# 4. Get ALL Active IP Addresses and Interface Names
ADAPTERS=$(ip -4 -o addr show | grep -v '127.0.0.1' | awk '{print "{\"Name\":\""$2"\",\"IP\":\""$4"\"}"}' | sed 's/\/.*//' | paste -sd, -)

# Format JSON Payload
PAYLOAD="{\"hostname\":\"$HOSTNAME\",\"os\":\"Linux\",\"cpu_load\":$CPU_LOAD,\"ram_used_pct\":$RAM_USED,\"net_rx_bytes\":$NET_RX,\"net_tx_bytes\":$NET_TX,\"adapters\":[$ADAPTERS]}"

# Push to your Windows Server
curl -X POST -H "Content-Type: application/json" -d "$PAYLOAD" $SERVER
EOF

echo "=== STEP 3: Making /bin/sysreport.sh executable ==="
chmod +x /bin/sysreport.sh

echo "=== STEP 4: Injecting the 5-Minute Cron Job ==="
# This extracts the existing crontab, appends our new line, and reinstalls it 
# without requiring you to open 'crontab -e' and type it manually.
CRON_JOB="*/5 * * * * /bin/bash /bin/sysreport.sh > /dev/null 2>&1"

# Check if the cron job already exists to avoid adding duplicates
(crontab -l 2>/dev/null | grep -F "$CRON_JOB") \
  && echo "Cron job already exists!" \
  || ( (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab - )

echo "=== STEP 5: Running a manual test push ==="
/bin/bash /bin/sysreport.sh

echo "Setup Complete! This Ubuntu machine is now reporting every 5 minutes."