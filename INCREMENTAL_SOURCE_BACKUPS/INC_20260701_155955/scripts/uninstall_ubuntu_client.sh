#!/usr/bin/env bash
systemctl disable --now sagar-system-monitor-client.service 2>/dev/null || true
rm -f /etc/systemd/system/sagar-system-monitor-client.service
systemctl daemon-reload
echo "Removed Ubuntu test client"
