#!/usr/bin/env bash
set -euo pipefail

TARGET_REPOSITORY="${1:-}"
EXPECTED_SOURCE_COMMIT="${2:-}"
SOURCE_REPOSITORY="${SOURCE_REPOSITORY:-sagarkerhalkar/Systeam_Monitor_Tool}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="${REPOSITORY_ROOT:-$(cd -- "$SCRIPT_DIR/../../.." && pwd)}"
REPORT_PATH="${REPORT_PATH:-/var/lib/sagar-monitor-staging/private-mirror-report.json}"
PYTHON_EXE="${PYTHON_EXE:-python3}"
DRY_RUN="${DRY_RUN:-0}"
CLI="$REPOSITORY_ROOT/commercial/tools/run_staging_lab.py"

[[ "$TARGET_REPOSITORY" == */* ]] || { echo "Usage: $0 owner/private-repo <40-char-commercial-v1-sha>" >&2; exit 2; }
[[ "$EXPECTED_SOURCE_COMMIT" =~ ^[0-9a-fA-F]{40}$ ]] || { echo "A full 40-character source commit SHA is required" >&2; exit 2; }
[[ -f "$CLI" ]] || { echo "Staging CLI is missing: $CLI" >&2; exit 2; }

mkdir -p "$(dirname -- "$REPORT_PATH")"
arguments=(
  "$CLI" private-mirror-sync
  --repository-root "$REPOSITORY_ROOT"
  --source-repository "$SOURCE_REPOSITORY"
  --target-repository "$TARGET_REPOSITORY"
  --expected-source-commit "$EXPECTED_SOURCE_COMMIT"
  --output "$REPORT_PATH"
)
[[ "$DRY_RUN" == "1" ]] && arguments+=(--dry-run)

PYTHONPATH="$REPOSITORY_ROOT/commercial" "$PYTHON_EXE" "${arguments[@]}"
printf 'Private staging mirror verification report: %s\n' "$REPORT_PATH"
echo 'No production deployment was performed.'