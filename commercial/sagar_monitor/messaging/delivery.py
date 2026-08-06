from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import hashlib
import hmac
import json
import secrets
import sqlite3
import uuid


MIGRATION_PATH = Path(__file__).resolve().parents[2] / "migrations" / "0006_message_delivery.sql"
STATES = {"QUEUED", "DISPATCHED", "ACKNOWLEDGED", "FAILED", "EXPIRED"}
SEVERITIES = {"info", "warning", "critical"}


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


def apply_message_migration(connection: sqlite3.Connection) -> None:
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))


def _event(
    connection: sqlite3.Connection,
    *,
    delivery_id: str,
    organization_id: str,
    from_state: str,
    to_state: str,
    created_at: datetime | str,
    reason: str = "",
    detail: Mapping[str, Any] | None = None,
) -> None:
    if to_state not in STATES:
        raise ValueError(f"unsupported delivery state: {to_state}")
    connection.execute(
        """INSERT INTO client_message_delivery_events_v1(
            event_id,delivery_id,organization_id,from_state,to_state,created_at,reason,detail_json
        ) VALUES(?,?,?,?,?,?,?,?)""",
        (
            str(uuid.uuid4()),
            delivery_id,
            organization_id,
            from_state,
            to_state,
            _iso(created_at),
            str(reason or "")[:500],
            json.dumps(dict(detail or {}), ensure_ascii=False, sort_keys=True),
        ),
    )


