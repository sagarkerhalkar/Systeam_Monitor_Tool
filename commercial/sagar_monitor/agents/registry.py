from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import uuid

from sagar_monitor.history.incremental import (
    HistoryEvent,
    apply_history_migration,
    rebuild_rollup_for_key,
)
from sagar_monitor.identity.agent_id import normalize_agent_install_id
from sagar_monitor.security.foundation import apply_security_migration


MIGRATION_PATH = Path(__file__).resolve().parents[2] / "migrations" / "0007_agent_auth_heartbeat.sql"
EVENT_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,160}$")
PLATFORM_MAP = {
    "windows": "windows",
    "win": "windows",
    "win32": "windows",
    "linux": "linux",
    "ubuntu": "linux",
    "debian": "linux",
}


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


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _platform(value: object) -> str:
    clean = str(value or "").strip().lower()
    result = PLATFORM_MAP.get(clean, "")
    if not result:
        raise ValueError("platform must be Windows or Linux/Ubuntu")
    return result


def _hostname(payload: Mapping[str, Any], fallback: str = "") -> str:
    identity = payload.get("identity") if isinstance(payload.get("identity"), Mapping) else {}
    return str(identity.get("hostname") or payload.get("hostname") or fallback or "").strip()[:255]


def _summary(payload: Mapping[str, Any]) -> dict[str, Any]:
    hardware = payload.get("hardware") if isinstance(payload.get("hardware"), Mapping) else {}
    cpu = hardware.get("cpu") if isinstance(hardware.get("cpu"), Mapping) else {}
    memory = hardware.get("memory") if isinstance(hardware.get("memory"), Mapping) else {}
    network = payload.get("network") if isinstance(payload.get("network"), Mapping) else {}
    traffic = network.get("traffic") if isinstance(network.get("traffic"), Mapping) else {}
    return {
        "hostname": _hostname(payload),
        "cpu_percent": cpu.get("usage_percent"),
        "ram_percent": memory.get("used_percent"),
        "current_download_mbps": traffic.get("current_download_mbps")
        or network.get("current_download_mbps"),
        "current_upload_mbps": traffic.get("current_upload_mbps")
        or network.get("current_upload_mbps"),
        "today_download_bytes": traffic.get("today_download_bytes"),
        "today_upload_bytes": traffic.get("today_upload_bytes"),
    }


