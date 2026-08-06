#!/usr/bin/env bash
set -euo pipefail

CERTIFICATE_FILE=''
PRIVATE_KEY_FILE=''
BIND_HOST='0.0.0.0'
PORT='8443'
PYTHON_BIN='python3'
ORGANIZATION_NAME=''
ORGANIZATION_ID=''
ADMIN_USERNAME=''
ADMIN_PASSWORD_FILE=''
HEALTH_URL=''
CA_BUNDLE=''

while [[ $# -gt 0 ]]; do
  case "$1" in
    --certificate) CERTIFICATE_FILE="$2"; shift 2 ;;
    --private-key) PRIVATE_KEY_FILE="$2"; shift 2 ;;
    --bind-host) BIND_HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --python) PYTHON_BIN="$2"; shift 2 ;;
    --organization-name) ORGANIZATION_NAME="$2"; shift 2 ;;
    --organization-id) ORGANIZATION_ID="$2"; shift 2 ;;
    --admin-username) ADMIN_USERNAME="$2"; shift 2 ;;
    --admin-password-file) ADMIN_PASSWORD_FILE="$2"; shift 2 ;;
    --health-url) HEALTH_URL="$2"; shift 2 ;;
    --ca-bundle) CA_BUNDLE="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

[[ "$(id -u)" -eq 0 ]] || { echo 'Run this installer as root.' >&2; exit 1; }
[[ -f "$CERTIFICATE_FILE" ]] || { echo 'A TLS certificate file is required.' >&2; exit 1; }
[[ -f "$PRIVATE_KEY_FILE" ]] || { echo 'A TLS private key file is required.' >&2; exit 1; }
[[ "$PORT" =~ ^[0-9]+$ ]] && (( PORT >= 1 && PORT <= 65535 )) || { echo 'Port must be 1-65535.' >&2; exit 1; }
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "Python is missing: $PYTHON_BIN" >&2; exit 1; }

SERVICE_USER=sagarmonitor-server
SERVICE_GROUP=sagarmonitor-server
SERVICE_NAME=sagar-monitor-commercial-server.service
INSTALL_ROOT=/opt/sagar-monitor-commercial-server
VERSIONS_ROOT="$INSTALL_ROOT/versions"
CONFIG_ROOT=/etc/sagar-monitor-commercial-server
TLS_ROOT="$CONFIG_ROOT/tls"
CONFIG_FILE="$CONFIG_ROOT/server.json"
DATA_ROOT=/var/lib/sagar-monitor-commercial-server
DATABASE_FILE="$DATA_ROOT/commercial.db"
BACKUP_ROOT=/var/backups/sagar-monitor-commercial-server
VERSION_NAME="$(date -u +%Y%m%dT%H%M%SZ)"
VERSION_ROOT="$VERSIONS_ROOT/$VERSION_NAME"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
COMMERCIAL_SOURCE="$REPOSITORY_ROOT/commercial"
OLD_TARGET=''
PRE_UPGRADE_BACKUP=''
CONFIG_ROLLBACK_ROOT=''
DATABASE_EXISTED_BEFORE=false
[[ -f "$DATABASE_FILE" ]] && DATABASE_EXISTED_BEFORE=true
[[ -L "$INSTALL_ROOT/current" ]] && OLD_TARGET="$(readlink -f "$INSTALL_ROOT/current")"

[[ -d "$COMMERCIAL_SOURCE/sagar_monitor" ]] || { echo "Commercial source is missing: $COMMERCIAL_SOURCE" >&2; exit 1; }

if ! getent group "$SERVICE_GROUP" >/dev/null; then
  groupadd --system "$SERVICE_GROUP"
fi
if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --gid "$SERVICE_GROUP" --home-dir "$DATA_ROOT" --shell /usr/sbin/nologin "$SERVICE_USER"
fi

systemctl stop "$SERVICE_NAME" >/dev/null 2>&1 || true

