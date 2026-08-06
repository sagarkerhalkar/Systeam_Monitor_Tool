from __future__ import annotations

from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import hashlib
import json
import os
import re
import tempfile

from sagar_monitor.server.package import build_source_package, verify_source_package
from .plan import staging_plan_document


_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{7,64}$")
_FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entry(name: str, data: bytes, mode: int = 0o644) -> tuple[str, bytes, int]:
    return name, data, mode


def build_release_candidate(repository_root: str | Path, output_path: str | Path, *, version: str, source_commit: str) -> dict[str, Any]:
    root = Path(repository_root).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    version_value = str(version or "").strip()
    commit_value = str(source_commit or "").strip().lower()
    if not _VERSION_RE.fullmatch(version_value):
        raise ValueError("version must contain only letters, numbers, dot, underscore and hyphen")
    if not _COMMIT_RE.fullmatch(commit_value):
        raise ValueError("source_commit must be a hexadecimal Git commit SHA")

    runbook_path = root / "docs" / "STAGING_LAB_BOOTSTRAP_V1.md"
    if not runbook_path.is_file():
        raise FileNotFoundError(f"staging runbook is missing: {runbook_path}")

    output.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"sagar-monitor-staging-rc-{version_value}"
    with TemporaryDirectory(dir=output.parent) as temporary_directory:
        server_package = Path(temporary_directory) / "commercial-server.zip"
        server_result = build_source_package(root, server_package, version=version_value)
        server_bytes = server_package.read_bytes()
        plan = staging_plan_document()
        plan_data = json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("utf-8")
        runbook_data = runbook_path.read_bytes()
        readme = (
            "Sagar Monitor Commercial Staging Release Candidate\n"
            "This archive contains no registration tokens, passwords, certificates or production data.\n"
            "Read STAGING-LAB-RUNBOOK.md before preparing any machine.\n"
            "Run commercial/tools/run_staging_lab.py verify-rc before extraction or installation.\n"
        ).encode("utf-8")
        manifest = {
            "format": "sagar-monitor-commercial-staging-rc-v1",
            "version": version_value,
            "source_commit": commit_value,
            "created_at": "2026-01-01T00:00:00+00:00",
            "server_package": {
                "path": "commercial-server.zip",
                "size_bytes": len(server_bytes),
                "sha256": _sha256_bytes(server_bytes),
                "verified_file_count": int(server_result["file_count"]),
            },
            "staging_plan": {
                "path": "STAGING-PLAN.json",
                "size_bytes": len(plan_data),
                "sha256": _sha256_bytes(plan_data),
                "plan_sha256": plan["plan_sha256"],
            },
            "runbook": {
                "path": "STAGING-LAB-RUNBOOK.md",
                "size_bytes": len(runbook_data),
                "sha256": _sha256_bytes(runbook_data),
            },
            "contains_secrets": False,
            "production_deployment_authorized": False,
        }
        manifest_data = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode("utf-8")
        entries = [
            _entry(f"{prefix}/commercial-server.zip", server_bytes),
            _entry(f"{prefix}/STAGING-PLAN.json", plan_data),
            _entry(f"{prefix}/STAGING-LAB-RUNBOOK.md", runbook_data),
            _entry(f"{prefix}/README.txt", readme),
            _entry(f"{prefix}/RC-MANIFEST.json", manifest_data),
        ]

        descriptor, temporary_name = tempfile.mkstemp(prefix=output.name + ".", suffix=".tmp", dir=output.parent)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
                for name, data, mode in sorted(entries, key=lambda item: item[0]):
                    info = ZipInfo(name, _FIXED_TIME)
                    info.compress_type = ZIP_DEFLATED
                    info.create_system = 3
                    info.external_attr = (mode & 0xFFFF) << 16
                    archive.writestr(info, data)
            os.replace(temporary, output)
        finally:
            temporary.unlink(missing_ok=True)

    verification = verify_release_candidate(output)
    return {
        "ok": True,
        "package": str(output),
        "sha256": _sha256_file(output),
        "size_bytes": output.stat().st_size,
        "version": version_value,
        "source_commit": commit_value,
        "server_file_count": verification["server_file_count"],
    }


def verify_release_candidate(package_path: str | Path) -> dict[str, Any]:
    package = Path(package_path).expanduser().resolve()
    if not package.is_file():
        raise FileNotFoundError(f"release candidate does not exist: {package}")
    with ZipFile(package, "r") as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError("release candidate contains duplicate entries")
        for name in names:
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts or "" in pure.parts:
                raise RuntimeError(f"unsafe release-candidate path: {name}")
        manifest_names = [name for name in names if name.endswith("/RC-MANIFEST.json")]
        if len(manifest_names) != 1:
            raise RuntimeError("release candidate must contain exactly one RC manifest")
        manifest_name = manifest_names[0]
        prefix = manifest_name[: -len("RC-MANIFEST.json")]
        manifest = json.loads(archive.read(manifest_name).decode("utf-8"))
        if manifest.get("format") != "sagar-monitor-commercial-staging-rc-v1":
            raise RuntimeError("unsupported staging release-candidate format")
        if manifest.get("contains_secrets") is not False:
            raise RuntimeError("release candidate secret declaration is invalid")
        if manifest.get("production_deployment_authorized") is not False:
            raise RuntimeError("release candidate must not authorize production deployment")

        expected_names = {
            prefix + "commercial-server.zip",
            prefix + "STAGING-PLAN.json",
            prefix + "STAGING-LAB-RUNBOOK.md",
            prefix + "README.txt",
            manifest_name,
        }
        if set(names) != expected_names:
            raise RuntimeError("release candidate contains undeclared files")

        server_data = archive.read(prefix + "commercial-server.zip")
        server_item = manifest.get("server_package") or {}
        if len(server_data) != int(server_item.get("size_bytes") or -1):
            raise RuntimeError("nested commercial-server package size mismatch")
        if _sha256_bytes(server_data) != str(server_item.get("sha256") or ""):
            raise RuntimeError("nested commercial-server package SHA-256 mismatch")

        plan_data = archive.read(prefix + "STAGING-PLAN.json")
        plan_item = manifest.get("staging_plan") or {}
        if len(plan_data) != int(plan_item.get("size_bytes") or -1):
            raise RuntimeError("staging plan size mismatch")
        if _sha256_bytes(plan_data) != str(plan_item.get("sha256") or ""):
            raise RuntimeError("staging plan SHA-256 mismatch")
        plan = json.loads(plan_data.decode("utf-8"))
        if plan.get("plan_sha256") != plan_item.get("plan_sha256"):
            raise RuntimeError("staging plan identity mismatch")

        runbook_data = archive.read(prefix + "STAGING-LAB-RUNBOOK.md")
        runbook_item = manifest.get("runbook") or {}
        if len(runbook_data) != int(runbook_item.get("size_bytes") or -1):
            raise RuntimeError("staging runbook size mismatch")
        if _sha256_bytes(runbook_data) != str(runbook_item.get("sha256") or ""):
            raise RuntimeError("staging runbook SHA-256 mismatch")

        with TemporaryDirectory() as directory:
            nested = Path(directory) / "commercial-server.zip"
            nested.write_bytes(server_data)
            nested_result = verify_source_package(nested)

        return {
            "ok": True,
            "package": str(package),
            "sha256": _sha256_file(package),
            "version": str(manifest.get("version") or ""),
            "source_commit": str(manifest.get("source_commit") or ""),
            "server_file_count": int(nested_result["file_count"]),
            "plan_sha256": str(plan.get("plan_sha256") or ""),
            "runbook_sha256": str(runbook_item.get("sha256") or ""),
        }