def queue_message(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    canonical_client_ids: Iterable[str],
    body: str,
    title: str = "",
    severity: str = "info",
    created_by_user_id: str = "",
    not_before: datetime | str | None = None,
    ttl_seconds: int = 24 * 60 * 60,
    max_attempts: int = 5,
    metadata: Mapping[str, Any] | None = None,
    now: datetime | str | None = None,
    message_id: str | None = None,
) -> dict[str, Any]:
    """Queue one logical message for unique canonical clients."""
    apply_message_migration(connection)
    clean_org = str(organization_id or "").strip()
    clean_body = str(body or "").strip()
    clean_severity = str(severity or "info").strip().lower()
    clients = sorted({str(value or "").strip() for value in canonical_client_ids if str(value or "").strip()})
    if not clean_org:
        raise ValueError("organization_id is required")
    if not clean_body:
        raise ValueError("message body is required")
    if clean_severity not in SEVERITIES:
        raise ValueError(f"unsupported severity: {severity}")
    if not clients:
        raise ValueError("at least one canonical client is required")
    if ttl_seconds < 60 or ttl_seconds > 30 * 24 * 60 * 60:
        raise ValueError("message TTL must be between 60 seconds and 30 days")
    if max_attempts < 1 or max_attempts > 100:
        raise ValueError("max_attempts must be between 1 and 100")

    created = _utc(now)
    available = _utc(not_before) if not_before is not None else created
    if available < created:
        available = created
    expires = created + timedelta(seconds=ttl_seconds)
    if available >= expires:
        raise ValueError("not_before must be earlier than expires_at")
    message_id = str(message_id or uuid.uuid4())

    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """INSERT INTO client_messages_v1(
                message_id,organization_id,created_by_user_id,title,body,severity,
                created_at,not_before,expires_at,metadata_json
            ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                message_id,
                clean_org,
                str(created_by_user_id or "").strip(),
                str(title or "").strip()[:200],
                clean_body,
                clean_severity,
                created.isoformat(),
                available.isoformat(),
                expires.isoformat(),
                json.dumps(dict(metadata or {}), ensure_ascii=False, sort_keys=True),
            ),
        )
        deliveries: list[str] = []
        for client_id in clients:
            delivery_id = str(uuid.uuid4())
            connection.execute(
                """INSERT INTO client_message_deliveries_v1(
                    delivery_id,message_id,organization_id,canonical_client_id,state,
                    attempt_count,max_attempts,queued_at,next_attempt_at,version
                ) VALUES(?,?,?,?, 'QUEUED',0,?,?,?,0)""",
                (
                    delivery_id,
                    message_id,
                    clean_org,
                    client_id,
                    max_attempts,
                    created.isoformat(),
                    available.isoformat(),
                ),
            )
            _event(
                connection,
                delivery_id=delivery_id,
                organization_id=clean_org,
                from_state="",
                to_state="QUEUED",
                created_at=created,
                reason="message queued",
            )
            deliveries.append(delivery_id)
        connection.commit()
        return {
            "message_id": message_id,
            "delivery_ids": deliveries,
            "target_count": len(deliveries),
            "expires_at": expires.isoformat(),
        }
    except Exception:
        connection.rollback()
        raise


@dataclass(frozen=True)
class DeliveryClaim:
    delivery_id: str
    message_id: str
    organization_id: str
    canonical_client_id: str
    dispatch_token: str
    title: str
    body: str
    severity: str
    attempt_count: int
    expires_at: str
    metadata: dict[str, Any]


def _expire_and_release(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    canonical_client_id: str | None,
    now: datetime,
) -> None:
    params: list[Any] = [now.isoformat(), organization_id]
    client_clause = ""
    if canonical_client_id:
        client_clause = " AND d.canonical_client_id=?"
        params.append(canonical_client_id)

    expired_rows = connection.execute(
        f"""SELECT d.delivery_id,d.state FROM client_message_deliveries_v1 d
            JOIN client_messages_v1 m ON m.message_id=d.message_id
            WHERE m.expires_at<=? AND d.organization_id=?{client_clause}
              AND d.state IN ('QUEUED','DISPATCHED','FAILED')""",
        params,
    ).fetchall()
    for delivery_id, old_state in expired_rows:
        connection.execute(
            """UPDATE client_message_deliveries_v1
               SET state='EXPIRED',expired_at=?,dispatch_token_hash='',lease_expires_at=NULL,version=version+1
               WHERE delivery_id=?""",
            (now.isoformat(), delivery_id),
        )
        _event(
            connection,
            delivery_id=delivery_id,
            organization_id=organization_id,
            from_state=old_state,
            to_state="EXPIRED",
            created_at=now,
            reason="message TTL expired",
        )

    stale_params: list[Any] = [now.isoformat(), organization_id]
    stale_clause = ""
    if canonical_client_id:
        stale_clause = " AND canonical_client_id=?"
        stale_params.append(canonical_client_id)
    stale_rows = connection.execute(
        f"""SELECT delivery_id,attempt_count,max_attempts FROM client_message_deliveries_v1
            WHERE state='DISPATCHED' AND lease_expires_at<=? AND organization_id=?{stale_clause}""",
        stale_params,
    ).fetchall()
    for delivery_id, attempts, max_attempts in stale_rows:
        if int(attempts) >= int(max_attempts):
            new_state = "FAILED"
            next_attempt = now.isoformat()
            reason = "dispatch acknowledgement timeout; maximum attempts reached"
        else:
            new_state = "QUEUED"
            next_attempt = now.isoformat()
            reason = "dispatch acknowledgement timeout; queued for retry"
        connection.execute(
            """UPDATE client_message_deliveries_v1
               SET state=?,next_attempt_at=?,dispatch_token_hash='',lease_expires_at=NULL,
                   last_error=?,failed_at=CASE WHEN ?='FAILED' THEN ? ELSE failed_at END,
                   version=version+1
               WHERE delivery_id=?""",
            (new_state, next_attempt, reason, new_state, now.isoformat(), delivery_id),
        )
        _event(
            connection,
            delivery_id=delivery_id,
            organization_id=organization_id,
            from_state="DISPATCHED",
            to_state=new_state,
            created_at=now,
            reason=reason,
        )


def claim_pending_deliveries(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    canonical_client_id: str,
    limit: int = 20,
    lease_seconds: int = 120,
    now: datetime | str | None = None,
) -> list[DeliveryClaim]:
    """Lease due deliveries. Raw dispatch tokens are returned once and only hashes are stored."""
    if limit < 1 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    if lease_seconds < 30 or lease_seconds > 3600:
        raise ValueError("lease_seconds must be between 30 and 3600")
    apply_message_migration(connection)
    anchor = _utc(now)
    clean_org = str(organization_id or "").strip()
    clean_client = str(canonical_client_id or "").strip()
    if not clean_org or not clean_client:
        raise ValueError("organization_id and canonical_client_id are required")
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        _expire_and_release(
            connection,
            organization_id=clean_org,
            canonical_client_id=clean_client,
            now=anchor,
        )
        rows = connection.execute(
            """SELECT d.delivery_id,d.message_id,d.organization_id,d.canonical_client_id,
                      d.attempt_count,d.max_attempts,m.title,m.body,m.severity,m.expires_at,m.metadata_json
               FROM client_message_deliveries_v1 d
               JOIN client_messages_v1 m ON m.message_id=d.message_id
               WHERE d.organization_id=? AND d.canonical_client_id=?
                 AND d.state IN ('QUEUED','FAILED')
                 AND d.next_attempt_at<=? AND m.not_before<=? AND m.expires_at>?
                 AND d.attempt_count<d.max_attempts
               ORDER BY d.next_attempt_at,d.queued_at,d.delivery_id
               LIMIT ?""",
            (
                clean_org,
                clean_client,
                anchor.isoformat(),
                anchor.isoformat(),
                anchor.isoformat(),
                limit,
            ),
        ).fetchall()
        claims: list[DeliveryClaim] = []
        for row in rows:
            dispatch_token = secrets.token_urlsafe(32)
            attempt_count = int(row["attempt_count"]) + 1
            lease_expires = anchor + timedelta(seconds=lease_seconds)
            previous_state = connection.execute(
                "SELECT state FROM client_message_deliveries_v1 WHERE delivery_id=?",
                (row["delivery_id"],),
            ).fetchone()[0]
            connection.execute(
                """UPDATE client_message_deliveries_v1
                   SET state='DISPATCHED',attempt_count=?,dispatched_at=?,lease_expires_at=?,
                       dispatch_token_hash=?,last_error='',version=version+1
                   WHERE delivery_id=?""",
                (
                    attempt_count,
                    anchor.isoformat(),
                    lease_expires.isoformat(),
                    _sha256(dispatch_token),
                    row["delivery_id"],
                ),
            )
            _event(
                connection,
                delivery_id=row["delivery_id"],
                organization_id=clean_org,
                from_state=previous_state,
                to_state="DISPATCHED",
                created_at=anchor,
                reason="delivery leased to client",
                detail={"attempt_count": attempt_count, "lease_expires_at": lease_expires.isoformat()},
            )
            try:
                metadata = json.loads(row["metadata_json"] or "{}")
            except (ValueError, TypeError, json.JSONDecodeError):
                metadata = {}
            claims.append(
                DeliveryClaim(
                    delivery_id=row["delivery_id"],
                    message_id=row["message_id"],
                    organization_id=clean_org,
                    canonical_client_id=clean_client,
                    dispatch_token=dispatch_token,
                    title=row["title"],
                    body=row["body"],
                    severity=row["severity"],
                    attempt_count=attempt_count,
                    expires_at=row["expires_at"],
                    metadata=metadata if isinstance(metadata, dict) else {},
                )
            )
        connection.commit()
        return claims
    except Exception:
        connection.rollback()
        raise


def acknowledge_delivery(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    canonical_client_id: str,
    delivery_id: str,
    dispatch_token: str,
    client_receipt_id: str,
    detail: Mapping[str, Any] | None = None,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    """Acknowledge display/receipt. Duplicate client receipt IDs are idempotent."""
    apply_message_migration(connection)
    anchor = _utc(now)
    if not client_receipt_id:
        raise ValueError("client_receipt_id is required")
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        existing = connection.execute(
            """SELECT receipt_id,acknowledged_at FROM client_message_receipts_v1
               WHERE delivery_id=? AND client_receipt_id=?""",
            (delivery_id, client_receipt_id),
        ).fetchone()
        if existing:
            connection.commit()
            return {
                "acknowledged": True,
                "idempotent": True,
                "receipt_id": existing["receipt_id"],
                "acknowledged_at": existing["acknowledged_at"],
            }
        row = connection.execute(
            """SELECT state,dispatch_token_hash,lease_expires_at,organization_id,canonical_client_id
               FROM client_message_deliveries_v1 WHERE delivery_id=?""",
            (delivery_id,),
        ).fetchone()
        if not row:
            connection.rollback()
            raise KeyError("delivery not found")
        if row["organization_id"] != organization_id or row["canonical_client_id"] != canonical_client_id:
            connection.rollback()
            raise PermissionError("delivery does not belong to this organization/client")
        if row["state"] == "ACKNOWLEDGED":
            connection.rollback()
            return {"acknowledged": True, "idempotent": True, "receipt_id": "", "acknowledged_at": ""}
        if row["state"] != "DISPATCHED":
            connection.rollback()
            raise RuntimeError(f"delivery cannot be acknowledged from state {row['state']}")
        if _utc(row["lease_expires_at"]) < anchor:
            connection.rollback()
            raise RuntimeError("dispatch lease has expired")
        if not hmac.compare_digest(str(row["dispatch_token_hash"]), _sha256(dispatch_token)):
            connection.rollback()
            raise PermissionError("invalid dispatch token")
        receipt_id = str(uuid.uuid4())
        connection.execute(
            """INSERT INTO client_message_receipts_v1(
                receipt_id,delivery_id,organization_id,canonical_client_id,client_receipt_id,
                acknowledged_at,detail_json
            ) VALUES(?,?,?,?,?,?,?)""",
            (
                receipt_id,
                delivery_id,
                organization_id,
                canonical_client_id,
                client_receipt_id,
                anchor.isoformat(),
                json.dumps(dict(detail or {}), ensure_ascii=False, sort_keys=True),
            ),
        )
        connection.execute(
            """UPDATE client_message_deliveries_v1
               SET state='ACKNOWLEDGED',acknowledged_at=?,dispatch_token_hash='',
                   lease_expires_at=NULL,last_error='',version=version+1
               WHERE delivery_id=?""",
            (anchor.isoformat(), delivery_id),
        )
        _event(
            connection,
            delivery_id=delivery_id,
            organization_id=organization_id,
            from_state="DISPATCHED",
            to_state="ACKNOWLEDGED",
            created_at=anchor,
            reason="client displayed/acknowledged message",
            detail={"client_receipt_id": client_receipt_id},
        )
        connection.commit()
        return {
            "acknowledged": True,
            "idempotent": False,
            "receipt_id": receipt_id,
            "acknowledged_at": anchor.isoformat(),
        }
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise


def record_delivery_failure(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    canonical_client_id: str,
    delivery_id: str,
    dispatch_token: str,
    error: str,
    retry_after_seconds: int = 60,
    now: datetime | str | None = None,
) -> dict[str, Any]:
    if retry_after_seconds < 1 or retry_after_seconds > 24 * 60 * 60:
        raise ValueError("retry_after_seconds must be between 1 second and 1 day")
    apply_message_migration(connection)
    anchor = _utc(now)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN IMMEDIATE")
        row = connection.execute(
            """SELECT state,dispatch_token_hash,organization_id,canonical_client_id,
                      attempt_count,max_attempts
               FROM client_message_deliveries_v1 WHERE delivery_id=?""",
            (delivery_id,),
        ).fetchone()
        if not row:
            connection.rollback()
            raise KeyError("delivery not found")
        if row["organization_id"] != organization_id or row["canonical_client_id"] != canonical_client_id:
            connection.rollback()
            raise PermissionError("delivery does not belong to this organization/client")
        if row["state"] != "DISPATCHED":
            connection.rollback()
            raise RuntimeError(f"delivery cannot fail from state {row['state']}")
        if not hmac.compare_digest(str(row["dispatch_token_hash"]), _sha256(dispatch_token)):
            connection.rollback()
            raise PermissionError("invalid dispatch token")
        terminal = int(row["attempt_count"]) >= int(row["max_attempts"])
        next_attempt = anchor + timedelta(seconds=retry_after_seconds)
        connection.execute(
            """UPDATE client_message_deliveries_v1
               SET state='FAILED',failed_at=?,next_attempt_at=?,last_error=?,
                   dispatch_token_hash='',lease_expires_at=NULL,version=version+1
               WHERE delivery_id=?""",
            (
                anchor.isoformat(),
                next_attempt.isoformat(),
                str(error or "delivery failed")[:2000],
                delivery_id,
            ),
        )
        _event(
            connection,
            delivery_id=delivery_id,
            organization_id=organization_id,
            from_state="DISPATCHED",
            to_state="FAILED",
            created_at=anchor,
            reason="client reported delivery failure",
            detail={"terminal": terminal, "retry_after_seconds": retry_after_seconds},
        )
        connection.commit()
        return {
            "failed": True,
            "terminal": terminal,
            "next_attempt_at": next_attempt.isoformat(),
            "attempt_count": int(row["attempt_count"]),
        }
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise


def expire_due_deliveries(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    now: datetime | str | None = None,
) -> int:
    apply_message_migration(connection)
    anchor = _utc(now)
    before = connection.total_changes
    try:
        connection.execute("BEGIN IMMEDIATE")
        _expire_and_release(
            connection,
            organization_id=organization_id,
            canonical_client_id=None,
            now=anchor,
        )
        changed = connection.total_changes - before
        connection.commit()
        return changed
    except Exception:
        connection.rollback()
        raise


def delivery_report(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    message_id: str,
) -> dict[str, Any]:
    """Read aggregate delivery status without changing state."""
    before = connection.total_changes
    connection.row_factory = sqlite3.Row
    message = connection.execute(
        """SELECT message_id,title,severity,created_at,not_before,expires_at
           FROM client_messages_v1 WHERE organization_id=? AND message_id=?""",
        (organization_id, message_id),
    ).fetchone()
    if not message:
        raise KeyError("message not found")
    counts = {
        row["state"]: int(row["count"])
        for row in connection.execute(
            """SELECT state,COUNT(*) AS count FROM client_message_deliveries_v1
               WHERE organization_id=? AND message_id=? GROUP BY state""",
            (organization_id, message_id),
        ).fetchall()
    }
    total = sum(counts.values())
    if connection.total_changes != before:
        raise RuntimeError("delivery report unexpectedly changed the database")
    return {
        **dict(message),
        "total": total,
        "counts": {state: counts.get(state, 0) for state in sorted(STATES)},
        "complete": total > 0 and counts.get("ACKNOWLEDGED", 0) + counts.get("EXPIRED", 0) + (
            counts.get("FAILED", 0)
        ) == total,
    }
