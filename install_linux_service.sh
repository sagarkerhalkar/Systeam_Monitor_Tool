#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then echo "Run with sudo." >&2; exit 1; fi
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="$(command -v python3 || true)"
[[ -n "$PYTHON_BIN" ]] || { echo "python3 not found" >&2; exit 1; }
install -d -m 0755 /etc/sagar-system-monitor
cat > /etc/systemd/system/sagar-system-monitor-server.service <<UNIT
[Unit]
Description=Sagar System Health Monitor Server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
ExecStart=$PYTHON_BIN -u $ROOT/universal_server.py --host 0.0.0.0 --port 2278
Restart=always
RestartSec=5
TimeoutStopSec=20
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now sagar-system-monitor-server.service
systemctl --no-pager --full status sagar-system-monitor-server.service || true
