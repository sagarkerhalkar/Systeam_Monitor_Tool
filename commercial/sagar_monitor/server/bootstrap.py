from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import hashlib
import re
import sqlite3
import uuid

from sagar_monitor.security.foundation import hash_password, validate_password_strength


MIGRATIONS_DIRECTORY = Path(__file__).resolve().parents[2] / "migrations"
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _migration_files() -> list[Path]:
    files = sorted(MIGRATIONS_DIRECTORY.glob("[0-9][0-9][0-9][0-9]_*.sql"))
    if not files:
        raise RuntimeError(f"no commercial migrations found in {MIGRATIONS_DIRECTORY}")
    return files


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ensure_log(connection: sqlite3.Connection) -> None:
    connection.execute(
        """CREATE TABLE IF NOT EXISTS commercial_migration_log_v1(
            migration_name TEXT PRIMARY KEY,
            sha256 TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )"""
    )
    connection.commit()


def run_all_migrations(connection: sqlite3.Connection) -> dict[str, Any]:
    """Apply every immutable SQL migration and reject checksum drift."""
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    _ensure_log(connection)
    applied = 0
    verified = 0
    for path in _migration_files():
        checksum = _sha256(path)
        row = connection.execute(
            "SELECT sha256 FROM commercial_migration_log_v1 WHERE migration_name=?",
            (path.name,),
        ).fetchone()
        if row:
            if str(row[0]) != checksum:
                raise RuntimeError(f"migration checksum mismatch: {path.name}")
            verified += 1
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            connection.executescript(sql)
            connection.execute(
                "INSERT INTO commercial_migration_log_v1(migration_name,sha256,applied_at) VALUES(?,?,?)",
                (path.name, checksum, _utc_now()),
            )
            connection.commit()
            applied += 1
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
    return {"applied": applied, "verified": verified, "total": len(_migration_files())}


def migration_status(database_path: str | Path) -> dict[str, Any]:
    path = Path(database_path).expanduser().resolve()
    expected = {item.name: _sha256(item) for item in _migration_files()}
    if not path.exists():
        return {
            "database_exists": False,
            "expected": len(expected),
            "applied": 0,
            "pending": sorted(expected),
            "mismatched": [],
        }
    connection = sqlite3.connect(path, timeout=5.0)
    try:
        table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='commercial_migration_log_v1'"
        ).fetchone()
        rows = (
            connection.execute("SELECT migration_name,sha256 FROM commercial_migration_log_v1").fetchall()
            if table
            else []
        )
    finally:
        connection.close()
    applied = {str(name): str(checksum) for name, checksum in rows}
    return {
        "database_exists": True,
        "expected": len(expected),
        "applied": len(applied),
        "pending": sorted(name for name in expected if name not in applied),
        "mismatched": sorted(
            name for name, checksum in expected.items() if name in applied and applied[name] != checksum
        ),
        "unexpected": sorted(name for name in applied if name not in expected),
    }


def bootstrap_database(
    database_path: str | Path,
    *,
    organization_name: str,
    admin_username: str,
    admin_password: str,
    organization_id: str | None = None,
) -> dict[str, str]:
    """Create the first organization/admin only when the database has no users."""
    path = Path(database_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    clean_name = str(organization_name or "").strip()
    username = str(admin_username or "").strip().lower()
    if len(clean_name) < 2:
        raise ValueError("organization name must contain at least two characters")
    if not _USERNAME_RE.fullmatch(username):
        raise ValueError("admin username must be 3-64 safe lowercase characters")
    validate_password_strength(admin_password)
    password_hash = hash_password(admin_password)
    organization_id = str(organization_id or uuid.uuid4())
    user_id = str(uuid.uuid4())
    created_at = _utc_now()

    connection = sqlite3.connect(path, timeout=10.0)
    try:
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        run_all_migrations(connection)
        user_count = connection.execute("SELECT COUNT(*) FROM users_v1").fetchone()[0]
        organization_count = connection.execute("SELECT COUNT(*) FROM organizations_v1").fetchone()[0]
        if int(user_count) or int(organization_count):
            raise RuntimeError("first-run bootstrap is already complete")
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            "INSERT INTO organizations_v1(organization_id,name,status,created_at) VALUES(?,?,'active',?)",
            (organization_id, clean_name, created_at),
        )
        connection.execute(
            """INSERT INTO users_v1(
                user_id,organization_id,username,password_hash,role,active,created_at,password_changed_at
            ) VALUES(?,?,?,?, 'admin',1,?,?)""",
            (user_id, organization_id, username, password_hash, created_at, created_at),
        )
        connection.commit()
        check = connection.execute("PRAGMA quick_check").fetchone()[0]
        if str(check).lower() != "ok":
            raise RuntimeError(f"database integrity check failed after bootstrap: {check}")
        return {
            "organization_id": organization_id,
            "user_id": user_id,
            "username": username,
            "database_path": str(path),
        }
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.close()
