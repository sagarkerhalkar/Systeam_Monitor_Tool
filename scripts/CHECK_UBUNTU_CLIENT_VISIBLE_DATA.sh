#!/usr/bin/env bash
set -euo pipefail
STATUS="/var/lib/commercial-monitor-pro/client_status.json"
ERR="/var/lib/commercial-monitor-pro/client_error.log"
MSG="/var/lib/commercial-monitor-pro/server_messages.log"
echo "=== Service ==="
systemctl is-active sagar-system-monitor-client.service || true
echo
echo "=== Client Status ==="
if [ -f "$STATUS" ]; then cat "$STATUS"; else echo "No status file yet: $STATUS"; fi
echo
echo "=== Last Errors ==="
if [ -f "$ERR" ]; then tail -n 80 "$ERR"; else echo "No error log."; fi
echo
echo "=== Last Server Messages ==="
if [ -f "$MSG" ]; then tail -n 50 "$MSG"; else echo "No server messages yet."; fi
