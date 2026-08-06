#!/usr/bin/env bash
set -euo pipefail

REMOVE_STATE=0
INSTALL_ROOT="/opt/sagar-monitor-agent"
STATE_ROOT="/var/lib/sagar-monitor-agent"

while (($#)); do
  case "$1" in
    --remove-state) REMOVE_STATE=1; shift ;;
    --install-root) INSTALL_ROOT="${2:-}"; shift 2 ;;
    --state-root) STATE_ROOT="${2:-}"; shift 2 ;;
    -h|--help)
      echo "Usage: sudo $0 [--remove-state] [--install-root PATH] [--state-root PATH]"
      exit 0
      ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this uninstaller as root." >&2
  exit 1
fi

systemctl disable --now sagar-monitor-commercial-agent.service >/dev/null 2>&1 || true
rm -f /etc/systemd/system/sagar-monitor-commercial-agent.service
rm -f /etc/xdg/autostart/sagar-monitor-commercial-notifier.desktop
systemctl daemon-reload
rm -rf -- "${INSTALL_ROOT}" "${INSTALL_ROOT}.rollback"

if ((REMOVE_STATE)); then
  rm -rf -- "${STATE_ROOT}"
fi

echo "Sagar Monitor commercial pilot agent removed."
if ((! REMOVE_STATE)); then
  echo "State and permanent identity were preserved at: ${STATE_ROOT}"
fi
