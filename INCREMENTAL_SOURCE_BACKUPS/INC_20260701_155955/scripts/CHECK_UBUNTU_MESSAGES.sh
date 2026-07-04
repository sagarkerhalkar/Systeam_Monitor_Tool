#!/usr/bin/env bash
set -euo pipefail
echo '=== Sagar Monitor Ubuntu Message Check ==='
echo 'Service:'
systemctl status sagar-system-monitor-client.service --no-pager || true
echo
echo 'Status JSON:'
cat /var/lib/commercial-monitor-pro/client_status.json 2>/dev/null || echo 'No status yet'
echo
echo 'Message log:'
tail -50 /var/lib/commercial-monitor-pro/server_messages.log 2>/dev/null || echo 'No message log yet'
echo
echo 'Last popup file:'
cat /tmp/sagar_monitor_last_message.txt 2>/dev/null || echo 'No /tmp/sagar_monitor_last_message.txt yet'
