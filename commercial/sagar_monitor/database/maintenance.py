from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import hashlib
import json
import re
import sqlite3
import uuid


MIGRATION_PATH = Path(__file__).resolve().parents[2] / "migrations" / "0004_database_maintenance.sql"

RETENTION_TABLES: dict[str, str] = {
    "heartbeats": "received_at",
    "notifications": "created_at",
    "change_events": "created_at",
    "history_samples_v1": "inserted_at",
}

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _quote_identifier(value: str) -> str:
    if not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"unsafe SQL identifier: {value}")
    return f'"{value}"'


def _utc(value: datetime | str | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _iso(value: datetime | str | None = None) -> str:
    return _utc(value).isoformat()


def apply_maintenance_migration(connection: sqlite3.Connection) -> None:
    connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class RetentionPolicy:
    table_name: str
    retention_days: int
    timestamp_column: str = ""
    enabled: bool = True
    archive_required: bool = True

    def normalized(self) -> "RetentionPolicy":
        table = str(self.table_name or "").strip()
        if table not in RETENTION_TABLES:
            raise ValueError(f"retention is not allowed for table: {table}")
        column = str(self.timestamp_column or RETENTION_TABLES[table]).strip()
        if column != RETENTION_TABLES[table]:
            raise ValueError(f"timestamp column is not allowed for {table}: {column}")
        days = int(self.retention_days)
        if days < 1:
            raise ValueError("retention_days must be at least 1")
        return RetentionPolicy(
            table_name=table,
            timestamp_column=column,
            retention_days=days,
            enabled=bool(self.enabled),
            archive_required=bool(self.archive_required),
        )


def configure_database(
    connection: sqlite3.Connection,
    *,
    wal_autocheckpoint_pages: int = 1000,
    busy_timeout_ms: int = 5000,
) -> dict[str, Any]:
    """Configure safe connection-level settings and WAL auto-checkpointing."""
    if wal_autocheckpoint_pages < 1:
        raise ValueError("wal_autocheckpoint_pages must be positive")
    if busy_timeout_ms < 1:
        raise ValueError("busy_timeout_ms must be positive")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(f"PRAGMA busy_timeout={int(busy_timeout_ms)}")
    journal_mode = str(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
    connection.execute(f"PRAGMA wal_autocheckpoint={int(wal_autocheckpoint_pages)}")
    return {
        "journal_mode": journal_mode,
        "wal_autocheckpoint_pages": int(
            connection.execute("PRAGMA wal_autocheckpoint").fetchone()[0]
        ),
        "busy_timeout_ms": int(connection.execute("PRAGMA busy_timeout").fetchone()[0]),
        "foreign_keys": bool(connection.execute("PRAGMA foreign_keys").fetchone()[0]),
    }


def database_health(connection: sqlite3.Connection, database_path: str | Path) -> dict[str, Any]:
    """Return bounded database/WAL health facts without changing the database."""
    path = Path(database_path).expanduser().resolve()
    page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
    page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
    freelist_count = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
    journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    autocheckpoint = int(connection.execute("PRAGMA wal_autocheckpoint").fetchone()[0])
    quick_check = str(connection.execute("PRAGMA quick_check(1)").fetchone()[0])

    def size(candidate: Path) -> int:
        try:
            return candidate.stat().st_size
        except OSError:
            return 0

    return {
        "database_path": str(path),
        "database_bytes": size(path),
        "wal_bytes": size(Path(str(path) + "-wal")),
        "shm_bytes": size(Path(str(path) + "-shm")),
        "page_size": page_size,
        "page_count": page_count,
        "allocated_bytes": page_size * page_count,
        "freelist_pages": freelist_count,
        "freelist_bytes": page_size * freelist_count,
        "journal_mode": journal_mode,
        "wal_autocheckpoint_pages": autocheckpoint,
        "quick_check": quick_check,
        "ok": quick_check.lower() == "ok",
    }


def passive_checkpoint(connection: sqlite3.Connection) -> dict[str, int | bool]:
    """Run SQLite's non-blocking PASSIVE checkpoint and report its result."""
    busy, log_pages, checkpointed_pages = connection.execute(
        "PRAGMA wal_checkpoint(PASSIVE)"
    ).fetchone()
    return {
        "busy": bool(busy),
        "log_pages": int(log_pages),
        "checkpointed_pages": int(checkpointed_pages),
    }


def truncate_checkpoint(
    connection: sqlite3.Connection,
    *,
    maintenance_window_confirmed: bool = False,
) -> dict[str, int | bool]:
    """TRUNCATE checkpoint is forbidden unless a maintenance window is explicit."""
    if not maintenance_window_confirmed:
        raise PermissionError("TRUNCATE checkpoint requires a confirmed maintenance window")
    if connection.in_transaction:
        raise RuntimeError("TRUNCATE checkpoint cannot run inside an active transaction")
    busy, log_pages, checkpointed_pages = connection.execute(
        "PRAGMA wal_checkpoint(TRUNCATE)"
    ).fetchone()
    return {
        "busy": bool(busy),
        "log_pages": int(log_pages),
        "checkpointed_pages": int(checkpointed_pages),
    }


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return bool(
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table_name,)
        ).fetchone()
    )


