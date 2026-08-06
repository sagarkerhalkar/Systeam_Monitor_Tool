from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import json
import os
import sqlite3
import ssl

from .bootstrap import migration_status
from .config import ServerConfig


def local_health(config: ServerConfig) -> dict[str, Any]:
    issues: list[str] = []
    migrations = migration_status(config.database_path)
    quick_check = "missing"
    active_admins = 0
    database_size = 0
    if not config.database_path.is_file():
        issues.append("database file is missing")
    else:
        database_size = config.database_path.stat().st_size
        connection = sqlite3.connect(f"file:{config.database_path.as_posix()}?mode=ro", uri=True, timeout=10.0)
        try:
            quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            active_admins = int(
                connection.execute(
                    "SELECT COUNT(*) FROM users_v1 WHERE active=1 AND role='admin'"
                ).fetchone()[0]
            )
        except sqlite3.Error as exc:
            issues.append(f"database health query failed: {exc}")
        finally:
            connection.close()
    if quick_check.lower() != "ok":
        issues.append(f"database quick_check is {quick_check}")
    if active_admins < 1:
        issues.append("no active administrator exists")
    if migrations.get("pending"):
        issues.append("database migrations are pending")
    if migrations.get("mismatched"):
        issues.append("database migration checksum mismatch")
    if not config.allow_loopback_http:
        if not config.certificate_file.is_file():
            issues.append("TLS certificate is missing")
        if not config.private_key_file.is_file():
            issues.append("TLS private key is missing")
    try:
        config.backup_directory.mkdir(parents=True, exist_ok=True)
        probe = config.backup_directory / ".health-write-test"
        probe.write_bytes(b"ok")
        probe.unlink(missing_ok=True)
    except OSError as exc:
        issues.append(f"backup directory is not writable: {exc}")
    return {
        "ok": not issues,
        "issues": issues,
        "database": {
            "path": str(config.database_path),
            "size_bytes": database_size,
            "quick_check": quick_check,
            "active_admins": active_admins,
            "wal_size_bytes": Path(str(config.database_path) + "-wal").stat().st_size
            if Path(str(config.database_path) + "-wal").exists()
            else 0,
        },
        "migrations": migrations,
        "tls": {
            "enabled": not config.allow_loopback_http,
            "certificate_exists": config.certificate_file.is_file(),
            "private_key_exists": config.private_key_file.is_file(),
        },
        "backup_directory": str(config.backup_directory),
    }


def remote_health(
    url: str,
    *,
    ca_bundle: str | Path | None = None,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    target = str(url or "").rstrip("/") + "/api/v1/health/ready"
    context = ssl.create_default_context(cafile=str(ca_bundle) if ca_bundle else None)
    request = Request(target, method="GET", headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout_seconds, context=context) as response:
            body = response.read(1024 * 1024)
            value = json.loads(body.decode("utf-8"))
            return {
                "ok": int(response.status) == 200 and bool(value.get("ok")),
                "status": int(response.status),
                "payload": value,
            }
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read(1024 * 1024).decode("utf-8"))
        except Exception:
            payload = {"ok": False, "error": "HTTP health check failed"}
        return {"ok": False, "status": int(exc.code), "payload": payload}
    except (URLError, OSError, ValueError, json.JSONDecodeError) as exc:
        return {"ok": False, "status": 0, "error": str(exc)}
