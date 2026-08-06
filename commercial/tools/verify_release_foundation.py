#!/usr/bin/env python3
"""Fail CI when the commercial foundation violates release-safety contracts."""

from __future__ import annotations

import json
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


def verify_server_package() -> None:
    required = (
        ROOT / "commercial" / "sagar_monitor" / "server" / "runtime.py",
        ROOT / "commercial" / "sagar_monitor" / "server" / "bootstrap.py",
        ROOT / "commercial" / "sagar_monitor" / "server" / "backup.py",
        ROOT / "commercial" / "sagar_monitor" / "server" / "package.py",
        ROOT / "commercial" / "tools" / "run_commercial_server.py",
        ROOT / "commercial" / "tools" / "build_commercial_server_package.py",
        ROOT / "commercial" / "tools" / "run_physical_certification.py",
        ROOT / "commercial" / "server" / "windows" / "install-commercial-server.ps1",
        ROOT / "commercial" / "server" / "windows" / "uninstall-commercial-server.ps1",
        ROOT / "commercial" / "server" / "windows" / "run-physical-certification.ps1",
        ROOT / "commercial" / "server" / "ubuntu" / "install-commercial-server.sh",
        ROOT / "commercial" / "server" / "ubuntu" / "uninstall-commercial-server.sh",
        ROOT / "commercial" / "server" / "ubuntu" / "run-physical-certification.sh",
        ROOT / "commercial" / "server" / "ubuntu" / "sagar-monitor-commercial-server.service",
    )
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        fail("required commercial server files are missing: " + ", ".join(missing))

    config_path = ROOT / "commercial" / "server" / "server-config.example.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("allow_loopback_http") is not False:
        fail("commercial server example must require HTTPS")
    if not config.get("certificate_file") or not config.get("private_key_file"):
        fail("commercial server example must declare certificate and private key paths")

    runtime = (ROOT / "commercial" / "sagar_monitor" / "server" / "runtime.py").read_text(encoding="utf-8")
    for marker in ("ssl.PROTOCOL_TLS_SERVER", "TLSv1_2", "Strict-Transport-Security"):
        if marker not in runtime:
            fail(f"commercial server runtime is missing security marker: {marker}")

    windows = (ROOT / "commercial" / "server" / "windows" / "install-commercial-server.ps1").read_text(encoding="utf-8")
    ubuntu = (ROOT / "commercial" / "server" / "ubuntu" / "install-commercial-server.sh").read_text(encoding="utf-8")
    service = (ROOT / "commercial" / "server" / "ubuntu" / "sagar-monitor-commercial-server.service").read_text(encoding="utf-8")
    for marker in ("pre-upgrade-", ".bootstrap-password", "DatabaseExistedBefore"):
        if marker not in windows:
            fail(f"Windows server installer is missing rollback marker: {marker}")
    for marker in ("pre-upgrade-", ".bootstrap-password", "DATABASE_EXISTED_BEFORE"):
        if marker not in ubuntu:
            fail(f"Ubuntu server installer is missing rollback marker: {marker}")
    for marker in ("NoNewPrivileges=true", "ProtectSystem=strict", "ReadWritePaths="):
        if marker not in service:
            fail(f"Ubuntu server service is missing hardening marker: {marker}")


def verify_qualification_gate() -> None:
    required = (
        ROOT / "commercial" / "sagar_monitor" / "qualification" / "scenario.py",
        ROOT / "commercial" / "sagar_monitor" / "qualification" / "recovery.py",
        ROOT / "commercial" / "tools" / "run_staging_qualification.py",
        ROOT / "commercial" / "tests" / "test_staging_qualification.py",
        ROOT / ".github" / "workflows" / "commercial-staging-qualification.yml",
    )
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        fail("required staging qualification files are missing: " + ", ".join(missing))

    scenario = required[0].read_text(encoding="utf-8")
    for marker in (
        "duplicate_replay_idempotent",
        "restore_counts_match",
        "wal_checkpoint_not_busy",
        "max_heartbeat_p95_ms",
        "evidence_sha256",
    ):
        if marker not in scenario:
            fail(f"qualification scenario is missing release marker: {marker}")

    recovery = required[1].read_text(encoding="utf-8")
    for marker in ("process.terminate()", "/api/v1/agents/status", "PRAGMA quick_check"):
        if marker not in recovery:
            fail(f"forced recovery probe is missing marker: {marker}")

    workflow = required[4].read_text(encoding="utf-8")
    for marker in ("--agents 100,500,1000", "actions/upload-artifact@v4", "--max-admin-p95-ms 300"):
        if marker not in workflow:
            fail(f"qualification workflow is missing release marker: {marker}")


def verify_physical_certification_gate() -> None:
    required = (
        ROOT / "commercial" / "sagar_monitor" / "certification" / "plan.py",
        ROOT / "commercial" / "sagar_monitor" / "certification" / "evidence.py",
        ROOT / "commercial" / "sagar_monitor" / "certification" / "probes.py",
        ROOT / "commercial" / "sagar_monitor" / "certification" / "cli.py",
        ROOT / "commercial" / "tests" / "test_physical_certification.py",
        ROOT / ".github" / "workflows" / "commercial-physical-certification.yml",
        ROOT / "docs" / "PHYSICAL_STAGING_CERTIFICATION_V1.md",
    )
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        fail("required physical certification files are missing: " + ", ".join(missing))

    plan = required[0].read_text(encoding="utf-8")
    for marker in (
        "windows_server_clean_install",
        "ubuntu_server_clean_install",
        "windows_failed_upgrade_rollback",
        "ubuntu_failed_upgrade_rollback",
        "soak_8_hours",
        "soak_24_hours",
        "controlled_pilot",
    ):
        if marker not in plan:
            fail(f"physical certification plan is missing required step: {marker}")

    evidence = required[1].read_text(encoding="utf-8")
    for marker in (
        "attachment hash changed",
        "approver must be different from the original operator",
        "finalized certification evidence cannot be modified",
        "ledger_sha256",
        "event_sha256",
    ):
        if marker not in evidence:
            fail(f"physical certification ledger is missing safety marker: {marker}")

    probes = required[2].read_text(encoding="utf-8")
    for marker in (
        "physical certification requires an HTTPS server URL",
        "PRAGMA quick_check",
        "certificate_sha256",
        "run_https_soak",
    ):
        if marker not in probes:
            fail(f"physical certification probes are missing marker: {marker}")

    workflow = required[5].read_text(encoding="utf-8")
    for marker in (
        "workflow_dispatch",
        "sagar-monitor-staging",
        "STAGING_CA_BUNDLE_PEM",
        "retention-days: 90",
    ):
        if marker not in workflow:
            fail(f"physical certification workflow is missing marker: {marker}")


def main() -> int:
    verify_no_payload_injection()
    verify_migrations()
    verify_required_identity_files()
    verify_server_package()
    verify_qualification_gate()
    verify_physical_certification_gate()
    print("Commercial release foundation verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
