#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
export PYTHONPATH="${ROOT}/commercial"
exec "${ROOT}/venv/bin/python" \
  "${ROOT}/commercial/tools/run_edge_agent.py" \
  --config /etc/sagar-monitor-agent/agent.json \
  notifier
