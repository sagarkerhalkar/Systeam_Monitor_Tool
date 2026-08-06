#!/usr/bin/env bash
set -euo pipefail

SERVER_URL=""
TOKEN_FILE=""
NOTIFIER_USER=""
PYTHON_BIN="python3"
INSTALL_ROOT="/opt/sagar-monitor-agent"
STATE_ROOT="/var/lib/sagar-monitor-agent"
CONFIG_ROOT="/etc/sagar-monitor-agent"
TIMEZONE_NAME="Asia/Kolkata"
HEARTBEAT_SECONDS="60"
SERVICE_NAME="sagar-monitor-commercial-agent.service"

usage() {
  cat <<'EOF'
Usage: sudo ./install-commercial-agent.sh \
  --server-url https://monitor.example.com \
  --enrollment-token-file /secure/path/token.txt \
  --notifier-user desktop-user

Options:
  --python PATH              Python 3.12+ executable (default: python3)
  --install-root PATH        Application directory
  --state-root PATH          Mutable state directory
  --timezone NAME            IANA timezone (default: Asia/Kolkata)
  --heartbeat-seconds N      10-3600 seconds (default: 60)
EOF
}

while (($#)); do
  case "$1" in
    --server-url) SERVER_URL="${2:-}"; shift 2 ;;
    --enrollment-token-file) TOKEN_FILE="${2:-}"; shift 2 ;;
    --notifier-user) NOTIFIER_USER="${2:-}"; shift 2 ;;
    --python) PYTHON_BIN="${2:-}"; shift 2 ;;
    --install-root) INSTALL_ROOT="${2:-}"; shift 2 ;;
    --state-root) STATE_ROOT="${2:-}"; shift 2 ;;
    --timezone) TIMEZONE_NAME="${2:-}"; shift 2 ;;
    --heartbeat-seconds) HEARTBEAT_SECONDS="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this installer as root." >&2
  exit 1
