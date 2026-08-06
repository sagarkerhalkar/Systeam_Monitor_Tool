from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping
import hashlib
import json
import os
import sqlite3
import tempfile
import uuid

from sagar_monitor.identity.agent_id import normalize_agent_install_id


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


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _restrict(path: Path, mode: int) -> None:
    if os.name != "nt":
        try:
            path.chmod(mode)
        except OSError:
            pass


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _restrict(path.parent, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(dict(value), handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        _restrict(temporary, 0o600)
        os.replace(temporary, path)
        _restrict(path, 0o600)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


@dataclass(frozen=True)
class AgentCredential:
    agent_install_id: str
    agent_token: str
    organization_id: str = ""
    canonical_client_id: str = ""
    token_version: int = 0
    platform: str = ""


class CredentialStore:
    """Atomic local identity and credential storage.

    The agent token must exist locally to authenticate, but it is written to a
    restricted file and is never written to logs or the queue database.
    """

    def __init__(self, state_directory: str | Path) -> None:
        self.state_directory = Path(state_directory).expanduser().resolve()
        self.identity_path = self.state_directory / "identity.json"
        self.credential_path = self.state_directory / "credential.json"
        self.state_directory.mkdir(parents=True, exist_ok=True)
        _restrict(self.state_directory, 0o700)

    def ensure_agent_install_id(self) -> str:
        current = self.load_agent_install_id()
        if current:
            return current
        generated = str(uuid.uuid4())
        _atomic_json(self.identity_path, {"agent_install_id": generated})
        return generated

    def load_agent_install_id(self) -> str:
        try:
            raw = json.loads(self.identity_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return ""
        return normalize_agent_install_id(raw.get("agent_install_id")) if isinstance(raw, dict) else ""

    def load_credential(self) -> AgentCredential | None:
        try:
            raw = json.loads(self.credential_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            return None
        if not isinstance(raw, dict):
            return None
        install_id = normalize_agent_install_id(raw.get("agent_install_id"))
        token = str(raw.get("agent_token") or "").strip()
        if not install_id or not token:
            return None
        return AgentCredential(
            agent_install_id=install_id,
            agent_token=token,
            organization_id=str(raw.get("organization_id") or "").strip(),
            canonical_client_id=str(raw.get("canonical_client_id") or "").strip(),
            token_version=max(0, int(raw.get("token_version") or 0)),
            platform=str(raw.get("platform") or "").strip(),
        )

    def save_registration(self, registration: Mapping[str, Any]) -> AgentCredential:
        install_id = normalize_agent_install_id(registration.get("agent_install_id"))
        token = str(registration.get("agent_token") or "").strip()
        if not install_id or not token:
            raise ValueError("registration response is missing agent credentials")
        identity = self.ensure_agent_install_id()
        if identity != install_id:
            raise ValueError("server registration identity does not match local permanent identity")
        document = {
            "agent_install_id": install_id,
            "agent_token": token,
            "organization_id": str(registration.get("organization_id") or "").strip(),
            "canonical_client_id": str(registration.get("canonical_client_id") or "").strip(),
            "token_version": max(1, int(registration.get("token_version") or 1)),
            "platform": str(registration.get("platform") or "").strip(),
        }
        _atomic_json(self.credential_path, document)
        credential = self.load_credential()
        if credential is None:
            raise RuntimeError("credential verification failed after atomic write")
        return credential

    def save_rotated_token(self, token: str, token_version: int) -> AgentCredential:
        current = self.load_credential()
        if current is None:
            raise RuntimeError("agent is not registered")
        clean_token = str(token or "").strip()
        if not clean_token:
            raise ValueError("rotated token is empty")
        document = {
            "agent_install_id": current.agent_install_id,
            "agent_token": clean_token,
            "organization_id": current.organization_id,
            "canonical_client_id": current.canonical_client_id,
            "token_version": max(current.token_version + 1, int(token_version or 0)),
            "platform": current.platform,
        }
        _atomic_json(self.credential_path, document)
        result = self.load_credential()
        if result is None:
            raise RuntimeError("rotated credential verification failed")
        return result


@dataclass(frozen=True)
class QueuedHeartbeat:
    event_id: str
    payload: dict[str, Any]
    timezone_name: str
    attempts: int


@dataclass(frozen=True)
class QueuedReceipt:
    delivery_id: str
    dispatch_token: str
    client_receipt_id: str
    detail: dict[str, Any]
    attempts: int


class EdgeQueue:
    """Durable outbound queue and local acknowledgement cache."""

    def __init__(self, database_path: str | Path, *, max_heartbeats: int = 10000) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        _restrict(self.database_path.parent, 0o700)
        if max_heartbeats < 100 or max_heartbeats > 1_000_000:
            raise ValueError("max_heartbeats must be between 100 and 1000000")
        self.max_heartbeats = max_heartbeats
        with self.connection() as connection:
            self._migrate(connection)
        _restrict(self.database_path, 0o600)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10.0)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA busy_timeout=10000")
            yield connection
            if connection.in_transaction:
                connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _migrate(connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS edge_heartbeat_queue_v1 (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                payload_json TEXT NOT NULL,
                timezone_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TEXT NOT NULL,
                last_error TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS ix_edge_heartbeat_due_v1
            ON edge_heartbeat_queue_v1(next_attempt_at, sequence);

            CREATE TABLE IF NOT EXISTS edge_receipt_queue_v1 (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                delivery_id TEXT NOT NULL UNIQUE,
                dispatch_token TEXT NOT NULL,
                client_receipt_id TEXT NOT NULL,
                detail_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                attempts INTEGER NOT NULL DEFAULT 0,
                next_attempt_at TEXT NOT NULL,
                last_error TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS ix_edge_receipt_due_v1
            ON edge_receipt_queue_v1(next_attempt_at, sequence);

            CREATE TABLE IF NOT EXISTS edge_message_cache_v1 (
                delivery_id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                body_hash TEXT NOT NULL,
                displayed_at TEXT NOT NULL,
                acknowledged_at TEXT,
                expires_at TEXT NOT NULL DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS edge_runtime_events_v1 (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                event_type TEXT NOT NULL,
                detail_json TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS ix_edge_runtime_events_time_v1
            ON edge_runtime_events_v1(created_at, sequence);
            """
        )

    def enqueue_heartbeat(
        self,
        *,
        event_id: str,
        payload: Mapping[str, Any],
        timezone_name: str,
        now: datetime | str | None = None,
    ) -> bool:
        clean_event = str(event_id or "").strip()
        if len(clean_event) < 8 or len(clean_event) > 160:
            raise ValueError("event_id must be 8-160 characters")
        payload_json = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        anchor = _iso(now)
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            before = connection.total_changes
            connection.execute(
                """INSERT OR IGNORE INTO edge_heartbeat_queue_v1(
                    event_id,payload_json,timezone_name,created_at,next_attempt_at
                ) VALUES(?,?,?,?,?)""",
                (clean_event, payload_json, str(timezone_name or "Asia/Kolkata"), anchor, anchor),
            )
            inserted = connection.total_changes > before
            overflow = connection.execute(
                "SELECT MAX(0,COUNT(*)-?) FROM edge_heartbeat_queue_v1",
                (self.max_heartbeats,),
            ).fetchone()[0]
            if overflow:
                connection.execute(
                    """DELETE FROM edge_heartbeat_queue_v1 WHERE sequence IN (
                        SELECT sequence FROM edge_heartbeat_queue_v1 ORDER BY sequence LIMIT ?
                    )""",
                    (int(overflow),),
                )
                self._audit(connection, "heartbeat_queue_trimmed", {"removed": int(overflow)}, now=anchor)
            return inserted

    def next_heartbeat(self, now: datetime | str | None = None) -> QueuedHeartbeat | None:
        anchor = _iso(now)
        with self.connection() as connection:
            row = connection.execute(
                """SELECT event_id,payload_json,timezone_name,attempts
                   FROM edge_heartbeat_queue_v1
                   WHERE next_attempt_at<=?
                   ORDER BY sequence LIMIT 1""",
                (anchor,),
            ).fetchone()
            if not row:
                return None
            try:
                payload = json.loads(row["payload_json"])
            except (ValueError, TypeError, json.JSONDecodeError):
                payload = {}
            return QueuedHeartbeat(
                event_id=str(row["event_id"]),
                payload=payload if isinstance(payload, dict) else {},
                timezone_name=str(row["timezone_name"]),
                attempts=int(row["attempts"]),
            )

    def complete_heartbeat(self, event_id: str) -> None:
        with self.connection() as connection:
            connection.execute("DELETE FROM edge_heartbeat_queue_v1 WHERE event_id=?", (event_id,))

    def fail_heartbeat(
        self,
        event_id: str,
        error: str,
        *,
        retry_after_seconds: int,
        now: datetime | str | None = None,
    ) -> None:
        anchor = _utc(now)
        retry_at = anchor + timedelta(seconds=max(1, retry_after_seconds))
        with self.connection() as connection:
            connection.execute(
                """UPDATE edge_heartbeat_queue_v1
                   SET attempts=attempts+1,next_attempt_at=?,last_error=? WHERE event_id=?""",
                (retry_at.isoformat(), str(error or "")[:1000], event_id),
            )

    def cache_message(self, message: Mapping[str, Any], now: datetime | str | None = None) -> tuple[bool, str]:
        delivery_id = str(message.get("delivery_id") or "").strip()
        message_id = str(message.get("message_id") or "").strip()
        dispatch_token = str(message.get("dispatch_token") or "").strip()
        if not delivery_id or not message_id or not dispatch_token:
            raise ValueError("message is missing delivery identity or dispatch token")
        body_hash = _sha256_text(
            json.dumps(
                {
                    "title": message.get("title"),
                    "body": message.get("body"),
                    "severity": message.get("severity"),
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        anchor = _iso(now)
        receipt_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"sagar-monitor:{delivery_id}"))
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT body_hash,acknowledged_at FROM edge_message_cache_v1 WHERE delivery_id=?",
                (delivery_id,),
            ).fetchone()
            first_display = existing is None
            if existing and str(existing["body_hash"]) != body_hash:
                raise ValueError("delivery_id was reused with different message content")
            if first_display:
                connection.execute(
                    """INSERT INTO edge_message_cache_v1(
                        delivery_id,message_id,body_hash,displayed_at,expires_at
                    ) VALUES(?,?,?,?,?)""",
                    (delivery_id, message_id, body_hash, anchor, str(message.get("expires_at") or "")),
                )
            if not existing or not existing["acknowledged_at"]:
                connection.execute(
                    """INSERT INTO edge_receipt_queue_v1(
                        delivery_id,dispatch_token,client_receipt_id,detail_json,created_at,next_attempt_at
                    ) VALUES(?,?,?,?,?,?)
                    ON CONFLICT(delivery_id) DO UPDATE SET
                        dispatch_token=excluded.dispatch_token,
                        next_attempt_at=excluded.next_attempt_at,
                        last_error=''""",
                    (
                        delivery_id,
                        dispatch_token,
                        receipt_id,
                        json.dumps({"displayed": True}, sort_keys=True),
                        anchor,
                        anchor,
                    ),
                )
            return first_display, receipt_id

    def next_receipt(self, now: datetime | str | None = None) -> QueuedReceipt | None:
        anchor = _iso(now)
        with self.connection() as connection:
            row = connection.execute(
                """SELECT delivery_id,dispatch_token,client_receipt_id,detail_json,attempts
                   FROM edge_receipt_queue_v1
                   WHERE next_attempt_at<=? ORDER BY sequence LIMIT 1""",
                (anchor,),
            ).fetchone()
            if not row:
                return None
            try:
                detail = json.loads(row["detail_json"] or "{}")
            except (ValueError, TypeError, json.JSONDecodeError):
                detail = {}
            return QueuedReceipt(
                delivery_id=str(row["delivery_id"]),
                dispatch_token=str(row["dispatch_token"]),
                client_receipt_id=str(row["client_receipt_id"]),
                detail=detail if isinstance(detail, dict) else {},
                attempts=int(row["attempts"]),
            )

    def complete_receipt(self, delivery_id: str, now: datetime | str | None = None) -> None:
        anchor = _iso(now)
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("DELETE FROM edge_receipt_queue_v1 WHERE delivery_id=?", (delivery_id,))
            connection.execute(
                "UPDATE edge_message_cache_v1 SET acknowledged_at=? WHERE delivery_id=?",
                (anchor, delivery_id),
            )

    def fail_receipt(
        self,
        delivery_id: str,
        error: str,
        *,
        retry_after_seconds: int,
        now: datetime | str | None = None,
    ) -> None:
        anchor = _utc(now)
        retry_at = anchor + timedelta(seconds=max(1, retry_after_seconds))
        with self.connection() as connection:
            connection.execute(
                """UPDATE edge_receipt_queue_v1
                   SET attempts=attempts+1,next_attempt_at=?,last_error=? WHERE delivery_id=?""",
                (retry_at.isoformat(), str(error or "")[:1000], delivery_id),
            )

    def counts(self) -> dict[str, int]:
        with self.connection() as connection:
            heartbeats = int(connection.execute("SELECT COUNT(*) FROM edge_heartbeat_queue_v1").fetchone()[0])
            receipts = int(connection.execute("SELECT COUNT(*) FROM edge_receipt_queue_v1").fetchone()[0])
            unacknowledged = int(
                connection.execute(
                    "SELECT COUNT(*) FROM edge_message_cache_v1 WHERE acknowledged_at IS NULL"
                ).fetchone()[0]
            )
            return {
                "pending_heartbeats": heartbeats,
                "pending_receipts": receipts,
                "unacknowledged_messages": unacknowledged,
            }

    def audit(self, event_type: str, detail: Mapping[str, Any] | None = None, now: datetime | str | None = None) -> None:
        with self.connection() as connection:
            self._audit(connection, event_type, detail or {}, now=now)

    @staticmethod
    def _audit(
        connection: sqlite3.Connection,
        event_type: str,
        detail: Mapping[str, Any],
        *,
        now: datetime | str | None = None,
    ) -> None:
        connection.execute(
            "INSERT INTO edge_runtime_events_v1(created_at,event_type,detail_json) VALUES(?,?,?)",
            (
                _iso(now),
                str(event_type or "unknown")[:100],
                json.dumps(dict(detail), ensure_ascii=False, sort_keys=True),
            ),
        )
        connection.execute(
            """DELETE FROM edge_runtime_events_v1 WHERE sequence IN (
                SELECT sequence FROM edge_runtime_events_v1 ORDER BY sequence DESC LIMIT -1 OFFSET 5000
            )"""
        )
