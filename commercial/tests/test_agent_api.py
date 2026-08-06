from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from sagar_monitor.api import AgentAPI, Request
from sagar_monitor.messaging import queue_message
from sagar_monitor.security import create_enrollment_token, create_organization


NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


def json_request(method: str, target: str, payload=None, headers=None, remote_addr="10.0.0.1") -> Request:
    merged = {"Content-Type": "application/json"}
    merged.update(headers or {})
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    return Request(method=method, target=target, headers=merged, body=body, remote_addr=remote_addr)


def heartbeat_payload(hostname: str, down: int, up: int = 0) -> dict:
    return {
        "hostname": hostname,
        "identity": {"hostname": hostname},
        "os": {"name": "Windows 11"},
        "hardware": {
            "cpu": {"usage_percent": 30},
            "memory": {"used_percent": 50},
        },
        "network": {
            "traffic": {
                "today_download_bytes": down,
                "today_upload_bytes": up,
                "current_download_mbps": 12.5,
                "current_upload_mbps": 3.5,
            }
        },
    }


class AgentAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "commercial.db"
        self.now = NOW
        self.api = AgentAPI(
            self.db,
            clock=lambda: self.now,
            max_body_bytes=8192,
            registration_limit=2,
            registration_window_seconds=60,
        )
        connection = sqlite3.connect(self.db)
        try:
            create_organization(connection, name="Organization A", organization_id="org-a", now=self.now)
            create_organization(connection, name="Organization B", organization_id="org-b", now=self.now)
        finally:
            connection.close()

    def tearDown(self):
        self.temp.cleanup()

    def enrollment(self, organization_id="org-a", max_uses=1, ttl_seconds=3600) -> str:
        connection = sqlite3.connect(self.db)
        try:
            return create_enrollment_token(
                connection,
                organization_id=organization_id,
                max_uses=max_uses,
                ttl_seconds=ttl_seconds,
                now=self.now,
            )
        finally:
            connection.close()

    def register(self, organization_id="org-a", hostname="pc-a", agent_id=None, remote="10.0.0.1"):
        token = self.enrollment(organization_id)
        agent_id = agent_id or str(uuid.uuid4())
        response = self.api.handle(
            json_request(
                "POST",
                "/api/v1/agents/register",
                {
                    "agent_install_id": agent_id,
                    "platform": "windows",
                    "hostname": hostname,
                    "metadata": {"installer": "test"},
                },
                headers={"Authorization": f"Enrollment {token}"},
                remote_addr=remote,
            )
        )
        self.assertEqual(response.status, 201, response.payload)
        return response.payload

    @staticmethod
    def agent_headers(agent: dict) -> dict[str, str]:
        return {
            "Authorization": f"Agent {agent['agent_token']}",
            "X-Agent-ID": agent["agent_install_id"],
        }

    def heartbeat(self, agent: dict, event_id: str, hostname="pc-a", down=100):
        return self.api.handle(
            json_request(
                "POST",
                "/api/v1/agents/heartbeat",
                {
                    "event_id": event_id,
                    "timezone_name": "Asia/Kolkata",
                    "payload": heartbeat_payload(hostname, down, 10),
                },
                headers=self.agent_headers(agent),
            )
        )

    def test_registration_returns_token_once_and_stores_only_hash(self):
        agent = self.register()
        connection = sqlite3.connect(self.db)
        try:
            row = connection.execute(
                "SELECT organization_id,canonical_client_id,token_hash,platform,status FROM agent_credentials_v1"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(row[0], "org-a")
        self.assertEqual(row[1], agent["canonical_client_id"])
        self.assertNotEqual(row[2], agent["agent_token"])
        self.assertEqual(row[3], "windows")
        self.assertEqual(row[4], "active")

    def test_enrollment_is_single_use_and_registration_is_rate_limited(self):
        token = self.enrollment()
        first_id = str(uuid.uuid4())
        first = self.api.handle(
            json_request(
                "POST",
                "/api/v1/agents/register",
                {"agent_install_id": first_id, "platform": "windows"},
                headers={"Authorization": f"Enrollment {token}"},
                remote_addr="10.0.0.7",
            )
        )
        self.assertEqual(first.status, 201)
        exhausted = self.api.handle(
            json_request(
                "POST",
                "/api/v1/agents/register",
                {"agent_install_id": str(uuid.uuid4()), "platform": "windows"},
                headers={"Authorization": f"Enrollment {token}"},
                remote_addr="10.0.0.7",
            )
        )
        self.assertEqual(exhausted.status, 401)
        blocked = self.api.handle(
            json_request(
                "POST",
                "/api/v1/agents/register",
                {"agent_install_id": str(uuid.uuid4()), "platform": "windows"},
                headers={"Authorization": "Enrollment invalid-token"},
                remote_addr="10.0.0.7",
            )
        )
        self.assertEqual(blocked.status, 429)

    def test_wrong_or_disabled_agent_is_rejected(self):
        agent = self.register()
        wrong = dict(agent)
        wrong["agent_token"] = "wrong"
        self.assertEqual(self.heartbeat(wrong, "event-wrong-0001").status, 401)
        connection = sqlite3.connect(self.db)
        try:
            connection.execute(
                "UPDATE agent_credentials_v1 SET status='disabled' WHERE agent_install_id=?",
                (agent["agent_install_id"],),
            )
            connection.commit()
        finally:
            connection.close()
        self.assertEqual(self.heartbeat(agent, "event-disabled-1").status, 401)

    def test_heartbeat_is_idempotent_and_updates_history_once(self):
        agent = self.register()
        first = self.heartbeat(agent, "event-00000001", down=100)
        duplicate = self.heartbeat(agent, "event-00000001", down=999)
        self.assertEqual(first.status, 200, first.payload)
        self.assertTrue(first.payload["heartbeat"]["inserted"])
        self.assertFalse(duplicate.payload["heartbeat"]["inserted"])
        connection = sqlite3.connect(self.db)
        try:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM agent_heartbeat_events_v1").fetchone()[0],
                1,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM history_samples_v1").fetchone()[0],
                1,
            )
            rollup = connection.execute(
                "SELECT sample_count,download_bytes FROM history_daily_rollup_v1"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(rollup[0], 1)
        self.assertEqual(rollup[1], 100)

    def test_hostname_change_keeps_canonical_client(self):
        agent = self.register(hostname="old-name")
        first = self.heartbeat(agent, "event-00000011", hostname="old-name", down=100)
        second = self.heartbeat(agent, "event-00000012", hostname="new-name", down=150)
        self.assertEqual(first.payload["heartbeat"]["canonical_client_id"], agent["canonical_client_id"])
        self.assertEqual(second.payload["heartbeat"]["canonical_client_id"], agent["canonical_client_id"])
        connection = sqlite3.connect(self.db)
        try:
            current = connection.execute(
                "SELECT canonical_client_id,hostname FROM agent_current_v1"
            ).fetchone()
            rollup = connection.execute(
                "SELECT sample_count,download_bytes,hostname_last FROM history_daily_rollup_v1"
            ).fetchone()
        finally:
            connection.close()
        self.assertEqual(current, (agent["canonical_client_id"], "new-name"))
        self.assertEqual(rollup, (2, 150, "new-name"))

    def test_heartbeat_claims_message_and_acknowledgement_stops_redelivery(self):
        agent = self.register()
        connection = sqlite3.connect(self.db)
        try:
            queued = queue_message(
                connection,
                organization_id="org-a",
                canonical_client_ids=[agent["canonical_client_id"]],
                body="Display once",
                now=self.now,
            )
        finally:
            connection.close()
        heartbeat = self.heartbeat(agent, "event-message-01")
        self.assertEqual(len(heartbeat.payload["messages"]), 1)
        message = heartbeat.payload["messages"][0]
        ack = self.api.handle(
            json_request(
                "POST",
                f"/api/v1/agents/messages/{message['delivery_id']}/ack",
                {
                    "dispatch_token": message["dispatch_token"],
                    "client_receipt_id": "receipt-local-1",
                    "detail": {"displayed": True},
                },
                headers=self.agent_headers(agent),
            )
        )
        self.assertEqual(ack.status, 200, ack.payload)
        self.assertTrue(ack.payload["acknowledged"])
        next_heartbeat = self.heartbeat(agent, "event-message-02", down=120)
        self.assertEqual(next_heartbeat.payload["messages"], [])
        connection = sqlite3.connect(self.db)
        try:
            state = connection.execute(
                "SELECT state FROM client_message_deliveries_v1 WHERE message_id=?",
                (queued["message_id"],),
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(state, "ACKNOWLEDGED")

    def test_agent_cannot_acknowledge_other_organization_delivery(self):
        agent_a = self.register("org-a", remote="10.0.0.11")
        agent_b = self.register("org-b", hostname="pc-b", remote="10.0.0.12")
        connection = sqlite3.connect(self.db)
        try:
            queue_message(
                connection,
                organization_id="org-b",
                canonical_client_ids=[agent_b["canonical_client_id"]],
                body="Org B only",
                now=self.now,
            )
        finally:
            connection.close()
        claimed = self.heartbeat(agent_b, "event-org-b-001").payload["messages"][0]
        denied = self.api.handle(
            json_request(
                "POST",
                f"/api/v1/agents/messages/{claimed['delivery_id']}/ack",
                {
                    "dispatch_token": claimed["dispatch_token"],
                    "client_receipt_id": "wrong-org-receipt",
                },
                headers=self.agent_headers(agent_a),
            )
        )
        self.assertEqual(denied.status, 401)

    def test_token_rotation_invalidates_old_token(self):
        agent = self.register()
        rotated = self.api.handle(
            json_request(
                "POST",
                "/api/v1/agents/token/rotate",
                {"reason": "scheduled rotation"},
                headers=self.agent_headers(agent),
            )
        )
        self.assertEqual(rotated.status, 200, rotated.payload)
        self.assertNotEqual(rotated.payload["agent_token"], agent["agent_token"])
        self.assertEqual(self.heartbeat(agent, "event-old-token1").status, 401)
        new_agent = dict(agent)
        new_agent["agent_token"] = rotated.payload["agent_token"]
        self.assertEqual(self.heartbeat(new_agent, "event-new-token1").status, 200)

    def test_status_is_agent_scoped(self):
        agent = self.register()
        self.heartbeat(agent, "event-status-001", hostname="status-pc")
        response = self.api.handle(
            Request(
                method="GET",
                target="/api/v1/agents/status",
                headers=self.agent_headers(agent),
            )
        )
        self.assertEqual(response.status, 200)
        self.assertEqual(response.payload["agent"]["canonical_client_id"], agent["canonical_client_id"])
        self.assertEqual(response.payload["current"]["hostname"], "status-pc")

    def test_invalid_event_and_oversized_body_are_rejected(self):
        agent = self.register()
        invalid = self.heartbeat(agent, "short")
        self.assertEqual(invalid.status, 400)
        oversized = self.api.handle(
            Request(
                method="POST",
                target="/api/v1/agents/heartbeat",
                headers={**self.agent_headers(agent), "Content-Type": "application/json"},
                body=b"x" * 8193,
            )
        )
        self.assertEqual(oversized.status, 413)

    def test_migration_is_idempotent(self):
        connection = sqlite3.connect(self.db)
        try:
            from sagar_monitor.agents import apply_agent_migration

            apply_agent_migration(connection)
            apply_agent_migration(connection)
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        finally:
            connection.close()
        self.assertIn("agent_credentials_v1", tables)
        self.assertIn("agent_heartbeat_events_v1", tables)
        self.assertIn("agent_current_v1", tables)


if __name__ == "__main__":
    unittest.main()
