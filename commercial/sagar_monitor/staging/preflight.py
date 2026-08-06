from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import ctypes
import hashlib
import json
import os
import platform
import secrets
import shutil
import socket

from .plan import (
    PRODUCTION_PORT,
    UBUNTU_PRODUCTION_MARKERS,
    WINDOWS_PRODUCTION_MARKERS,
    require_role,
    staging_plan_document,
)


MARKER_SCHEMA = "sagar-monitor-staging-host-marker-v1"
RECEIPT_SCHEMA = "sagar-monitor-staging-runner-receipt-v1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _hash_document(document: Mapping[str, Any], field: str) -> str:
    copy = dict(document)
    copy.pop(field, None)
    return hashlib.sha256(_canonical(copy)).hexdigest()


def _memory_bytes() -> int | None:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        try:
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_physical)
        except (AttributeError, OSError):
            return None
    try:
        return int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
    except (AttributeError, OSError, ValueError):
        return None


def is_elevated() -> bool:
    if os.name == "nt":
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            return False
    return hasattr(os, "geteuid") and os.geteuid() == 0


def normalized_platform() -> str:
    value = platform.system().lower()
    if value == "windows":
        return "windows"
    if value == "linux":
        return "ubuntu"
    return value


def _port_is_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("127.0.0.1", int(port)))
        except OSError:
            return False
    return True


def _marker_paths(platform_name: str) -> tuple[str, ...]:
    return WINDOWS_PRODUCTION_MARKERS if platform_name == "windows" else UBUNTU_PRODUCTION_MARKERS


def _machine_snapshot(work_root: Path) -> dict[str, Any]:
    usage = shutil.disk_usage(work_root if work_root.exists() else work_root.parent)
    return {
        "captured_at": _utc_now(),
        "hostname": socket.gethostname(),
        "platform": normalized_platform(),
        "platform_release": platform.release(),
        "machine": platform.machine(),
        "python_version": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "memory_bytes": _memory_bytes(),
        "disk_total_bytes": int(usage.total),
        "disk_free_bytes": int(usage.free),
        "work_root": str(work_root),
        "elevated": is_elevated(),
    }


def preflight_host(*, role_id: str, work_root: str | Path, phase: str = "clean") -> dict[str, Any]:
    role = require_role(role_id)
    phase_value = str(phase).lower().strip()
    if phase_value not in {"clean", "installed"}:
        raise ValueError("phase must be clean or installed")
    root = Path(work_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    snapshot = _machine_snapshot(root)
    actual_platform = str(snapshot["platform"])
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: Any) -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    platform_ok = role.platform == "cross-platform" or role.platform == actual_platform
    add("role_platform", platform_ok, {"required": role.platform, "actual": actual_platform})
    add("administrator_or_root", bool(snapshot["elevated"]), snapshot["elevated"])

    cpu_count = int(snapshot["cpu_count"] or 0)
    add("minimum_cpu", cpu_count >= role.minimum_cpu_count, {"minimum": role.minimum_cpu_count, "actual": cpu_count})

    memory = int(snapshot["memory_bytes"] or 0)
    add("minimum_memory", memory >= role.minimum_memory_bytes, {"minimum_bytes": role.minimum_memory_bytes, "actual_bytes": memory})
    free_disk = int(snapshot["disk_free_bytes"])
    add("minimum_free_disk", free_disk >= role.minimum_free_disk_bytes, {"minimum_bytes": role.minimum_free_disk_bytes, "actual_bytes": free_disk})

    marker_paths = []
    for raw in _marker_paths(actual_platform):
        candidate = Path(raw)
        if candidate.exists():
            marker_paths.append(str(candidate))
    add("no_known_production_paths", not marker_paths, marker_paths)

    port_free = _port_is_free(PRODUCTION_PORT) if phase_value == "clean" else True
    add("production_port_unused", port_free, {"port": PRODUCTION_PORT, "phase": phase_value, "checked": phase_value == "clean"})

    result = {
        "schema": "sagar-monitor-staging-host-preflight-v1",
        "captured_at": _utc_now(),
        "role": role.role_id,
        "phase": phase_value,
        "snapshot": snapshot,
        "checks": checks,
        "ok": all(bool(item["ok"]) for item in checks),
        "plan_sha256": staging_plan_document()["plan_sha256"],
    }
    result["preflight_sha256"] = _hash_document(result, "preflight_sha256")
    return result