def apply_agent_migration(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class AgentIdentity:
    agent_install_id: str
    organization_id: str
    canonical_client_id: str
    platform: str
    current_hostname: str
    token_version: int
    status: str


def _identity_from_row(row: sqlite3.Row | tuple[Any, ...]) -> AgentIdentity:
    return AgentIdentity(
        agent_install_id=str(row["agent_install_id"]),
        organization_id=str(row["organization_id"]),
        canonical_client_id=str(row["canonical_client_id"]),
        platform=str(row["platform"]),
        current_hostname=str(row["current_hostname"] or ""),
        token_version=int(row["token_version"]),
        status=str(row["status"]),
    )


def register_agent(
    connection: sqlite3.Connection,
    *,
    enrollment_token: str,
    agent_install_id: str,
    platform: str,
    hostname: str = "",
    metadata: Mapping[str, Any] | None = None,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    """Consume one enrollment use and return the raw agent token exactly once."""
    apply_security_migration(connection)
    apply_agent_migration(connection)
    normalized_id = normalize_agent_install_id(agent_install_id)
    if not normalized_id:
        raise ValueError("agent_install_id must be a valid UUID")
    normalized_platform = _platform(platform)
    if not enrollment_token:
        raise PermissionError("valid enrollment token is required")
    anchor = _utc(now)
    token_hash = _sha256(enrollment_token)
    raw_agent_token = secrets.token_urlsafe(40)
    canonical_client_id = "client:" + _sha256(f"{normalized_id}\0agent")[:24]
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        enrollment = connection.execute(
            "SELECT * FROM enrollment_tokens_v1 WHERE token_hash=?",
            (token_hash,),
        ).fetchone()
        if (
            not enrollment
            or enrollment["revoked_at"]
            or _utc(enrollment["expires_at"]) <= anchor
            or int(enrollment["uses"]) >= int(enrollment["max_uses"])
        ):
            connection.rollback()
            raise PermissionError("enrollment token is invalid, expired, revoked or exhausted")
        organization_id = str(enrollment["organization_id"])
        connection.execute(
            "UPDATE enrollment_tokens_v1 SET uses=uses+1 WHERE token_hash=?",
            (token_hash,),
        )
        connection.execute(
            """INSERT INTO agent_credentials_v1(
                agent_install_id,organization_id,canonical_client_id,token_hash,
                token_version,platform,current_hostname,status,created_at,last_seen_at,
                rotated_at,metadata_json
            ) VALUES(?,?,?,?,1,?,?, 'active',?,?,NULL,?)""",
            (
                normalized_id,
                organization_id,
                canonical_client_id,
                _sha256(raw_agent_token),
                normalized_platform,
                str(hostname or "").strip()[:255],
                anchor.isoformat(),
                anchor.isoformat(),
                json.dumps(dict(metadata or {}), ensure_ascii=False, sort_keys=True),
            ),
        )
        connection.commit()
        return {
            "agent_install_id": normalized_id,
            "organization_id": organization_id,
            "canonical_client_id": canonical_client_id,
            "agent_token": raw_agent_token,
            "token_version": 1,
            "platform": normalized_platform,
        }
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise


def authenticate_agent(
    connection: sqlite3.Connection,
    *,
    agent_install_id: str,
    agent_token: str,
) -> AgentIdentity | None:
    normalized_id = normalize_agent_install_id(agent_install_id)
    if not normalized_id or not agent_token:
        return None
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        "SELECT * FROM agent_credentials_v1 WHERE agent_install_id=?",
        (normalized_id,),
    ).fetchone()
    if not row or str(row["status"]) != "active":
        return None
    if not hmac.compare_digest(str(row["token_hash"]), _sha256(agent_token)):
        return None
    return _identity_from_row(row)


def rotate_agent_token(
    connection: sqlite3.Connection,
    *,
    agent_install_id: str,
    current_token: str,
    reason: str = "agent requested rotation",
    now: datetime | str | None = None,
) -> dict[str, Any]:
    apply_agent_migration(connection)
    identity = authenticate_agent(
        connection,
        agent_install_id=agent_install_id,
        agent_token=current_token,
    )
    if not identity:
        raise PermissionError("valid active agent credential is required")
    anchor = _utc(now)
    new_token = secrets.token_urlsafe(40)
    new_version = identity.token_version + 1
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """UPDATE agent_credentials_v1
               SET token_hash=?,token_version=?,rotated_at=?
               WHERE agent_install_id=? AND token_version=? AND status='active'""",
            (
                _sha256(new_token),
                new_version,
                anchor.isoformat(),
                identity.agent_install_id,
                identity.token_version,
            ),
        )
        if connection.execute("SELECT changes()").fetchone()[0] != 1:
            connection.rollback()
            raise RuntimeError("agent token changed concurrently")
        connection.execute(
            """INSERT INTO agent_token_rotation_events_v1(
                rotation_id,agent_install_id,organization_id,old_version,new_version,rotated_at,reason
            ) VALUES(?,?,?,?,?,?,?)""",
            (
                str(uuid.uuid4()),
                identity.agent_install_id,
                identity.organization_id,
                identity.token_version,
                new_version,
                anchor.isoformat(),
                str(reason or "")[:500],
            ),
        )
        connection.commit()
        return {
            "agent_install_id": identity.agent_install_id,
            "agent_token": new_token,
            "token_version": new_version,
            "rotated_at": anchor.isoformat(),
        }
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise


