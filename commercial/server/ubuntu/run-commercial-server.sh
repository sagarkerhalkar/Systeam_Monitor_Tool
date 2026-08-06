#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT=/opt/sagar-monitor-commercial-server
CONFIG_FILE=/etc/sagar-monitor-commercial-server/server.json
VERSION_ROOT="$(readlink -f "$INSTALL_ROOT/current")"
if [[ -z "$VERSION_ROOT" || ! -d "$VERSION_ROOT" ]]; then
  echo 'Commercial server version pointer is missing or invalid.' >&2
  exit 1
fi
PYTHON="$VERSION_ROOT/venv/bin/python"
ENTRYPOINT="$VERSION_ROOT/commercial/tools/run_commercial_server.py"
[[ -x "$PYTHON" ]] || { echo "Python runtime is missing: $PYTHON" >&2; exit 1; }
[[ -f "$ENTRYPOINT" ]] || { echo "Server entrypoint is missing: $ENTRYPOINT" >&2; exit 1; }
[[ -f "$CONFIG_FILE" ]] || { echo "Server configuration is missing: $CONFIG_FILE" >&2; exit 1; }

export PYTHONPATH="$VERSION_ROOT/commercial"
exec "$PYTHON" "$ENTRYPOINT" --config "$CONFIG_FILE" serve