fi
if [[ ! ${SERVER_URL} =~ ^https:// ]]; then
  echo "--server-url must use HTTPS." >&2
  exit 1
fi
if [[ -z ${NOTIFIER_USER} ]] || ! id "${NOTIFIER_USER}" >/dev/null 2>&1; then
  echo "--notifier-user must name an existing desktop user." >&2
  exit 1
fi
if ! [[ ${HEARTBEAT_SECONDS} =~ ^[0-9]+$ ]] || ((HEARTBEAT_SECONDS < 10 || HEARTBEAT_SECONDS > 3600)); then
  echo "--heartbeat-seconds must be between 10 and 3600." >&2
  exit 1
fi
if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python executable not found: ${PYTHON_BIN}" >&2
  exit 1
fi
if ! command -v notify-send >/dev/null 2>&1; then
  echo "notify-send is required. Install the libnotify-bin package first." >&2
  exit 1
fi

"${PYTHON_BIN}" - <<'PY'
import sys
if sys.version_info < (3, 12):
    raise SystemExit("Python 3.12 or newer is required")
PY

SCRIPT_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd -- "${SCRIPT_ROOT}/../../.." && pwd)"
if [[ ! -f "${SOURCE_ROOT}/commercial/sagar_monitor/edge/runtime.py" ]]; then
  echo "Commercial agent source is incomplete." >&2
  exit 1
fi

STAGE="${INSTALL_ROOT}.new.$(date +%s).$$"
ROLLBACK="${INSTALL_ROOT}.rollback"
CONFIG_FILE="${CONFIG_ROOT}/agent.json"
CONFIG_BACKUP="${CONFIG_FILE}.rollback.$$"
MOVED_EXISTING=0
CONFIG_EXISTED=0
SWAPPED=0

rollback() {
  local exit_code=$?
  set +e
  systemctl stop "${SERVICE_NAME}" >/dev/null 2>&1
  if ((SWAPPED)); then
    rm -rf -- "${INSTALL_ROOT}"
  fi
  if ((MOVED_EXISTING)) && [[ -d ${ROLLBACK} ]]; then
    mv -- "${ROLLBACK}" "${INSTALL_ROOT}"
  fi
  if ((CONFIG_EXISTED)) && [[ -f ${CONFIG_BACKUP} ]]; then
    mv -f -- "${CONFIG_BACKUP}" "${CONFIG_FILE}"
  elif [[ -f ${CONFIG_BACKUP} ]]; then
    rm -f -- "${CONFIG_BACKUP}"
  fi
  rm -rf -- "${STAGE}"
  systemctl daemon-reload >/dev/null 2>&1
  if [[ -d ${INSTALL_ROOT} ]]; then
    systemctl start "${SERVICE_NAME}" >/dev/null 2>&1
  fi
  exit "${exit_code}"
}
trap rollback ERR INT TERM

if ! getent group sagar-monitor >/dev/null; then
  groupadd --system sagar-monitor
fi
if ! id sagar-monitor >/dev/null 2>&1; then
  useradd --system --gid sagar-monitor --home-dir /nonexistent --shell /usr/sbin/nologin sagar-monitor
fi
if ! getent group sagar-monitor-notify >/dev/null; then
  groupadd --system sagar-monitor-notify
fi
usermod -a -G sagar-monitor-notify sagar-monitor
usermod -a -G sagar-monitor,sagar-monitor-notify "${NOTIFIER_USER}"

mkdir -p -- "${STAGE}"
cp -a -- "${SOURCE_ROOT}/commercial" "${STAGE}/commercial"
install -m 0755 "${SCRIPT_ROOT}/run-system-agent.sh" "${STAGE}/run-system-agent.sh"
install -m 0755 "${SCRIPT_ROOT}/run-user-notifier.sh" "${STAGE}/run-user-notifier.sh"
"${PYTHON_BIN}" -m venv "${STAGE}/venv"
"${STAGE}/venv/bin/python" -m pip install \
  --disable-pip-version-check \
  --require-hashes \
  -r "${STAGE}/commercial/requirements.lock"
chown -R root:root "${STAGE}"
chmod -R go-w "${STAGE}"

install -d -o sagar-monitor -g sagar-monitor -m 0750 "${STATE_ROOT}"
install -d -o sagar-monitor -g sagar-monitor-notify -m 2770 "${STATE_ROOT}/messages"
install -d -o sagar-monitor -g sagar-monitor-notify -m 2770 "${STATE_ROOT}/messages/pending"
install -d -o sagar-monitor -g sagar-monitor-notify -m 2770 "${STATE_ROOT}/messages/displayed"
install -d -o root -g root -m 0755 "${CONFIG_ROOT}"

if [[ -f ${CONFIG_FILE} ]]; then
  cp -a -- "${CONFIG_FILE}" "${CONFIG_BACKUP}"
  CONFIG_EXISTED=1
fi
cat >"${CONFIG_FILE}.new" <<EOF
{
  "server_url": "${SERVER_URL%/}",
  "state_directory": "${STATE_ROOT}",
  "enrollment_token_file": "${STATE_ROOT}/enrollment.token",
  "timezone_name": "${TIMEZONE_NAME}",
  "heartbeat_interval_seconds": ${HEARTBEAT_SECONDS},
  "max_heartbeats_per_cycle": 20,
  "max_receipts_per_cycle": 50,
  "queue_limit": 10000,
  "timeout_seconds": 20,
  "allow_loopback_http": false,
  "registration_metadata": {"installer": "ubuntu-pilot-v1"}
}
EOF
install -o root -g root -m 0644 "${CONFIG_FILE}.new" "${CONFIG_FILE}"
rm -f -- "${CONFIG_FILE}.new"

if [[ ! -f ${STATE_ROOT}/credential.json ]]; then
  if [[ -z ${TOKEN_FILE} || ! -f ${TOKEN_FILE} ]]; then
    echo "A readable --enrollment-token-file is required for first installation." >&2
    false
  fi
  if [[ ! -s ${TOKEN_FILE} ]]; then
    echo "Enrollment token file is empty." >&2
    false
  fi
  install -o sagar-monitor -g sagar-monitor -m 0600 "${TOKEN_FILE}" "${STATE_ROOT}/enrollment.token"
fi

systemctl stop "${SERVICE_NAME}" >/dev/null 2>&1 || true
rm -rf -- "${ROLLBACK}"
if [[ -d ${INSTALL_ROOT} ]]; then
  mv -- "${INSTALL_ROOT}" "${ROLLBACK}"
  MOVED_EXISTING=1
fi
mv -- "${STAGE}" "${INSTALL_ROOT}"
SWAPPED=1

install -o root -g root -m 0644 \
  "${SCRIPT_ROOT}/sagar-monitor-commercial-agent.service" \
  "/etc/systemd/system/${SERVICE_NAME}"
install -o root -g root -m 0644 \
  "${SCRIPT_ROOT}/sagar-monitor-commercial-notifier.desktop" \
  "/etc/xdg/autostart/sagar-monitor-commercial-notifier.desktop"

# Registration preflight runs as the final service identity. It must succeed
# before the previous installation is considered replaceable.
runuser -u sagar-monitor -- env \
  PYTHONPATH="${INSTALL_ROOT}/commercial" \
  "${INSTALL_ROOT}/venv/bin/python" \
  "${INSTALL_ROOT}/commercial/tools/run_edge_agent.py" \
  --config "${CONFIG_FILE}" \
  once

systemctl daemon-reload
systemctl enable --now "${SERVICE_NAME}"
sleep 2
systemctl is-active --quiet "${SERVICE_NAME}"

rm -f -- "${CONFIG_BACKUP}"
trap - ERR INT TERM

echo "Sagar Monitor commercial pilot agent installed successfully."
echo "Service: ${SERVICE_NAME}"
echo "Install root: ${INSTALL_ROOT}"
echo "State root: ${STATE_ROOT}"
echo "Notifier user: ${NOTIFIER_USER} (log out and sign in once if group membership was newly added)"
