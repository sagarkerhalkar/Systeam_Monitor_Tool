#!/usr/bin/env bash
set -euo pipefail
SERVER_URL="${SERVER_URL:?Use: sudo SERVER_URL=http://SERVER-IP:2278 bash BOOTSTRAP_UBUNTU_CLIENT_2278.sh}"
INTERVAL_SECONDS="${INTERVAL_SECONDS:-5}"
FILE_SERVER_URL="${FILE_SERVER_URL:-$SERVER_URL}"
FILE_SERVER_URL="${FILE_SERVER_URL%/}"
TMP_DIR="/tmp/sagar-system-monitor"
mkdir -p "$TMP_DIR"

echo "Checking server: $SERVER_URL/api/health"
if ! command -v curl >/dev/null 2>&1; then
  echo "curl is missing. Installing curl..."
  apt-get update -y >/dev/null 2>&1 || true
  apt-get install -y curl >/dev/null 2>&1 || true
fi
curl -fsSL "$SERVER_URL/api/health" >/dev/null
echo "Server reachable: OK"

echo "Downloading latest Ubuntu client files from $FILE_SERVER_URL"
curl -fsSL "$FILE_SERVER_URL/scripts/client_ubuntu.sh" -o "$TMP_DIR/client_ubuntu.sh"
curl -fsSL "$FILE_SERVER_URL/scripts/install_ubuntu_client_2278.sh" -o "$TMP_DIR/install_ubuntu_client_2278.sh"
curl -fsSL "$FILE_SERVER_URL/scripts/CHECK_UBUNTU_CLIENT_VISIBLE_DATA.sh" -o "$TMP_DIR/CHECK_UBUNTU_CLIENT_VISIBLE_DATA.sh" || true
curl -fsSL "$FILE_SERVER_URL/scripts/CHECK_UBUNTU_MESSAGES.sh" -o "$TMP_DIR/CHECK_UBUNTU_MESSAGES.sh" || true
chmod +x "$TMP_DIR"/*.sh

echo "Installing Ubuntu client service sending to $SERVER_URL every ${INTERVAL_SECONDS}s"
SERVER_URL="$SERVER_URL" INTERVAL_SECONDS="$INTERVAL_SECONDS" bash "$TMP_DIR/install_ubuntu_client_2278.sh"

echo "Done. Check: sudo systemctl status sagar-system-monitor-client.service"
