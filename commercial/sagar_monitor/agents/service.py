from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
import json
import sqlite3

from sagar_monitor.history.incremental import (
    HistoryEvent,
    apply_history_migration,
    rebuild_rollup_for_key,
)

from .registry import (
    AgentIdentity,
    EVENT_ID_RE,
    _hostname,
    _sha256,
    _summary,
    _utc,
    apply_agent_migration,
    authenticate_agent,
    register_agent,
    rotate_agent_token,
)


def ingest_heartbeat(
    connection: sqlite3.Connection,
    *,
    agent: AgentIdentity,
    client_event_id: str,
    payload: Mapping[str, Any],
    timezone_name: str = "Asia/Kolkata",
    received_at: datetime | str | None = None,
) -> dict[str, Any]:
    """Persist one event and order equal timestamps by database sequence.

    The sequence prefix is used only as a deterministic history tie-breaker. It
    prevents two heartbeats received at the same timestamp from reversing
    cumulative counters or the last hostname.
    """
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
        sequence_row = connection.execute(
            "SELECT sequence_id FROM agent_heartbeat_events_v1 WHERE event_key=?",
            (event_key,),
        ).fetchone()
        if not sequence_row:
            raise RuntimeError("heartbeat sequence was not created")
        sequence_id = int(sequence_row[0])
        local_day = ""
        if inserted:
            history_event = HistoryEvent.from_payload(
                event_id=f"{sequence_id:020d}:{event_key}",
                canonical_client_id=agent.canonical_client_id,
                received_at=anchor,
                payload=payload_object,
                organization_id=agent.organization_id,
                timezone_name=timezone_name,
            ).normalized()
            local_day = history_event.local_day
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
        else:
            day_row = connection.execute(
                """SELECT local_day FROM history_samples_v1
                   WHERE event_id=?""",
                (f"{sequence_id:020d}:{event_key}",),
            ).fetchone()
            local_day = str(day_row[0]) if day_row else ""
        connection.execute(
            """UPDATE agent_credentials_v1
               SET last_seen_at=?,current_hostname=? WHERE agent_install_id=?""",
            (anchor.isoformat(), hostname, agent.agent_install_id),
        )
        connection.commit()
        return {
            "inserted": inserted,
            "sequence_id": sequence_id,
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


__all__ = [
    "AgentIdentity",
    "apply_agent_migration",
    "authenticate_agent",
    "ingest_heartbeat",
    "register_agent",
    "rotate_agent_token",
]
