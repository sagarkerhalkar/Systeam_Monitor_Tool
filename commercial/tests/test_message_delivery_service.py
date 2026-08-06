from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
import unittest

from sagar_monitor.messaging import (
    apply_message_migration,
    claim_pending_deliveries,
    delivery_report,
    expire_due_deliveries,
    queue_message,
    record_delivery_failure,
)

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


class MessageDeliveryServiceTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_message_migration(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_retryable_failure_does_not_complete_report(self):
        queued = queue_message(
            self.connection,
            organization_id="org-a",
            canonical_client_ids=["client-a"],
            body="Temporary test",
            max_attempts=2,
            now=NOW,
        )
        claim = claim_pending_deliveries(
            self.connection,
            organization_id="org-a",
            canonical_client_id="client-a",
            now=NOW,
        )[0]
        record_delivery_failure(
            self.connection,
            organization_id="org-a",
            canonical_client_id="client-a",
            delivery_id=claim.delivery_id,
            dispatch_token=claim.dispatch_token,
            error="temporary",
            retry_after_seconds=60,
            now=NOW,
        )
        report = delivery_report(
            self.connection, organization_id="org-a", message_id=queued["message_id"]
        )
        self.assertFalse(report["complete"])
        self.assertEqual(report["terminal_failed"], 0)

    def test_expire_due_returns_delivery_count(self):
        queue_message(
            self.connection,
            organization_id="org-a",
            canonical_client_ids=["client-a", "client-b"],
            body="Expiring test",
            ttl_seconds=60,
            now=NOW,
        )
        changed = expire_due_deliveries(
            self.connection,
            organization_id="org-a",
            now=NOW + timedelta(seconds=61),
        )
        self.assertEqual(changed, 2)


if __name__ == "__main__":
    unittest.main()
