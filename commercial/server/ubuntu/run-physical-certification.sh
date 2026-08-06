#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
COMMERCIAL_ROOT="$REPOSITORY_ROOT/commercial"
ENTRYPOINT="$COMMERCIAL_ROOT/tools/run_physical_certification.py"

[[ -f "$ENTRYPOINT" ]] || { echo "Physical certification entrypoint is missing: $ENTRYPOINT" >&2; exit 1; }
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "Python is missing: $PYTHON_BIN" >&2; exit 1; }

export PYTHONPATH="$COMMERCIAL_ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON_BIN" "$ENTRYPOINT" "$@"
