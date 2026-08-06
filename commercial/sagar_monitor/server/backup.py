from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import json
import os
import shutil
import sqlite3
import tempfile


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_path(database_backup: Path) -> Path:
    return database_backup.with_name(database_backup.name + ".manifest.json")


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _quick_check(path: Path) -> str:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=10.0)
    try:
        return str(connection.execute("PRAGMA quick_check").fetchone()[0])
    finally:
        connection.close()


def backup_database(source_path: str | Path, destination_path: str | Path) -> dict[str, Any]:
    """Create a consistent online SQLite backup with a signed-by-hash manifest."""
    source = Path(source_path).expanduser().resolve()
    destination = Path(destination_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"source database does not exist: {source}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=destination.name + ".", suffix=".tmp", dir=destination.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    temporary.unlink(missing_ok=True)
    source_connection = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=30.0)
    target_connection = sqlite3.connect(temporary, timeout=30.0)
    try:
        source_connection.execute("PRAGMA busy_timeout=30000")
        source_connection.backup(target_connection, pages=1000, sleep=0.05)
        target_connection.commit()
    finally:
        target_connection.close()
        source_connection.close()
    try:
        integrity = _quick_check(temporary)
        if integrity.lower() != "ok":
            raise RuntimeError(f"backup integrity check failed: {integrity}")
        created_at = _utc_now()
        manifest = {
            "format": "sagar-monitor-sqlite-backup-v1",
            "created_at": created_at,
            "source_name": source.name,
            "backup_name": destination.name,
            "size_bytes": temporary.stat().st_size,
            "sha256": _sha256(temporary),
            "quick_check": integrity,
        }
        os.replace(temporary, destination)
        _atomic_json(_manifest_path(destination), manifest)
        return {"database": str(destination), "manifest": str(_manifest_path(destination)), **manifest}
    finally:
        temporary.unlink(missing_ok=True)


def verify_backup(database_backup: str | Path) -> dict[str, Any]:
    backup = Path(database_backup).expanduser().resolve()
    manifest_path = _manifest_path(backup)
    if not backup.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("backup database or manifest is missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("backup manifest is invalid") from exc
    if not isinstance(manifest, dict) or manifest.get("format") != "sagar-monitor-sqlite-backup-v1":
        raise RuntimeError("unsupported backup manifest format")
    actual_size = backup.stat().st_size
    actual_hash = _sha256(backup)
    if int(manifest.get("size_bytes") or -1) != actual_size:
        raise RuntimeError("backup size does not match its manifest")
    if str(manifest.get("sha256") or "") != actual_hash:
        raise RuntimeError("backup SHA-256 does not match its manifest")
    integrity = _quick_check(backup)
    if integrity.lower() != "ok":
        raise RuntimeError(f"backup integrity check failed: {integrity}")
    return {"ok": True, "database": str(backup), "manifest": str(manifest_path), **manifest}


def restore_database(
    database_backup: str | Path,
    target_path: str | Path,
    *,
    pre_restore_directory: str | Path | None = None,
    service_stopped: bool = False,
) -> dict[str, Any]:
    """Restore only after explicit service-stop confirmation and preserve the old database."""
    if not service_stopped:
        raise RuntimeError("restore requires explicit confirmation that the server service is stopped")
    backup = Path(database_backup).expanduser().resolve()
    target = Path(target_path).expanduser().resolve()
    verification = verify_backup(backup)
    target.parent.mkdir(parents=True, exist_ok=True)
    pre_restore: dict[str, Any] | None = None
    if target.exists():
        directory = (
            Path(pre_restore_directory).expanduser().resolve()
            if pre_restore_directory is not None
            else target.parent / "pre-restore"
        )
        directory.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        pre_restore = backup_database(target, directory / f"{target.stem}-{stamp}.db")
    descriptor, temporary_name = tempfile.mkstemp(prefix=target.name + ".", suffix=".restore", dir=target.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(backup, temporary)
        if _sha256(temporary) != verification["sha256"]:
            raise RuntimeError("restored temporary copy failed SHA-256 verification")
        integrity = _quick_check(temporary)
        if integrity.lower() != "ok":
            raise RuntimeError(f"restored temporary copy failed integrity check: {integrity}")
        os.replace(temporary, target)
        for suffix in ("-wal", "-shm"):
            Path(str(target) + suffix).unlink(missing_ok=True)
        return {
            "ok": True,
            "target": str(target),
            "restored_from": str(backup),
            "sha256": verification["sha256"],
            "pre_restore_backup": pre_restore,
        }
    finally:
        temporary.unlink(missing_ok=True)
