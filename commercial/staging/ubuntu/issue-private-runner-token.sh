#!/usr/bin/env bash
set -euo pipefail

TARGET_REPOSITORY="${1:-}"
OUTPUT_PATH="${2:-}"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="${REPOSITORY_ROOT:-$(cd -- "$SCRIPT_DIR/../../.." && pwd)}"
PYTHON_EXE="${PYTHON_EXE:-python3}"
CLI="$REPOSITORY_ROOT/commercial/tools/run_staging_lab.py"

[[ "$TARGET_REPOSITORY" == */* ]] || { echo "Usage: $0 owner/private-repo /secure/path/runner-token.txt" >&2; exit 2; }
[[ -n "$OUTPUT_PATH" ]] || { echo "A runner token output path is required" >&2; exit 2; }
[[ -f "$CLI" ]] || { echo "Staging CLI is missing: $CLI" >&2; exit 2; }

PYTHONPATH="$REPOSITORY_ROOT/commercial" "$PYTHON_EXE" "$CLI" issue-runner-token \
  --repository "$TARGET_REPOSITORY" \
  --output "$OUTPUT_PATH" \
  --repository-root "$REPOSITORY_ROOT"
chmod 0600 "$OUTPUT_PATH" 2>/dev/null || true
printf 'Runner token written to protected file: %s\n' "$OUTPUT_PATH"
echo 'The token value was not printed. Delete the file immediately after runner registration.'