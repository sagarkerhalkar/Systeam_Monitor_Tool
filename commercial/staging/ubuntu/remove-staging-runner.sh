#!/usr/bin/env bash
set -euo pipefail

INSTALL_ROOT="${1:-/opt/actions-runner-sagar-staging}"
WORK_ROOT="${2:-/var/lib/sagar-monitor-staging}"
REMOVAL_TOKEN_FILE="${3:-}"

[[ "$(id -u)" -eq 0 ]] || { echo "Run runner removal as root" >&2; exit 2; }
if [[ ! -d "$INSTALL_ROOT" ]]; then
  echo "Runner directory is already absent: $INSTALL_ROOT"
  exit 0
fi

if [[ -x "$INSTALL_ROOT/svc.sh" ]]; then
  "$INSTALL_ROOT/svc.sh" stop || true
  "$INSTALL_ROOT/svc.sh" uninstall || true
fi

if [[ -n "$REMOVAL_TOKEN_FILE" ]]; then
  [[ -f "$REMOVAL_TOKEN_FILE" ]] || { echo "Removal token file is missing: $REMOVAL_TOKEN_FILE" >&2; exit 2; }
  TOKEN="$(tr -d '\r\n' <"$REMOVAL_TOKEN_FILE")"
  "$INSTALL_ROOT/config.sh" remove --token "$TOKEN" || true
  TOKEN=""
  if command -v shred >/dev/null 2>&1; then
    shred -u "$REMOVAL_TOKEN_FILE" || rm -f "$REMOVAL_TOKEN_FILE"
  else
    rm -f "$REMOVAL_TOKEN_FILE"
  fi
fi

rm -rf "$INSTALL_ROOT"
rm -f "$WORK_ROOT/runner-receipt.json"
echo "Staging runner removed. Host marker and physical evidence were preserved."
