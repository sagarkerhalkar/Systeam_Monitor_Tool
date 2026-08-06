#!/usr/bin/env bash
set -euo pipefail

REMOVE_DATA=false
[[ "${1:-}" == '--remove-data' ]] && REMOVE_DATA=true
[[ "$(id -u)" -eq 0 ]] || { echo 'Run this uninstaller as root.' >&2; exit 1; }

SERVICE_NAME=sagar-monitor-commercial-server.service
INSTALL_ROOT=/opt/sagar-monitor-commercial-server
CONFIG_ROOT=/etc/sagar-monitor-commercial-server
DATA_ROOT=/var/lib/sagar-monitor-commercial-server
BACKUP_ROOT=/var/backups/sagar-monitor-commercial-server

systemctl stop "$SERVICE_NAME" >/dev/null 2>&1 || true
systemctl disable "$SERVICE_NAME" >/dev/null 2>&1 || true
rm -f "/etc/systemd/system/$SERVICE_NAME"
systemctl daemon-reload
rm -rf "$INSTALL_ROOT"

if $REMOVE_DATA; then
  rm -rf "$CONFIG_ROOT" "$DATA_ROOT" "$BACKUP_ROOT"
  userdel sagarmonitor-server >/dev/null 2>&1 || true
  groupdel sagarmonitor-server >/dev/null 2>&1 || true
  echo 'Commercial server application, configuration, database, TLS files and backups were removed.'
else
  echo "Commercial server application removed. Configuration/data are preserved at $CONFIG_ROOT, $DATA_ROOT and $BACKUP_ROOT."
fi