rollback() {
  local exit_code=$?
  local database_restore_ok=true
  local configuration_restore_ok=true
  set +e
  systemctl stop "$SERVICE_NAME" >/dev/null 2>&1
  if $DATABASE_EXISTED_BEFORE && [[ -n "$PRE_UPGRADE_BACKUP" && -f "$PRE_UPGRADE_BACKUP" && -x "$VERSION_ROOT/venv/bin/python" ]]; then
    runuser -u "$SERVICE_USER" -- env PYTHONPATH="$VERSION_ROOT/commercial" \
      "$VERSION_ROOT/venv/bin/python" "$VERSION_ROOT/commercial/tools/run_commercial_server.py" \
      --config "$CONFIG_FILE" restore --backup "$PRE_UPGRADE_BACKUP" --confirm-service-stopped
    [[ $? -eq 0 ]] || database_restore_ok=false
  fi
  if [[ -n "$CONFIG_ROLLBACK_ROOT" && -d "$CONFIG_ROLLBACK_ROOT" ]]; then
    [[ -f "$CONFIG_ROLLBACK_ROOT/server.json" ]] && cp -f "$CONFIG_ROLLBACK_ROOT/server.json" "$CONFIG_FILE"
    [[ -f "$CONFIG_ROLLBACK_ROOT/server.crt" ]] && cp -f "$CONFIG_ROLLBACK_ROOT/server.crt" "$TLS_ROOT/server.crt"
    [[ -f "$CONFIG_ROLLBACK_ROOT/server.key" ]] && cp -f "$CONFIG_ROLLBACK_ROOT/server.key" "$TLS_ROOT/server.key"
    chown root:"$SERVICE_GROUP" "$CONFIG_FILE" "$TLS_ROOT/server.crt" "$TLS_ROOT/server.key" 2>/dev/null
    chmod 0640 "$CONFIG_FILE" "$TLS_ROOT/server.crt" "$TLS_ROOT/server.key" 2>/dev/null
    [[ $? -eq 0 ]] || configuration_restore_ok=false
  fi
  if [[ -n "$OLD_TARGET" && -d "$OLD_TARGET" ]]; then
    ln -sfn "$OLD_TARGET" "$INSTALL_ROOT/current.rollback"
    mv -Tf "$INSTALL_ROOT/current.rollback" "$INSTALL_ROOT/current"
    if $database_restore_ok && $configuration_restore_ok; then
      systemctl start "$SERVICE_NAME" >/dev/null 2>&1
    fi
  else
    rm -f "$INSTALL_ROOT/current"
  fi
  if ! $DATABASE_EXISTED_BEFORE; then
    rm -f "$DATABASE_FILE" "$DATABASE_FILE-wal" "$DATABASE_FILE-shm"
  fi
  rm -f "$CONFIG_ROOT/.bootstrap-password"
  rm -rf "$VERSION_ROOT"
  if ! $database_restore_ok || ! $configuration_restore_ok; then
    echo 'Installation failed and rollback was incomplete. Old service remains stopped.' >&2
  fi
  exit "$exit_code"
}
trap rollback ERR

install -d -m 0750 -o root -g "$SERVICE_GROUP" "$INSTALL_ROOT" "$VERSIONS_ROOT" "$CONFIG_ROOT" "$TLS_ROOT"
install -d -m 0700 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$DATA_ROOT" "$BACKUP_ROOT"
install -d -m 0750 -o root -g "$SERVICE_GROUP" "$VERSION_ROOT/commercial"
cp -a "$COMMERCIAL_SOURCE/sagar_monitor" "$VERSION_ROOT/commercial/"
cp -a "$COMMERCIAL_SOURCE/tools" "$VERSION_ROOT/commercial/"
cp -a "$COMMERCIAL_SOURCE/migrations" "$VERSION_ROOT/commercial/"
cp "$COMMERCIAL_SOURCE/requirements.lock" "$VERSION_ROOT/commercial/requirements.lock"
chown -R root:"$SERVICE_GROUP" "$VERSION_ROOT"
chmod -R go-w "$VERSION_ROOT"

"$PYTHON_BIN" -m venv "$VERSION_ROOT/venv"
"$VERSION_ROOT/venv/bin/python" -m pip install --disable-pip-version-check --require-hashes -r "$VERSION_ROOT/commercial/requirements.lock"
"$VERSION_ROOT/venv/bin/python" -c 'import ssl,sys; c=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER); c.load_cert_chain(sys.argv[1],sys.argv[2])' "$CERTIFICATE_FILE" "$PRIVATE_KEY_FILE"

if [[ -f "$CONFIG_FILE" || -f "$TLS_ROOT/server.crt" || -f "$TLS_ROOT/server.key" ]]; then
  CONFIG_ROLLBACK_ROOT="$BACKUP_ROOT/pre-upgrade-config-$(date -u +%Y%m%dT%H%M%SZ)"
  install -d -m 0700 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$CONFIG_ROLLBACK_ROOT"
  [[ -f "$CONFIG_FILE" ]] && cp -f "$CONFIG_FILE" "$CONFIG_ROLLBACK_ROOT/server.json"
  [[ -f "$TLS_ROOT/server.crt" ]] && cp -f "$TLS_ROOT/server.crt" "$CONFIG_ROLLBACK_ROOT/server.crt"
  [[ -f "$TLS_ROOT/server.key" ]] && cp -f "$TLS_ROOT/server.key" "$CONFIG_ROLLBACK_ROOT/server.key"
  chown -R "$SERVICE_USER":"$SERVICE_GROUP" "$CONFIG_ROLLBACK_ROOT"
  chmod -R go-rwx "$CONFIG_ROLLBACK_ROOT"
