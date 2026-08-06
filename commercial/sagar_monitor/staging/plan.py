from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import hashlib
import json


@dataclass(frozen=True)
class HostRole:
    role_id: str
    platform: str
    purpose: str
    minimum_cpu_count: int
    minimum_memory_bytes: int
    minimum_free_disk_bytes: int


GIB = 1024 * 1024 * 1024

HOST_ROLES: tuple[HostRole, ...] = (
    HostRole("windows_server", "windows", "Clean Windows commercial server", 4, 8 * GIB, 50 * GIB),
    HostRole("ubuntu_server", "ubuntu", "Clean Ubuntu commercial server", 4, 8 * GIB, 50 * GIB),
    HostRole("windows_client_1", "windows", "Primary Windows commercial agent", 2, 4 * GIB, 20 * GIB),
    HostRole("windows_client_2", "windows", "Secondary Windows commercial agent", 2, 4 * GIB, 20 * GIB),
    HostRole("ubuntu_client_1", "ubuntu", "Primary Ubuntu commercial agent", 2, 4 * GIB, 20 * GIB),
    HostRole("ubuntu_client_2", "ubuntu", "Secondary Ubuntu commercial agent", 2, 4 * GIB, 20 * GIB),
    HostRole("restore_host", "cross-platform", "Separate restore-verification host", 4, 8 * GIB, 100 * GIB),
)

ROLE_BY_ID = {role.role_id: role for role in HOST_ROLES}
REPOSITORY_FULL_NAME = "sagarkerhalkar/Systeam_Monitor_Tool"
REQUIRED_REPOSITORY_VISIBILITY = "PRIVATE"
REQUIRED_RUNNER_LABELS = ("self-hosted", "sagar-monitor-staging", "commercial-certification")
PRODUCTION_PORT = 2278

WINDOWS_PRODUCTION_MARKERS = (
    r"C:\SagarSystemHealthMonitor",
    r"D:\SagarSystemHealthMonitor",
)
UBUNTU_PRODUCTION_MARKERS = (
    "/opt/SagarSystemHealthMonitor",
    "/var/lib/SagarSystemHealthMonitor",
)


def require_role(role_id: str) -> HostRole:
    try:
        return ROLE_BY_ID[str(role_id).strip()]
    except KeyError as exc:
        raise ValueError(f"unknown staging role: {role_id}") from exc


def staging_plan_document() -> dict[str, Any]:
    document = {
        "schema": "sagar-monitor-staging-lab-plan-v1",
        "repository": REPOSITORY_FULL_NAME,
        "required_repository_visibility": REQUIRED_REPOSITORY_VISIBILITY,
        "required_runner_labels": list(REQUIRED_RUNNER_LABELS),
        "production_port_must_be_unused": PRODUCTION_PORT,
        "hosts": [asdict(role) for role in HOST_ROLES],
        "security": {
            "offline_first": True,
            "runner_registration_requires_private_repository": True,
            "runner_registration_is_ephemeral": True,
            "runner_token_files_are_deleted_after_use": True,
            "production_credentials_are_forbidden": True,
            "production_network_access_is_forbidden": True,
        },
    }
    raw = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    document["plan_sha256"] = hashlib.sha256(raw).hexdigest()
    return document
