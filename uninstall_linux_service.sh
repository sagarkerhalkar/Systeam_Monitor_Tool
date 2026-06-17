#!/usr/bin/env bash
set -euo pipefail
if [[ ${EUID:-$(id -u)} -ne 0 ]]; then echo "Run with sudo." >&2; exit 1; fi
systemctl disable --now sagar-system-monitor-server.service 2>/dev/null || true
rm -f /etc/systemd/system/sagar-system-monitor-server.service
systemctl daemon-reload