fi

install -m 0640 -o root -g "$SERVICE_GROUP" "$CERTIFICATE_FILE" "$TLS_ROOT/server.crt"
install -m 0640 -o root -g "$SERVICE_GROUP" "$PRIVATE_KEY_FILE" "$TLS_ROOT/server.key"

cat >"$CONFIG_FILE.tmp" <<EOF
{
  "bind_host": "$BIND_HOST",
  "port": $PORT,
  "database_path": "$DATABASE_FILE",
  "certificate_file": "$TLS_ROOT/server.crt",
  "private_key_file": "$TLS_ROOT/server.key",
  "backup_directory": "$BACKUP_ROOT",
  "max_body_bytes": 2097152,
  "max_header_bytes": 32768,
  "socket_timeout_seconds": 30,
  "allow_loopback_http": false,
  "server_label": "Sagar Monitor Commercial Server"
}
EOF
chown root:"$SERVICE_GROUP" "$CONFIG_FILE.tmp"
chmod 0640 "$CONFIG_FILE.tmp"
mv -f "$CONFIG_FILE.tmp" "$CONFIG_FILE"

PYTHON="$VERSION_ROOT/venv/bin/python"
ENTRYPOINT="$VERSION_ROOT/commercial/tools/run_commercial_server.py"
export PYTHONPATH="$VERSION_ROOT/commercial"

if $DATABASE_EXISTED_BEFORE; then
  PRE_UPGRADE_BACKUP="$BACKUP_ROOT/pre-upgrade-$(date -u +%Y%m%dT%H%M%SZ).db"
  runuser -u "$SERVICE_USER" -- "$PYTHON" "$ENTRYPOINT" --config "$CONFIG_FILE" backup --output "$PRE_UPGRADE_BACKUP"
  runuser -u "$SERVICE_USER" -- "$PYTHON" "$ENTRYPOINT" --config "$CONFIG_FILE" migrate
else
  if [[ -z "$ORGANIZATION_NAME" || -z "$ADMIN_USERNAME" || ! -f "$ADMIN_PASSWORD_FILE" ]]; then
    echo 'First installation requires --organization-name, --admin-username and --admin-password-file.' >&2
    false
  fi
  TEMP_PASSWORD="$CONFIG_ROOT/.bootstrap-password"
  install -m 0600 -o "$SERVICE_USER" -g "$SERVICE_GROUP" "$ADMIN_PASSWORD_FILE" "$TEMP_PASSWORD"
  BOOTSTRAP_ARGS=(
    "$ENTRYPOINT" --config "$CONFIG_FILE" bootstrap
    --organization-name "$ORGANIZATION_NAME"
    --admin-username "$ADMIN_USERNAME"
    --password-file "$TEMP_PASSWORD"
  )
  [[ -n "$ORGANIZATION_ID" ]] && BOOTSTRAP_ARGS+=(--organization-id "$ORGANIZATION_ID")
  runuser -u "$SERVICE_USER" -- "$PYTHON" "${BOOTSTRAP_ARGS[@]}"
fi

runuser -u "$SERVICE_USER" -- "$PYTHON" "$ENTRYPOINT" --config "$CONFIG_FILE" health
install -m 0755 -o root -g root "$SCRIPT_DIR/run-commercial-server.sh" "$INSTALL_ROOT/run-commercial-server.sh"
install -m 0644 -o root -g root "$SCRIPT_DIR/sagar-monitor-commercial-server.service" "/etc/systemd/system/$SERVICE_NAME"
ln -sfn "$VERSION_ROOT" "$INSTALL_ROOT/current.new"
mv -Tf "$INSTALL_ROOT/current.new" "$INSTALL_ROOT/current"
systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null
systemctl start "$SERVICE_NAME"
sleep 3
systemctl is-active --quiet "$SERVICE_NAME"

if [[ -n "$HEALTH_URL" ]]; then
  HEALTH_ARGS=(health --remote --url "$HEALTH_URL")
  [[ -n "$CA_BUNDLE" ]] && HEALTH_ARGS+=(--ca-bundle "$CA_BUNDLE")
  runuser -u "$SERVICE_USER" -- "$PYTHON" "$ENTRYPOINT" --config "$CONFIG_FILE" "${HEALTH_ARGS[@]}"
fi

trap - ERR
echo "Commercial server installed successfully. Version: $VERSION_NAME"
echo "Configuration: $CONFIG_FILE"
echo "Database: $DATABASE_FILE"
