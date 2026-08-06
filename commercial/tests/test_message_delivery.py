from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import sqlite3
import unittest

from sagar_monitor.messaging.delivery import (
    acknowledge_delivery,
    apply_message_migration,
    claim_pending_deliveries,
    delivery_report,
    queue_message,
    record_delivery_failure,
)

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


class MessageDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_message_migration(self.connection)

    def tearDown(self):
        self.connection.close()

    def queue(self, **overrides):
        values = {
            "organization_id": "org-a",
            "canonical_client_ids": ["client-a"],
            "title": "Maintenance",
            "body": "Restart after class.",
            "now": NOW,
        }
        values.update(overrides)
        return queue_message(self.connection, **values)

    def test_queue_deduplicates_targets_and_creates_events(self):
        result = self.queue(canonical_client_ids=["client-a", "client-a", "client-b"])
        self.assertEqual(result["target_count"], 2)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM client_message_deliveries_v1").fetchone()[0],
            2,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM client_message_delivery_events_v1").fetchone()[0],
            2,
        )

    def test_claim_is_client_scoped_and_stores_only_token_hash(self):
        self.queue(canonical_client_ids=["client-a", "client-b"])
        claims = claim_pending_deliveries(
            self.connection,
            organization_id="org-a",
            canonical_client_id="client-a",
            now=NOW,
        )
        self.assertEqual(len(claims), 1)
        claim = claims[0]
        stored = self.connection.execute(
            "SELECT state,dispatch_token_hash,attempt_count FROM client_message_deliveries_v1 WHERE delivery_id=?",
            (claim.delivery_id,),
        ).fetchone()
        self.assertEqual(stored[0], "DISPATCHED")
        self.assertNotEqual(stored[1], claim.dispatch_token)
        self.assertEqual(stored[1], hashlib.sha256(claim.dispatch_token.encode()).hexdigest())
        self.assertEqual(stored[2], 1)
        self.assertEqual(
            self.connection.execute(
                "SELECT state FROM client_message_deliveries_v1 WHERE canonical_client_id='client-b'"
            ).fetchone()[0],
            "QUEUED",
        )

    def test_acknowledgement_is_real_and_idempotent(self):
        queued = self.queue()
        claim = claim_pending_deliveries(
            self.connection,
            organization_id="org-a",
            canonical_client_id="client-a",
            now=NOW,
        )[0]
        first = acknowledge_delivery(
            self.connection,
            organization_id="org-a",
            canonical_client_id="client-a",
            delivery_id=claim.delivery_id,
            dispatch_token=claim.dispatch_token,
            client_receipt_id="local-receipt-1",
            now=NOW + timedelta(seconds=2),
        )
        second = acknowledge_delivery(
            self.connection,
            organization_id="org-a",
            canonical_client_id="client-a",
            delivery_id=claim.delivery_id,
            dispatch_token=claim.dispatch_token,
            client_receipt_id="local-receipt-1",
            now=NOW + timedelta(seconds=3),
        )
        self.assertTrue(first["acknowledged"])
        self.assertFalse(first["idempotent"])
        self.assertTrue(second["idempotent"])
        self.assertEqual(
            self.connection.execute(
                "SELECT state FROM client_message_deliveries_v1 WHERE delivery_id=?",
                (claim.delivery_id,),
            ).fetchone()[0],
            "ACKNOWLEDGED",
        )
        report = delivery_report(
            self.connection, organization_id="org-a", message_id=queued["message_id"]
        )
        self.assertEqual(report["counts"]["ACKNOWLEDGED"], 1)

    def test_wrong_token_or_client_cannot_acknowledge(self):
        self.queue()
        claim = claim_pending_deliveries(
            self.connection,
            organization_id="org-a",
            canonical_client_id="client-a",
            now=NOW,
        )[0]
        with self.assertRaises(PermissionError):
            acknowledge_delivery(
                self.connection,
                organization_id="org-a",
                canonical_client_id="client-b",
                delivery_id=claim.delivery_id,
                dispatch_token=claim.dispatch_token,
                client_receipt_id="r1",
                now=NOW,
            )
        with self.assertRaises(PermissionError):
            acknowledge_delivery(
                self.connection,
                organization_id="org-a",
                canonical_client_id="client-a",
                delivery_id=claim.delivery_id,
                dispatch_token="wrong",
                client_receipt_id="r1",
                now=NOW,
            )

    def test_unacknowledged_lease_retries_same_delivery_id(self):
        self.queue()
        first = claim_pending_deliveries(
            self.connection,
            organization_id="org-a",
            canonical_client_id="client-a",
            lease_seconds=30,
            now=NOW,
        )[0]
        second = claim_pending_deliveries(
            self.connection,
            organization_id="org-a",
            canonical_client_id="client-a",
            lease_seconds=30,
            now=NOW + timedelta(seconds=31),
        )[0]
        self.assertEqual(first.delivery_id, second.delivery_id)
        self.assertNotEqual(first.dispatch_token, second.dispatch_token)
        self.assertEqual(second.attempt_count, 2)

    def test_client_failure_respects_backoff_then_retries(self):
        self.queue()
        first = claim_pending_deliveries(
            self.connection,
            organization_id="org-a",
            canonical_client_id="client-a",
            now=NOW,
        )[0]
        failure = record_delivery_failure(
            self.connection,
            organization_id="org-a",
            canonical_client_id="client-a",
            delivery_id=first.delivery_id,
            dispatch_token=first.dispatch_token,
            error="display service unavailable",
            retry_after_seconds=60,
            now=NOW + timedelta(seconds=1),
        )
        self.assertFalse(failure["terminal"])
        self.assertEqual(
            claim_pending_deliveries(
                self.connection,
                organization_id="org-a",
                canonical_client_id="client-a",
                now=NOW + timedelta(seconds=30),
            ),
            [],
        )
        retry = claim_pending_deliveries(
            self.connection,
            organization_id="org-a",
            canonical_client_id="client-a",
            now=NOW + timedelta(seconds=61),
        )[0]
        self.assertEqual(retry.delivery_id, first.delivery_id)
        self.assertEqual(retry.attempt_count, 2)

    def test_max_attempt_failure_is_not_reclaimed(self):
        self.queue(max_attempts=1)
        claim = claim_pending_deliveries(
            self.connection,
            organization_id="org-a",
            canonical_client_id="client-a",
            now=NOW,
        )[0]
        result = record_delivery_failure(
            self.connection,
            organization_id="org-a",
            canonical_client_id="client-a",
            delivery_id=claim.delivery_id,
            dispatch_token=claim.dispatch_token,
            error="permanent error",
            retry_after_seconds=1,
            now=NOW,
        )
        self.assertTrue(result["terminal"])
        self.assertEqual(
            claim_pending_deliveries(
                self.connection,
                organization_id="org-a",
                canonical_client_id="client-a",
                now=NOW + timedelta(seconds=2),
            ),
            [],
        )

    def test_expired_message_is_never_dispatched(self):
        queued = self.queue(ttl_seconds=60)
        self.assertEqual(
            claim_pending_deliveries(
                self.connection,
                organization_id="org-a",
                canonical_client_id="client-a",
                now=NOW + timedelta(seconds=61),
            ),
            [],
        )
        report = delivery_report(
            self.connection, organization_id="org-a", message_id=queued["message_id"]
        )
        self.assertEqual(report["counts"]["EXPIRED"], 1)

    def test_report_is_read_only(self):
        queued = self.queue()
        before = self.connection.total_changes
        report = delivery_report(
            self.connection, organization_id="org-a", message_id=queued["message_id"]
        )
        self.assertEqual(report["total"], 1)
        self.assertEqual(self.connection.total_changes, before)

    def test_migration_is_idempotent(self):
        apply_message_migration(self.connection)
        apply_message_migration(self.connection)
        tables = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("client_messages_v1", tables)
        self.assertIn("client_message_receipts_v1", tables)
        self.assertIn("client_message_delivery_events_v1", tables)


if __name__ == "__main__":
    unittest.main()
