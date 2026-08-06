from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import unittest
import uuid

from sagar_monitor.edge.counters import DailyCounterStore
from sagar_monitor.edge.inbox import LocalInbox
from sagar_monitor.edge.state import CredentialStore, EdgeQueue


NOW = datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc)


class EdgeStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_permanent_identity_and_atomic_credential_survive_restart(self) -> None:
        store = CredentialStore(self.root / "state")
        agent_id = store.ensure_agent_install_id()
        self.assertEqual(agent_id, store.ensure_agent_install_id())
        registration = {
            "agent_install_id": agent_id,
            "agent_token": "secret-agent-token",
            "organization_id": "org-a",
            "canonical_client_id": "client-a",
            "token_version": 1,
            "platform": "linux",
        }
        credential = store.save_registration(registration)
        restarted = CredentialStore(self.root / "state").load_credential()
        self.assertEqual(restarted, credential)
        raw = json.loads(store.credential_path.read_text(encoding="utf-8"))
        self.assertEqual(raw["agent_token"], "secret-agent-token")
        self.assertNotIn("enrollment", store.credential_path.read_text(encoding="utf-8"))
        if os.name != "nt":
            self.assertEqual(store.credential_path.stat().st_mode & 0o777, 0o600)

    def test_registration_identity_mismatch_is_rejected(self) -> None:
        store = CredentialStore(self.root / "state")
        store.ensure_agent_install_id()
        with self.assertRaises(ValueError):
            store.save_registration(
                {
                    "agent_install_id": str(uuid.uuid4()),
                    "agent_token": "token",
                }
            )

    def test_heartbeat_queue_is_idempotent_and_persistent(self) -> None:
        path = self.root / "queue.sqlite3"
        queue = EdgeQueue(path, max_heartbeats=100)
        self.assertTrue(
            queue.enqueue_heartbeat(
                event_id="hb:event-0001",
                payload={"hostname": "alpha"},
                timezone_name="Asia/Kolkata",
                now=NOW,
            )
        )
        self.assertFalse(
            queue.enqueue_heartbeat(
                event_id="hb:event-0001",
                payload={"hostname": "alpha"},
                timezone_name="Asia/Kolkata",
                now=NOW,
            )
        )
        restarted = EdgeQueue(path, max_heartbeats=100)
        item = restarted.next_heartbeat(NOW)
        self.assertIsNotNone(item)
        self.assertEqual(item.event_id, "hb:event-0001")
        restarted.fail_heartbeat(item.event_id, "offline", retry_after_seconds=60, now=NOW)
        self.assertIsNone(restarted.next_heartbeat(NOW + timedelta(seconds=59)))
        self.assertEqual(restarted.next_heartbeat(NOW + timedelta(seconds=60)).attempts, 1)
        restarted.complete_heartbeat(item.event_id)
        self.assertEqual(restarted.counts()["pending_heartbeats"], 0)

    def test_queue_limit_trims_oldest_heartbeats(self) -> None:
        queue = EdgeQueue(self.root / "queue.sqlite3", max_heartbeats=100)
        for number in range(105):
            queue.enqueue_heartbeat(
                event_id=f"hb:event-{number:04d}",
                payload={"number": number},
                timezone_name="Asia/Kolkata",
                now=NOW,
            )
        self.assertEqual(queue.counts()["pending_heartbeats"], 100)
        self.assertEqual(queue.next_heartbeat(NOW).event_id, "hb:event-0005")

    def test_daily_counter_starts_at_zero_and_handles_reset(self) -> None:
        counters = DailyCounterStore(self.root / "queue.sqlite3")
        self.assertEqual(
            counters.update(
                local_day="2026-08-06",
                download_total=1000,
                upload_total=500,
                now=NOW,
            ),
            (0, 0),
        )
        self.assertEqual(
            counters.update(
                local_day="2026-08-06",
                download_total=1600,
                upload_total=900,
                now=NOW + timedelta(minutes=1),
            ),
            (600, 400),
        )
        self.assertEqual(
            counters.update(
                local_day="2026-08-06",
                download_total=100,
                upload_total=50,
                now=NOW + timedelta(minutes=2),
            ),
            (700, 450),
        )
        self.assertEqual(
            counters.update(
                local_day="2026-08-07",
                download_total=500,
                upload_total=250,
                now=NOW + timedelta(days=1),
            ),
            (0, 0),
        )

    def test_inbox_updates_lease_without_duplicate_display(self) -> None:
        inbox = LocalInbox(self.root / "messages")
        message = {
            "delivery_id": "12345678-1234-1234-1234-123456789012",
            "message_id": "message-a",
            "dispatch_token": "lease-one",
            "title": "Notice",
            "body": "Hello",
            "severity": "info",
        }
        self.assertTrue(inbox.stage(message))
        renewed = dict(message, dispatch_token="lease-two")
        self.assertFalse(inbox.stage(renewed))
        pending = inbox.pending_messages()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["dispatch_token"], "lease-two")
        inbox.mark_displayed(message["delivery_id"], {"notifier": "test"})
        displayed = inbox.displayed_messages()
        self.assertEqual(len(displayed), 1)
        self.assertEqual(displayed[0][1]["detail"]["notifier"], "test")
        inbox.complete(message["delivery_id"])
        self.assertEqual(inbox.pending_messages(), [])

    def test_receipt_queue_updates_dispatch_lease_and_acknowledges(self) -> None:
        queue = EdgeQueue(self.root / "queue.sqlite3", max_heartbeats=100)
        message = {
            "delivery_id": "12345678-1234-1234-1234-123456789012",
            "message_id": "message-a",
            "dispatch_token": "lease-one",
            "title": "Notice",
            "body": "Hello",
            "severity": "warning",
        }
        first, receipt_id = queue.cache_message(message, now=NOW)
        self.assertTrue(first)
        receipt = queue.next_receipt(NOW)
        self.assertEqual(receipt.dispatch_token, "lease-one")
        self.assertEqual(receipt.client_receipt_id, receipt_id)
        queue.cache_message(dict(message, dispatch_token="lease-two"), now=NOW)
        self.assertEqual(queue.next_receipt(NOW).dispatch_token, "lease-two")
        queue.complete_receipt(message["delivery_id"], now=NOW)
        self.assertEqual(queue.counts()["pending_receipts"], 0)
        self.assertEqual(queue.counts()["unacknowledged_messages"], 0)


if __name__ == "__main__":
    unittest.main()