def ingest_heartbeat(
    connection: sqlite3.Connection,
    *,
    agent: AgentIdentity,
    client_event_id: str,
    payload: Mapping[str, Any],
    timezone_name: str = "Asia/Kolkata",
    received_at: datetime | str | None = None,
) -> dict[str, Any]:
    """Persist one idempotent heartbeat and update exactly one client/day rollup."""
    if not EVENT_ID_RE.fullmatch(str(client_event_id or "")):
        raise ValueError("client_event_id must be 8-160 safe characters")
    if not isinstance(payload, Mapping):
        raise ValueError("heartbeat payload must be a JSON object")
    apply_agent_migration(connection)
    apply_history_migration(connection)
    anchor = _utc(received_at)
    payload_object = dict(payload)
    payload_json = json.dumps(
        payload_object,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    payload_hash = _sha256(payload_json)
    event_key = _sha256(f"{agent.agent_install_id}\0{client_event_id}")
    hostname = _hostname(payload_object, agent.current_hostname)
    summary = _summary(payload_object)
    history_event = HistoryEvent.from_payload(
        event_id=event_key,
        canonical_client_id=agent.canonical_client_id,
        received_at=anchor,
        payload=payload_object,
        organization_id=agent.organization_id,
        timezone_name=timezone_name,
    ).normalized()
    local_day = history_event.local_day
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        before = connection.total_changes
        connection.execute(
            """INSERT OR IGNORE INTO agent_heartbeat_events_v1(
                event_key,client_event_id,organization_id,canonical_client_id,
                agent_install_id,received_at,hostname,platform,payload_hash,payload_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                event_key,
                client_event_id,
                agent.organization_id,
                agent.canonical_client_id,
                agent.agent_install_id,
                anchor.isoformat(),
                hostname,
                agent.platform,
                payload_hash,
                payload_json,
            ),
        )
        inserted = connection.total_changes > before
        if inserted:
            connection.execute(
                """INSERT INTO history_samples_v1(
                    event_id,organization_id,canonical_client_id,local_day,event_at,
                    timezone_name,hostname,download_counter_bytes,upload_counter_bytes,
                    current_download_mbps,current_upload_mbps,cpu_percent,ram_percent,
                    payload_hash,inserted_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    history_event.event_id,
                    history_event.organization_id,
                    history_event.canonical_client_id,
                    local_day,
                    history_event.event_at,
                    history_event.timezone_name,
                    history_event.hostname,
                    history_event.download_counter_bytes,
                    history_event.upload_counter_bytes,
                    history_event.current_download_mbps,
                    history_event.current_upload_mbps,
                    history_event.cpu_percent,
                    history_event.ram_percent,
                    history_event.payload_hash,
                    anchor.isoformat(),
                ),
            )
            rebuild_rollup_for_key(
                connection,
                agent.organization_id,
                agent.canonical_client_id,
                local_day,
            )
            connection.execute(
                """INSERT INTO agent_current_v1(
                    organization_id,canonical_client_id,agent_install_id,hostname,
                    platform,updated_at,last_event_key,payload_hash,summary_json
                ) VALUES(?,?,?,?,?,?,?,?,?)
                ON CONFLICT(organization_id,canonical_client_id) DO UPDATE SET
                    agent_install_id=excluded.agent_install_id,
                    hostname=excluded.hostname,
                    platform=excluded.platform,
                    updated_at=excluded.updated_at,
                    last_event_key=excluded.last_event_key,
                    payload_hash=excluded.payload_hash,
                    summary_json=excluded.summary_json""",
                (
                    agent.organization_id,
                    agent.canonical_client_id,
                    agent.agent_install_id,
                    hostname,
                    agent.platform,
                    anchor.isoformat(),
                    event_key,
                    payload_hash,
                    json.dumps(summary, ensure_ascii=False, sort_keys=True),
                ),
            )
        connection.execute(
            """UPDATE agent_credentials_v1
               SET last_seen_at=?,current_hostname=? WHERE agent_install_id=?""",
            (anchor.isoformat(), hostname, agent.agent_install_id),
        )
        connection.commit()
        return {
            "inserted": inserted,
            "event_key": event_key,
            "client_event_id": client_event_id,
            "organization_id": agent.organization_id,
            "canonical_client_id": agent.canonical_client_id,
            "agent_install_id": agent.agent_install_id,
            "hostname": hostname,
            "local_day": local_day,
            "received_at": anchor.isoformat(),
        }
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
