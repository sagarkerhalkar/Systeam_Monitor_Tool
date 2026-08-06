from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Mapping
import unittest
import uuid

from sagar_monitor.edge.runtime import AgentRuntime, RuntimeConfig
from sagar_monitor.edge.transport import TransportError, UnauthorizedError


class MutableClock:
    def __init__(self) -> None:
        self.value = datetime(2026, 8, 6, 10, 0, tzinfo=timezone.utc)

    def __call__(self) -> datetime:
        return self.value

    def advance(self, seconds: int) -> None:
        self.value += timedelta(seconds=seconds)


class FakeCollector:
    def __init__(self, totals: list[tuple[int, int]] | None = None) -> None:
        self.totals = list(totals or [(1000, 500)])
        self.index = 0

    def sample(self) -> dict[str, Any]:
        down, up = self.totals[min(self.index, len(self.totals) - 1)]
        self.index += 1
        return {
            "hostname": "edge-host",
            "identity": {"hostname": "edge-host", "platform": "linux"},
            "hardware": {
                "cpu": {"usage_percent": 25.0},
                "memory": {"used_percent": 50.0},
            },
            "network": {
                "traffic": {
                    "raw_download_total_bytes": down,
                    "raw_upload_total_bytes": up,
                    "current_download_mbps": 1.5,
                    "current_upload_mbps": 0.5,
                }
            },
            "agent": {},
        }


