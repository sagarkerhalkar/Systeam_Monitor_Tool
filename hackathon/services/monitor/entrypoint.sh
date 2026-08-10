#!/usr/bin/env sh
set -eu

DATA_ROOT="${MONITOR_DATA_ROOT:-/data}"
PORT="${MONITOR_PORT:-8443}"
ORG_NAME="${MONITOR_ORG_NAME:-Sagar Monitor Hackathon}"
ORG_ID="${MONITOR_ORG_ID:-sagar-monitor-hackathon}"
ADMIN_USER="${MONITOR_ADMIN_USERNAME:-hackathon-admin}"
ADMIN_PASSWORD="${MONITOR_ADMIN_PASSWORD:-}"
CONFIG="$DATA_ROOT/server.json"
DB="$DATA_ROOT/commercial.db"
BACKUPS="$DATA_ROOT/backups"
TLS="$DATA_ROOT/tls"
CERT="$TLS/server.crt"
KEY="$TLS/server.key"
PASSWORD_FILE="$DATA_ROOT/.bootstrap-password"
ENTRYPOINT="/app/commercial/tools/run_commercial_server.py"

mkdir -p "$BACKUPS" "$TLS"
chmod 0700 "$DATA_ROOT" "$TLS" "$BACKUPS" 2>/dev/null || true

if [ ! -s "$CERT" ] || [ ! -s "$KEY" ]; then
  openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 7 \
    -subj "/CN=sagar-monitor-hackathon" \
    -addext "subjectAltName=DNS:monitor,DNS:localhost,IP:127.0.0.1" \
    -keyout "$KEY" -out "$CERT" >/dev/null 2>&1
  chmod 0600 "$KEY"
  chmod 0644 "$CERT"
fi

cat > "$CONFIG" <<EOF
{
  "bind_host": "0.0.0.0",
  "port": $PORT,
  "database_path": "$DB",
  "certificate_file": "$CERT",
  "private_key_file": "$KEY",
  "backup_directory": "$BACKUPS",
  "max_body_bytes": 2097152,
  "max_header_bytes": 32768,
  "socket_timeout_seconds": 30,
  "allow_loopback_http": false,
  "server_label": "Sagar Monitor DORA SOTA Hackathon"
}
EOF
chmod 0600 "$CONFIG"

if [ ! -s "$DB" ]; then
  if [ -z "$ADMIN_PASSWORD" ]; then
    echo "MONITOR_ADMIN_PASSWORD must be supplied on first container start." >&2
    exit 2
  fi
  printf '%s' "$ADMIN_PASSWORD" > "$PASSWORD_FILE"
  chmod 0600 "$PASSWORD_FILE"
  python "$ENTRYPOINT" --config "$CONFIG" bootstrap \
    --organization-name "$ORG_NAME" \
    --organization-id "$ORG_ID" \
    --admin-username "$ADMIN_USER" \
    --password-file "$PASSWORD_FILE"
else
  python "$ENTRYPOINT" --config "$CONFIG" migrate
fi

rm -f "$PASSWORD_FILE"
unset MONITOR_ADMIN_PASSWORD ADMIN_PASSWORD || true

python "$ENTRYPOINT" --config "$CONFIG" health
exec python "$ENTRYPOINT" --config "$CONFIG" serve