def create_retention_plan(
    connection: sqlite3.Connection,
    policies: Iterable[RetentionPolicy],
    *,
    now: datetime | str | None = None,
) -> list[dict[str, Any]]:
    """Create a read-only retention plan; no archive or deletion occurs."""
    anchor = _utc(now)
    plan: list[dict[str, Any]] = []
    before = connection.total_changes
    for raw_policy in policies:
        policy = raw_policy.normalized()
        cutoff = anchor - timedelta(days=policy.retention_days)
        exists = _table_exists(connection, policy.table_name)
        count = 0
        if exists and policy.enabled:
            table = _quote_identifier(policy.table_name)
            column = _quote_identifier(policy.timestamp_column)
            count = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {column} < ?",
                    (cutoff.isoformat(),),
                ).fetchone()[0]
            )
        plan.append(
            {
                "table_name": policy.table_name,
                "timestamp_column": policy.timestamp_column,
                "retention_days": policy.retention_days,
                "cutoff_at": cutoff.isoformat(),
                "enabled": policy.enabled,
                "archive_required": policy.archive_required,
                "table_exists": exists,
                "planned_rows": count,
            }
        )
    if connection.total_changes != before:
        raise RuntimeError("retention planning unexpectedly changed the database")
    return plan


def _column_definitions(connection: sqlite3.Connection, table_name: str) -> list[tuple[str, str]]:
    rows = connection.execute(f"PRAGMA table_info({_quote_identifier(table_name)})").fetchall()
    if not rows:
        raise RuntimeError(f"table not found: {table_name}")
    return [(str(row[1]), str(row[2] or "TEXT")) for row in rows]