class FakeTransport:
    def __init__(self) -> None:
        self.registrations: list[tuple[str, dict[str, Any]]] = []
        self.heartbeats: list[dict[str, Any]] = []
        self.acknowledgements: list[tuple[str, dict[str, Any]]] = []
        self.fail_heartbeat = False
        self.unauthorized_heartbeat = False
        self.messages: list[dict[str, Any]] = []
        self.token = "agent-token-v1"
        self.token_version = 1

    def register(self, enrollment_token: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.registrations.append((enrollment_token, dict(payload)))
        return {
            "agent_install_id": payload["agent_install_id"],
            "agent_token": self.token,
            "organization_id": "org-a",
            "canonical_client_id": "client-a",
            "token_version": self.token_version,
            "platform": payload["platform"],
        }

    def heartbeat(self, agent_install_id: str, agent_token: str, event: Mapping[str, Any]) -> dict[str, Any]:
        if self.unauthorized_heartbeat:
            raise UnauthorizedError("credential rejected")
        if self.fail_heartbeat:
            raise TransportError("offline", retryable=True)
        self.assert_credential(agent_install_id, agent_token)
        self.heartbeats.append(dict(event))
        return {"ok": True, "heartbeat": {"inserted": True}, "messages": list(self.messages)}

    def acknowledge(
        self,
        agent_install_id: str,
        agent_token: str,
        delivery_id: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        self.assert_credential(agent_install_id, agent_token)
        self.acknowledgements.append((delivery_id, dict(payload)))
        return {"ok": True, "acknowledged": True}

    def status(self, agent_install_id: str, agent_token: str) -> dict[str, Any]:
        self.assert_credential(agent_install_id, agent_token)
        return {"ok": True, "agent": {"agent_install_id": agent_install_id}}

    def rotate(self, agent_install_id: str, agent_token: str, reason: str) -> dict[str, Any]:
        self.assert_credential(agent_install_id, agent_token)
        self.token_version += 1
        self.token = f"agent-token-v{self.token_version}"
        return {"ok": True, "agent_token": self.token, "token_version": self.token_version}

    def assert_credential(self, agent_install_id: str, agent_token: str) -> None:
        if not agent_install_id or agent_token != self.token:
            raise UnauthorizedError()


class EdgeRuntimeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.clock = MutableClock()
        self.transport = FakeTransport()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def runtime(self, collector: FakeCollector | None = None) -> AgentRuntime:
        return AgentRuntime(
            RuntimeConfig(
                state_directory=self.root / "state",
                timezone_name="Asia/Kolkata",
                heartbeat_interval_seconds=60,
                max_heartbeats_per_cycle=20,
                max_receipts_per_cycle=20,
                queue_limit=100,
            ),
            self.transport,
            collector=collector or FakeCollector(),
            clock=self.clock,
            sleeper=lambda _: None,
        )

    def test_registration_and_heartbeat_are_persistent(self) -> None:
        runtime = self.runtime()
        first = runtime.run_cycle(enrollment_token="enrollment-secret")
        self.assertTrue(first.registered)
        self.assertTrue(first.sample_enqueued)
        self.assertEqual(first.heartbeats_sent, 1)
        self.assertEqual(len(self.transport.registrations), 1)
        self.assertEqual(self.transport.registrations[0][0], "enrollment-secret")
        restarted = self.runtime()
        second = restarted.run_cycle(enrollment_token="")
        self.assertFalse(second.registered)
        self.assertEqual(len(self.transport.registrations), 1)
        self.assertEqual(len(self.transport.heartbeats), 2)
        self.assertEqual(
            self.transport.heartbeats[0]["payload"]["identity"]["agent_install_id"],
            self.transport.heartbeats[1]["payload"]["identity"]["agent_install_id"],
        )

    def test_offline_heartbeat_survives_restart_and_retries(self) -> None:
        self.transport.fail_heartbeat = True
        runtime = self.runtime()
        first = runtime.run_cycle(enrollment_token="enrollment-secret")
        self.assertEqual(first.heartbeats_sent, 0)
        self.assertEqual(first.queue_counts["pending_heartbeats"], 1)
        self.transport.fail_heartbeat = False
        self.clock.advance(1000)
        restarted = self.runtime()
        second = restarted.run_cycle(collect_sample=False)
        self.assertEqual(second.heartbeats_sent, 1)
        self.assertEqual(second.queue_counts["pending_heartbeats"], 0)
        self.assertEqual(len(self.transport.heartbeats), 1)

    def test_daily_network_counter_is_not_boot_total(self) -> None:
        collector = FakeCollector([(10_000, 5_000), (10_600, 5_250)])
        runtime = self.runtime(collector)
        runtime.run_cycle(enrollment_token="enrollment-secret")
        self.clock.advance(60)
        runtime.run_cycle()
        first = self.transport.heartbeats[0]["payload"]["network"]["traffic"]
        second = self.transport.heartbeats[1]["payload"]["network"]["traffic"]
        self.assertEqual(first["today_download_bytes"], 0)
        self.assertEqual(first["today_upload_bytes"], 0)
        self.assertEqual(second["today_download_bytes"], 600)
        self.assertEqual(second["today_upload_bytes"], 250)

    def test_message_is_not_acknowledged_until_notifier_marks_displayed(self) -> None:
        delivery_id = "12345678-1234-1234-1234-123456789012"
        self.transport.messages = [
            {
                "delivery_id": delivery_id,
                "message_id": "message-a",
                "dispatch_token": "lease-one",
                "title": "Maintenance",
                "body": "Restart after class",
                "severity": "warning",
                "attempt_count": 1,
                "expires_at": "2026-08-07T00:00:00+00:00",
                "metadata": {},
            }
        ]
        runtime = self.runtime()
        first = runtime.run_cycle(enrollment_token="enrollment-secret")
        self.assertEqual(first.messages_staged, 1)
        self.assertEqual(self.transport.acknowledgements, [])
        self.assertEqual(len(runtime.inbox.pending_messages()), 1)
        runtime.inbox.mark_displayed(delivery_id, {"notifier": "test"})
        second = runtime.run_cycle(collect_sample=False)
        self.assertEqual(second.receipts_sent, 1)
        self.assertEqual(len(self.transport.acknowledgements), 1)
        self.assertEqual(self.transport.acknowledgements[0][0], delivery_id)
        self.assertEqual(runtime.inbox.pending_messages(), [])
        self.assertEqual(second.queue_counts["pending_receipts"], 0)

    def test_redelivery_after_local_ack_reopens_receipt_without_popup(self) -> None:
        delivery_id = "12345678-1234-1234-1234-123456789012"
        message = {
            "delivery_id": delivery_id,
            "message_id": "message-a",
            "dispatch_token": "lease-one",
            "title": "Notice",
            "body": "Hello",
            "severity": "info",
            "attempt_count": 1,
            "expires_at": "2026-08-07T00:00:00+00:00",
            "metadata": {},
        }
        self.transport.messages = [message]
        runtime = self.runtime()
        runtime.run_cycle(enrollment_token="enrollment-secret")
        runtime.inbox.mark_displayed(delivery_id, {"notifier": "test"})
        runtime.run_cycle(collect_sample=False)
        self.assertEqual(len(self.transport.acknowledgements), 1)
        self.transport.messages = [dict(message, dispatch_token="lease-two", attempt_count=2)]
        runtime.run_cycle()
        self.assertEqual(runtime.inbox.pending_messages(), [])
        # The renewed acknowledgement is queued during the heartbeat and sent
        # on the next cycle, preserving the new server lease token.
        runtime.run_cycle(collect_sample=False)
        self.assertEqual(len(self.transport.acknowledgements), 2)
        self.assertEqual(self.transport.acknowledgements[-1][1]["dispatch_token"], "lease-two")

    def test_unauthorized_heartbeat_does_not_drop_event(self) -> None:
        runtime = self.runtime()
        runtime.register("enrollment-secret")
        self.transport.unauthorized_heartbeat = True
        result = runtime.run_cycle()
        self.assertTrue(result.authentication_error)
        self.assertEqual(result.queue_counts["pending_heartbeats"], 1)

    def test_token_rotation_is_atomic_and_survives_restart(self) -> None:
        runtime = self.runtime()
        original, _ = runtime.register("enrollment-secret")
        rotated = runtime.rotate_token("scheduled")
        self.assertNotEqual(rotated.agent_token, original.agent_token)
        self.assertEqual(rotated.token_version, 2)
        restarted = self.runtime()
        stored = restarted.credentials.load_credential()
        self.assertEqual(stored.agent_token, rotated.agent_token)
        result = restarted.run_cycle()
        self.assertFalse(result.authentication_error)

    def test_invalid_timezone_and_short_interval_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            RuntimeConfig(state_directory=self.root, timezone_name="Not/AZone").normalized()
        with self.assertRaises(ValueError):
            RuntimeConfig(state_directory=self.root, heartbeat_interval_seconds=1).normalized()


if __name__ == "__main__":
    unittest.main()
