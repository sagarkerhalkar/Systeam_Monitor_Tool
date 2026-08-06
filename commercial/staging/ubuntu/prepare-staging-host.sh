#!/usr/bin/env bash
set -euo pipefail

ROLE="${1:-}"
SITE="${2:-}"
OPERATOR="${3:-}"
WORK_ROOT="${4:-/var/lib/sagar-monitor-staging}"
PYTHON_EXE="${PYTHON_EXE:-python3}"
GROUP_NAME="sagar-monitor-staging"

case "$ROLE" in
  ubuntu_server|ubuntu_client_1|ubuntu_client_2|restore_host) ;;
  *) echo "Role must be ubuntu_server, ubuntu_client_1, ubuntu_client_2 or restore_host" >&2; exit 2 ;;
esac
[[ -n "$SITE" && -n "$OPERATOR" ]] || { echo "Site and operator are required" >&2; exit 2; }
[[ "$(id -u)" -eq 0 ]] || { echo "Run this staging-host preparation as root" >&2; exit 2; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMMERCIAL_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
CLI="$COMMERCIAL_ROOT/tools/run_staging_lab.py"
[[ -f "$CLI" ]] || { echo "Staging CLI is missing: $CLI" >&2; exit 2; }

getent group "$GROUP_NAME" >/dev/null || groupadd --system "$GROUP_NAME"
install -d -m 0750 -o root -g "$GROUP_NAME" "$WORK_ROOT"

PREFLIGHT="$WORK_ROOT/host-preflight.json"
MARKER="$WORK_ROOT/host-marker.json"
[[ ! -e "$MARKER" ]] || { echo "A staging marker already exists: $MARKER" >&2; exit 2; }

PYTHONPATH="$COMMERCIAL_ROOT" "$PYTHON_EXE" "$CLI" preflight \
  --role "$ROLE" \
  --work-root "$WORK_ROOT" \
  --phase clean \
  --output "$PREFLIGHT" \
  --marker "$MARKER" \
  --site "$SITE" \
  --operator "$OPERATOR"

chown root:"$GROUP_NAME" "$PREFLIGHT" "$MARKER"
chmod 0640 "$PREFLIGHT" "$MARKER"

echo "Staging host prepared."
echo "Preflight: $PREFLIGHT"
echo "Marker:    $MARKER"