def _row_hash(columns: list[str], row: Mapping[str, Any]) -> str:
    payload = json.dumps(
        {name: row.get(name) for name in columns},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _ensure_archive_table(
    archive: sqlite3.Connection,
    table_name: str,
    definitions: list[tuple[str, str]],
) -> str:
    archive_table = f"archived_{table_name}_v1"
    column_sql = ", ".join(
        f"{_quote_identifier(name)} {column_type}" for name, column_type in definitions
    )
    archive.execute(
        f"""CREATE TABLE IF NOT EXISTS {_quote_identifier(archive_table)} (
            {column_sql},
            source_row_hash TEXT NOT NULL UNIQUE,
            archived_at TEXT NOT NULL
        )"""
    )
    archive.execute(
        f"CREATE INDEX IF NOT EXISTS {_quote_identifier('ix_' + archive_table + '_archived')} "
        f"ON {_quote_identifier(archive_table)}(archived_at)"
    )
    return archive_table


def archive_and_prune(
    connection: sqlite3.Connection,
    policy: RetentionPolicy,
    *,
    archive_path: str | Path | None = None,
    backup_verified: bool = False,
    now: datetime | str | None = None,
    batch_size: int = 1000,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Archive each batch durably before pruning it from the operational table."""
    normalized = policy.normalized()
    if batch_size < 1 or batch_size > 10000:
        raise ValueError("batch_size must be between 1 and 10000")
    plan = create_retention_plan(connection, [normalized], now=now)[0]
    result = dict(plan)
    result.update({"archived_rows": 0, "pruned_rows": 0, "dry_run": dry_run})
    if dry_run or not normalized.enabled or plan["planned_rows"] == 0:
        return result
    if not backup_verified:
        raise PermissionError("retention execution requires verified backup evidence")
    if normalized.archive_required and archive_path is None:
        raise PermissionError("archive_path is required by this retention policy")
    if connection.in_transaction:
        raise RuntimeError("retention cannot start inside an active transaction")

    apply_maintenance_migration(connection)
    run_id = str(uuid.uuid4())
    started_at = _iso()
    connection.execute(
        """INSERT INTO database_maintenance_runs_v1(
            run_id, operation, table_name, started_at, status, cutoff_at,
            planned_rows, detail_json
        ) VALUES(?,?,?,?,?,?,?,?)""",
        (
            run_id,
            "archive_and_prune",
            normalized.table_name,
            started_at,
            "running",
            plan["cutoff_at"],
            plan["planned_rows"],
            json.dumps({"archive_path": str(archive_path or ""), "batch_size": batch_size}),
        ),
    )
    connection.commit()

    archive = sqlite3.connect(Path(archive_path).expanduser().resolve()) if archive_path else None
    try:
        connection.row_factory = sqlite3.Row
        definitions = _column_definitions(connection, normalized.table_name)
        columns = [name for name, _ in definitions]
        archive_table = ""
        if archive is not None:
            archive_table = _ensure_archive_table(archive, normalized.table_name, definitions)
            archive.commit()

        table = _quote_identifier(normalized.table_name)
        timestamp_column = _quote_identifier(normalized.timestamp_column)
        while True:
            rows = connection.execute(
                f"SELECT rowid AS __source_rowid__, * FROM {table} "
                f"WHERE {timestamp_column} < ? ORDER BY {timestamp_column}, rowid LIMIT ?",
                (plan["cutoff_at"], batch_size),
            ).fetchall()
            if not rows:
                break

            rowids = [int(row["__source_rowid__"]) for row in rows]
            if archive is not None:
                insert_columns = columns + ["source_row_hash", "archived_at"]
                placeholders = ",".join("?" for _ in insert_columns)
                insert_sql = (
                    f"INSERT OR IGNORE INTO {_quote_identifier(archive_table)} "
                    f"({','.join(_quote_identifier(name) for name in insert_columns)}) "
                    f"VALUES({placeholders})"
                )
                archived_at = _iso()
                hashes: list[str] = []
                for row in rows:
                    mapping = dict(row)
                    digest = _row_hash(columns, mapping)
                    hashes.append(digest)
                    archive.execute(
                        insert_sql,
                        tuple(mapping.get(name) for name in columns) + (digest, archived_at),
                    )
                archive.commit()
                verified = sum(
                    1
                    for digest in hashes
                    if archive.execute(
                        f"SELECT 1 FROM {_quote_identifier(archive_table)} WHERE source_row_hash=?",
                        (digest,),
                    ).fetchone()
                )
                if verified != len(hashes):
                    raise RuntimeError("archive verification failed; source rows were not pruned")
                result["archived_rows"] += len(hashes)

            placeholders = ",".join("?" for _ in rowids)
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(f"DELETE FROM {table} WHERE rowid IN ({placeholders})", rowids)
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            result["pruned_rows"] += len(rowids)

        connection.execute(
            """UPDATE database_maintenance_runs_v1
               SET completed_at=?, status='completed', archived_rows=?, pruned_rows=?, detail_json=?
               WHERE run_id=?""",
            (
                _iso(),
                result["archived_rows"],
                result["pruned_rows"],
                json.dumps(result, ensure_ascii=False, sort_keys=True),
                run_id,
            ),
        )
        connection.commit()
        result["run_id"] = run_id
        return result
    except Exception as exc:
        connection.rollback()
        connection.execute(
            """UPDATE database_maintenance_runs_v1
               SET completed_at=?, status='failed', detail_json=? WHERE run_id=?""",
            (_iso(), json.dumps({"error": str(exc)}), run_id),
        )
        connection.commit()
        raise
    finally:
        if archive is not None:
            archive.close()