def write_json(path: str | Path, document: Mapping[str, Any]) -> Path:
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(dict(document), ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    return destination


def create_host_marker(path: str | Path, *, role_id: str, site: str, operator: str, preflight: Mapping[str, Any]) -> Path:
    if not bool(preflight.get("ok")):
        raise RuntimeError("staging host marker cannot be created from a failed preflight")
    destination = Path(path).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"staging host marker already exists: {destination}")
    role = require_role(role_id)
    site_value = str(site or "").strip()
    operator_value = str(operator or "").strip()
    if not site_value or not operator_value:
        raise ValueError("site and operator are required")
    snapshot = preflight.get("snapshot")
    if not isinstance(snapshot, Mapping):
        raise ValueError("preflight snapshot is missing")
    document: dict[str, Any] = {
        "schema": MARKER_SCHEMA,
        "role": role.role_id,
        "platform": snapshot.get("platform"),
        "hostname": snapshot.get("hostname"),
        "site": site_value[:160],
        "operator": operator_value[:160],
        "created_at": _utc_now(),
        "nonce": secrets.token_hex(32),
        "plan_sha256": preflight.get("plan_sha256"),
        "preflight_sha256": preflight.get("preflight_sha256"),
    }
    document["marker_sha256"] = _hash_document(document, "marker_sha256")
    return write_json(destination, document)


def load_and_verify_marker(path: str | Path, *, expected_role: str | None = None) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    try:
        document = json.loads(source.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise RuntimeError(f"cannot read staging marker: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("staging marker is not valid JSON") from exc
    if not isinstance(document, dict) or document.get("schema") != MARKER_SCHEMA:
        raise RuntimeError("unsupported staging marker schema")
    if document.get("marker_sha256") != _hash_document(document, "marker_sha256"):
        raise RuntimeError("staging marker SHA-256 mismatch")
    require_role(str(document.get("role") or ""))
    if expected_role and document.get("role") != expected_role:
        raise RuntimeError(f"staging marker role mismatch: expected {expected_role}")
    return document


def create_runner_receipt(path: str | Path, *, marker_path: str | Path, repository: str, platform_name: str, runner_name: str) -> Path:
    marker = load_and_verify_marker(marker_path)
    platform_value = str(platform_name).lower().strip()
    if platform_value not in {"windows", "ubuntu"}:
        raise ValueError("runner receipt platform must be windows or ubuntu")
    if marker.get("platform") != platform_value and marker.get("role") != "restore_host":
        raise RuntimeError("runner receipt platform does not match the staging marker")
    repository_value = str(repository or "").strip()
    runner_value = str(runner_name or "").strip()
    if not repository_value or not runner_value:
        raise ValueError("repository and runner_name are required")
    document: dict[str, Any] = {
        "schema": RECEIPT_SCHEMA,
        "repository": repository_value,
        "repository_visibility": "PRIVATE",
        "platform": platform_value,
        "runner_name": runner_value[:160],
        "ephemeral": True,
        "labels": ["sagar-monitor-staging", "commercial-certification"],
        "marker_sha256": marker.get("marker_sha256"),
        "created_at": _utc_now(),
    }
    document["receipt_sha256"] = _hash_document(document, "receipt_sha256")
    return write_json(path, document)


def verify_runner_receipt(path: str | Path, *, marker_path: str | Path, repository: str, platform_name: str) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    marker = load_and_verify_marker(marker_path)
    try:
        document = json.loads(source.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise RuntimeError(f"cannot read runner receipt: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("runner receipt is not valid JSON") from exc
    if not isinstance(document, dict) or document.get("schema") != RECEIPT_SCHEMA:
        raise RuntimeError("unsupported runner receipt schema")
    errors: list[str] = []
    if str(document.get("repository") or "") != str(repository):
        errors.append("runner receipt repository mismatch")
    if str(document.get("platform") or "") != str(platform_name):
        errors.append("runner receipt platform mismatch")
    if document.get("repository_visibility") != "PRIVATE":
        errors.append("runner receipt does not prove a private repository")
    if document.get("ephemeral") is not True:
        errors.append("runner receipt is not ephemeral")
    if document.get("marker_sha256") != marker.get("marker_sha256"):
        errors.append("runner receipt marker mismatch")
    if document.get("receipt_sha256") != _hash_document(document, "receipt_sha256"):
        errors.append("runner receipt SHA-256 mismatch")
    return {"ok": not errors, "errors": errors, "receipt": document, "marker": marker}
