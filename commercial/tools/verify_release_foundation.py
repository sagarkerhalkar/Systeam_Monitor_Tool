#!/usr/bin/env python3
"""Fail CI when the commercial foundation violates release-safety contracts."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
MIGRATION_DIR = ROOT / "commercial" / "migrations"

FORBIDDEN_TRANSFER_PATHS = (
    ROOT / ".github" / "commercial_identity_full",
    ROOT / ".github" / "commercial_identity_payload",
    ROOT / ".github" / "commercial_identity_small",
)

FORBIDDEN_WORKFLOW_MARKERS = (
    "git apply",
    ".b64",
    "base64 --decode",
    "commercial_identity_payload",
)

FORBIDDEN_MIGRATION_PATTERNS = (
    re.compile(r"\bDROP\s+TABLE\b", re.IGNORECASE),
    re.compile(r"\bDELETE\s+FROM\s+(latest|heartbeats)\b", re.IGNORECASE),
    re.compile(r"\bTRUNCATE\s+(TABLE\s+)?(latest|heartbeats)\b", re.IGNORECASE),
)


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def verify_no_payload_injection() -> None:
    present = [str(path.relative_to(ROOT)) for path in FORBIDDEN_TRANSFER_PATHS if path.exists()]
    if present:
        fail("patch-transfer directories are forbidden: " + ", ".join(present))

    for workflow in sorted(WORKFLOW_DIR.glob("*.yml")) + sorted(WORKFLOW_DIR.glob("*.yaml")):
        text = workflow.read_text(encoding="utf-8", errors="strict").lower()
        markers = [marker for marker in FORBIDDEN_WORKFLOW_MARKERS if marker in text]
        if markers:
            fail(
                f"{workflow.relative_to(ROOT)} contains forbidden patch-injection markers: "
                + ", ".join(markers)
            )


def verify_migrations() -> None:
    migrations = sorted(MIGRATION_DIR.glob("*.sql"))
    if not migrations:
        fail("no commercial database migrations were found")

    versions: list[int] = []
    for migration in migrations:
        match = re.match(r"^(\d{4})_[a-z0-9_]+\.sql$", migration.name)
        if not match:
            fail(f"migration name is not versioned correctly: {migration.name}")
        versions.append(int(match.group(1)))

        sql = migration.read_text(encoding="utf-8", errors="strict")
        for pattern in FORBIDDEN_MIGRATION_PATTERNS:
            if pattern.search(sql):
                fail(f"destructive production-data statement found in {migration.name}")

    if len(versions) != len(set(versions)):
        fail("duplicate migration version detected")
    if versions != sorted(versions):
        fail("migration versions are not ordered")


def verify_required_identity_files() -> None:
    required = (
        ROOT / "commercial" / "sagar_monitor" / "identity" / "resolver.py",
        ROOT / "commercial" / "tests" / "test_identity_resolver.py",
        ROOT / "commercial" / "migrations" / "0001_agent_identity.sql",
    )
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        fail("required identity foundation files are missing: " + ", ".join(missing))


def main() -> int:
    verify_no_payload_injection()
    verify_migrations()
    verify_required_identity_files()
    print("Commercial release foundation verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
