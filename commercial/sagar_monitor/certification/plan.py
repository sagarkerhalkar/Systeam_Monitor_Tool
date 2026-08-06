from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Final


@dataclass(frozen=True)
class CertificationStep:
    step_id: str
    title: str
    platform: str
    category: str
    execution: str
    required: bool = True
    attachment_required: bool = False
    minimum_duration_seconds: int = 0


CERTIFICATION_STEPS: Final[tuple[CertificationStep, ...]] = (
    CertificationStep(
        "windows_server_clean_install",
        "Clean Windows commercial server installation",
        "windows",
        "installation",
        "guided",
        attachment_required=True,
    ),
    CertificationStep(
        "ubuntu_server_clean_install",
        "Clean Ubuntu commercial server installation",
        "ubuntu",
        "installation",
        "guided",
        attachment_required=True,
    ),
    CertificationStep(
        "windows_agent_clean_install",
        "Clean Windows commercial agent installation and enrollment",
        "windows",
        "agent",
        "guided",
        attachment_required=True,
    ),
    CertificationStep(
        "ubuntu_agent_clean_install",
        "Clean Ubuntu commercial agent installation and enrollment",
        "ubuntu",
        "agent",
        "guided",
        attachment_required=True,
    ),
    CertificationStep(
        "windows_failed_upgrade_rollback",
        "Windows failed-upgrade rollback restores application, configuration and database",
        "windows",
        "rollback",
        "guided",
        attachment_required=True,
    ),
    CertificationStep(
        "ubuntu_failed_upgrade_rollback",
        "Ubuntu failed-upgrade rollback restores application, configuration and database",
        "ubuntu",
        "rollback",
        "guided",
        attachment_required=True,
    ),
    CertificationStep(
        "windows_abrupt_restart_recovery",
        "Windows abrupt shutdown and restart recovery",
        "windows",
        "recovery",
        "physical",
        attachment_required=True,
    ),
    CertificationStep(
        "ubuntu_abrupt_restart_recovery",
        "Ubuntu abrupt shutdown and restart recovery",
        "ubuntu",
        "recovery",
        "physical",
        attachment_required=True,
    ),
    CertificationStep(
        "windows_offline_queue_replay",
        "Windows agent offline heartbeat and message receipt replay",
        "windows",
        "network",
        "physical",
        attachment_required=True,
    ),
    CertificationStep(
        "ubuntu_offline_queue_replay",
        "Ubuntu agent offline heartbeat and message receipt replay",
        "ubuntu",
        "network",
        "physical",
        attachment_required=True,
    ),
    CertificationStep(
        "server_disk_pressure_recovery",
        "Server low-storage and disk-pressure recovery",
        "cross-platform",
        "storage",
        "physical",
        attachment_required=True,
    ),
    CertificationStep(
        "separate_hardware_restore",
        "Verified backup restore onto separate hardware",
        "cross-platform",
        "backup",
        "physical",
        attachment_required=True,
    ),
    CertificationStep(
        "tls_certificate_renewal",
        "TLS certificate replacement and renewal",
        "cross-platform",
        "tls",
        "guided",
        attachment_required=True,
    ),
    CertificationStep(
        "invalid_tls_rejection",
        "Expired, mismatched or untrusted TLS certificate rejection",
        "cross-platform",
        "tls",
        "guided",
        attachment_required=True,
    ),
    CertificationStep(
        "soak_8_hours",
        "Eight-hour continuous server and agent soak",
        "cross-platform",
        "soak",
        "automated",
        minimum_duration_seconds=8 * 60 * 60,
    ),
    CertificationStep(
        "soak_24_hours",
        "Twenty-four-hour continuous server and agent soak",
        "cross-platform",
        "soak",
        "automated",
        minimum_duration_seconds=24 * 60 * 60,
    ),
    CertificationStep(
        "windows_antivirus_compatibility",
        "Windows Defender or approved antivirus compatibility",
        "windows",
        "security",
        "physical",
        attachment_required=True,
    ),
    CertificationStep(
        "controlled_pilot",
        "Controlled pilot with representative Windows and Ubuntu clients",
        "cross-platform",
        "pilot",
        "physical",
        attachment_required=True,
        minimum_duration_seconds=8 * 60 * 60,
    ),
)

STEP_BY_ID: Final[dict[str, CertificationStep]] = {step.step_id: step for step in CERTIFICATION_STEPS}


def certification_plan_document() -> dict:
    return {
        "schema": "sagar-monitor-physical-certification-plan-v1",
        "required_step_count": sum(1 for step in CERTIFICATION_STEPS if step.required),
        "steps": [asdict(step) for step in CERTIFICATION_STEPS],
    }


def require_step(step_id: str) -> CertificationStep:
    try:
        return STEP_BY_ID[str(step_id)]
    except KeyError as exc:
        raise ValueError(f"unknown certification step: {step_id}") from exc
