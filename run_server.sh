#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
PYTHON_BIN="${PYTHON_BIN:-python3}"
HOST="${CMP_HOST:-0.0.0.0}"
PORT="${CMP_PORT:-2278}"
exec "$PYTHON_BIN" -u universal_server.py --host "$HOST" --port "$PORT"
