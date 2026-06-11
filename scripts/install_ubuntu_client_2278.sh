#!/usr/bin/env bash
set -euo pipefail
SERVER_URL="${SERVER_URL:?Use: sudo SERVER_URL=http://SERVER-IP:2278 bash install_ubuntu_client_2278.sh}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-5}"
ROOT="/opt/sagar-system-monitor"
DATA="/var/lib/commercial-monitor-pro"

echo "Installing prerequisites for Ubuntu/Linux client..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -y >/dev/null 2>&1 || true
apt-get install -y curl python3 iproute2 procps coreutils util-linux pciutils usbutils lm-sensors libnotify-bin zenity >/dev/null 2>&1 || true

# Stop old test service names so old broken clients cannot run in parallel.
systemctl disable --now commercial-monitor-pro-test2278.service >/dev/null 2>&1 || true
systemctl disable --now sagar-system-monitor-client.service >/dev/null 2>&1 || true

mkdir -p "$ROOT" "$DATA"
cp "$(dirname "$0")/client_ubuntu.sh" "$ROOT/client_ubuntu.sh"
chmod +x "$ROOT/client_ubuntu.sh"

cat >/etc/systemd/system/sagar-system-monitor-client.service <<EOF2
[Unit]
Description=Sagar Kerhalkar System Monitor Tool Ubuntu Client
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=SERVER_URL=$SERVER_URL
Environment=INTERVAL_SECONDS=$INTERVAL_SECONDS
Environment=ROOT=/var/lib/commercial-monitor-pro
ExecStart=$ROOT/client_ubuntu.sh
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF2

systemctl daemon-reload
systemctl enable --now sagar-system-monitor-client.service

echo "Sending one immediate Ubuntu heartbeat now..."
RUN_ONCE=1 SERVER_URL="$SERVER_URL" INTERVAL_SECONDS="$INTERVAL_SECONDS" ROOT="$DATA" "$ROOT/client_ubuntu.sh" || true

echo "Installed sagar-system-monitor-client.service sending to $SERVER_URL every ${INTERVAL_SECONDS}s"
echo "Status file: $DATA/client_status.json"
echo "Logs: sudo journalctl -u sagar-system-monitor-client.service -n 80 --no-pager"
