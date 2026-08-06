from __future__ import annotations

from typing import Any
import sqlite3

from .delivery import (
    DeliveryClaim,
    STATES,
    _utc,
    acknowledge_delivery,
    apply_message_migration,
    claim_pending_deliveries,
    expire_due_deliveries as _expire_due_deliveries,
    queue_message,
    record_delivery_failure,
)


def expire_due_deliveries(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    now=None,
) -> int:
    """Expire/release due rows and return the number of affected deliveries."""
    apply_message_migration(connection)
    anchor = _utc(now)
    affected = int(
        connection.execute(
            """SELECT COUNT(*) FROM (
                   SELECT d.delivery_id FROM client_message_deliveries_v1 d
                   JOIN client_messages_v1 m ON m.message_id=d.message_id
                   WHERE d.organization_id=? AND m.expires_at<=?
                     AND d.state IN ('QUEUED','DISPATCHED','FAILED')
                   UNION
                   SELECT d.delivery_id FROM client_message_deliveries_v1 d
                   WHERE d.organization_id=? AND d.state='DISPATCHED'
                     AND d.lease_expires_at<=?
               )""",
            (organization_id, anchor.isoformat(), organization_id, anchor.isoformat()),
        ).fetchone()[0]
    )
    _expire_due_deliveries(connection, organization_id=organization_id, now=anchor)
    return affected


def delivery_report(
    connection: sqlite3.Connection,
    *,
    organization_id: str,
    message_id: str,
) -> dict[str, Any]:
    """Read aggregate status; retryable failures do not mark a message complete."""
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
    terminal_failed = int(
        connection.execute(
            """SELECT COUNT(*) FROM client_message_deliveries_v1
               WHERE organization_id=? AND message_id=? AND state='FAILED'
                 AND attempt_count>=max_attempts""",
            (organization_id, message_id),
        ).fetchone()[0]
    )
    total = sum(counts.values())
    if connection.total_changes != before:
        raise RuntimeError("delivery report unexpectedly changed the database")
    return {
        **dict(message),
        "total": total,
        "counts": {state: counts.get(state, 0) for state in sorted(STATES)},
        "terminal_failed": terminal_failed,
        "complete": total > 0
        and counts.get("ACKNOWLEDGED", 0) + counts.get("EXPIRED", 0) + terminal_failed == total,
    }


__all__ = [
    "DeliveryClaim",
    "acknowledge_delivery",
    "apply_message_migration",
    "claim_pending_deliveries",
    "delivery_report",
    "expire_due_deliveries",
    "queue_message",
    "record_delivery_failure",
]
