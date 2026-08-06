#!/usr/bin/env bash
set -euo pipefail

REPOSITORY="${1:-}"
REGISTRATION_TOKEN_FILE="${2:-}"
RUNNER_ARCHIVE="${3:-}"
RUNNER_ARCHIVE_SHA256="${4:-}"
RUNNER_NAME="${5:-$(hostname)-sagar-staging}"
INSTALL_ROOT="${6:-/opt/actions-runner-sagar-staging}"
WORK_ROOT="${7:-/var/lib/sagar-monitor-staging}"
PYTHON_EXE="${PYTHON_EXE:-python3}"
GH_EXE="${GH_EXE:-gh}"
RUNNER_USER="sagar-staging-runner"
STAGING_GROUP="sagar-monitor-staging"

[[ "$(id -u)" -eq 0 ]] || { echo "Run runner installation as root" >&2; exit 2; }
[[ "$REPOSITORY" == */* ]] || { echo "Repository must be in owner/name form" >&2; exit 2; }
[[ "$RUNNER_ARCHIVE_SHA256" =~ ^[0-9a-fA-F]{64}$ ]] || { echo "A 64-character runner archive SHA-256 is required" >&2; exit 2; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
COMMERCIAL_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
CLI="$COMMERCIAL_ROOT/tools/run_staging_lab.py"
MARKER="$WORK_ROOT/host-marker.json"
RECEIPT="$WORK_ROOT/runner-receipt.json"

for required in "$CLI" "$MARKER" "$REGISTRATION_TOKEN_FILE" "$RUNNER_ARCHIVE"; do
  [[ -f "$required" ]] || { echo "Required file is missing: $required" >&2; exit 2; }
done
[[ ! -e "$INSTALL_ROOT" ]] || { echo "Runner installation directory already exists: $INSTALL_ROOT" >&2; exit 2; }

cleanup_token() {
  if [[ -f "$REGISTRATION_TOKEN_FILE" ]]; then
    if command -v shred >/dev/null 2>&1; then
      shred -u "$REGISTRATION_TOKEN_FILE" || rm -f "$REGISTRATION_TOKEN_FILE"
    else
      rm -f "$REGISTRATION_TOKEN_FILE"
    fi
  fi
}
trap cleanup_token EXIT

PYTHONPATH="$COMMERCIAL_ROOT" "$PYTHON_EXE" "$CLI" repository-check \
  --repository "$REPOSITORY" \
  --gh-executable "$GH_EXE"

PYTHONPATH="$COMMERCIAL_ROOT" "$PYTHON_EXE" "$CLI" verify-marker --marker "$MARKER"

ACTUAL_SHA256="$(sha256sum "$RUNNER_ARCHIVE" | awk '{print tolower($1)}')"
[[ "$ACTUAL_SHA256" == "${RUNNER_ARCHIVE_SHA256,,}" ]] || {
  echo "Runner archive SHA-256 mismatch. Expected $RUNNER_ARCHIVE_SHA256 but got $ACTUAL_SHA256" >&2
  exit 2
}

getent group "$STAGING_GROUP" >/dev/null || groupadd --system "$STAGING_GROUP"
if ! id "$RUNNER_USER" >/dev/null 2>&1; then
  useradd --system --create-home --home-dir "/home/$RUNNER_USER" --shell /bin/bash "$RUNNER_USER"
fi
usermod -a -G "$STAGING_GROUP" "$RUNNER_USER"
chown root:"$STAGING_GROUP" "$WORK_ROOT" "$MARKER"
chmod 0750 "$WORK_ROOT"
chmod 0640 "$MARKER"

install -d -m 0755 -o "$RUNNER_USER" -g "$RUNNER_USER" "$INSTALL_ROOT"
tar -xzf "$RUNNER_ARCHIVE" -C "$INSTALL_ROOT"
chown -R "$RUNNER_USER":"$RUNNER_USER" "$INSTALL_ROOT"
[[ -x "$INSTALL_ROOT/config.sh" ]] || { echo "The supplied archive is not a Linux GitHub Actions runner package" >&2; exit 2; }

TOKEN="$(tr -d '\r\n' <"$REGISTRATION_TOKEN_FILE")"
[[ -n "$TOKEN" ]] || { echo "Runner registration token file is empty" >&2; exit 2; }

runuser -u "$RUNNER_USER" -- "$INSTALL_ROOT/config.sh" \
  --unattended \
  --url "https://github.com/$REPOSITORY" \
  --token "$TOKEN" \
  --name "$RUNNER_NAME" \
  --labels "sagar-monitor-staging,commercial-certification" \
  --work "_work" \
  --replace \
  --ephemeral
TOKEN=""

"$INSTALL_ROOT/svc.sh" install "$RUNNER_USER"
"$INSTALL_ROOT/svc.sh" start

if [[ -d /etc/needrestart/conf.d ]]; then
  printf '%s\n' "\$nrconf{override_rc}{qr(^actions\\.runner\\..+\\.service\$)} = 0;" \
    >/etc/needrestart/conf.d/actions_runner_services.conf
fi

PYTHONPATH="$COMMERCIAL_ROOT" "$PYTHON_EXE" "$CLI" write-runner-receipt \
  --receipt "$RECEIPT" \
  --marker "$MARKER" \
  --repository "$REPOSITORY" \
  --platform ubuntu \
  --runner-name "$RUNNER_NAME"

chown root:"$STAGING_GROUP" "$RECEIPT"
chmod 0640 "$RECEIPT"

PYTHONPATH="$COMMERCIAL_ROOT" "$PYTHON_EXE" "$CLI" verify-runner-receipt \
  --receipt "$RECEIPT" \
  --marker "$MARKER" \
  --repository "$REPOSITORY" \
  --platform ubuntu

echo "Ephemeral staging runner installed: $RUNNER_NAME"
echo "Receipt: $RECEIPT"
echo "The runner will unregister after one workflow job. Reinstall it before another physical-certification job."
