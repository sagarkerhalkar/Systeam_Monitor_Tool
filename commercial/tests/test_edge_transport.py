from __future__ import annotations

from io import BytesIO
from unittest.mock import patch
import json
import unittest
from urllib.error import HTTPError, URLError

from sagar_monitor.edge.transport import HTTPAgentTransport, TransportError, UnauthorizedError


class FakeResponse:
    def __init__(self, payload, status=200) -> None:
        self.raw = json.dumps(payload).encode("utf-8")
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self, limit=-1):
        return self.raw if limit < 0 else self.raw[:limit]


class EdgeTransportTests(unittest.TestCase):
    def test_https_is_required_except_explicit_loopback(self) -> None:
        with self.assertRaises(ValueError):
            HTTPAgentTransport("http://monitor.example.com")
        transport = HTTPAgentTransport("http://127.0.0.1:2278", allow_loopback_http=True)
        self.assertEqual(transport.settings.server_url, "http://127.0.0.1:2278")

    def test_registration_sends_enrollment_header_and_bounded_json(self) -> None:
        captured = {}

        def fake_urlopen(request, **kwargs):
            captured["request"] = request
            captured["kwargs"] = kwargs
            return FakeResponse(
                {
                    "ok": True,
                    "agent_install_id": "12345678-1234-1234-1234-123456789012",
                    "agent_token": "secret",
                },
                status=201,
            )

        transport = HTTPAgentTransport("https://monitor.example.com")
        with patch("sagar_monitor.edge.transport.urlopen", side_effect=fake_urlopen):
            result = transport.register(
                "enrollment-secret",
                {
                    "agent_install_id": "12345678-1234-1234-1234-123456789012",
                    "platform": "linux",
                },
            )
        request = captured["request"]
        self.assertEqual(request.full_url, "https://monitor.example.com/api/v1/agents/register")
        self.assertEqual(request.get_header("Authorization"), "Enrollment enrollment-secret")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertTrue(result["ok"])
        self.assertNotIn("enrollment-secret", request.data.decode("utf-8"))

    def test_heartbeat_sends_agent_identity_headers(self) -> None:
        captured = {}

        def fake_urlopen(request, **kwargs):
            captured["request"] = request
            return FakeResponse({"ok": True, "heartbeat": {}, "messages": []})

        transport = HTTPAgentTransport("https://monitor.example.com")
        with patch("sagar_monitor.edge.transport.urlopen", side_effect=fake_urlopen):
            transport.heartbeat(
                "12345678-1234-1234-1234-123456789012",
                "agent-secret",
                {"event_id": "hb:event-0001", "payload": {}},
            )
        request = captured["request"]
        self.assertEqual(request.get_header("Authorization"), "Agent agent-secret")
        self.assertEqual(request.get_header("X-agent-id"), "12345678-1234-1234-1234-123456789012")

    def test_unauthorized_and_network_errors_are_classified(self) -> None:
        transport = HTTPAgentTransport("https://monitor.example.com")
        error = HTTPError(
            "https://monitor.example.com/api/v1/agents/status",
            401,
            "Unauthorized",
            {},
            BytesIO(json.dumps({"error": {"message": "bad token"}}).encode("utf-8")),
        )
        with patch("sagar_monitor.edge.transport.urlopen", side_effect=error):
            with self.assertRaises(UnauthorizedError):
                transport.status("12345678-1234-1234-1234-123456789012", "bad")
        with patch("sagar_monitor.edge.transport.urlopen", side_effect=URLError("offline")):
            with self.assertRaises(TransportError) as raised:
                transport.status("12345678-1234-1234-1234-123456789012", "token")
        self.assertTrue(raised.exception.retryable)

    def test_invalid_server_json_is_not_retried_forever(self) -> None:
        class InvalidResponse(FakeResponse):
            def __init__(self):
                self.raw = b"not-json"
                self.status = 200

        transport = HTTPAgentTransport("https://monitor.example.com")
        with patch("sagar_monitor.edge.transport.urlopen", return_value=InvalidResponse()):
            with self.assertRaises(TransportError) as raised:
                transport.status("12345678-1234-1234-1234-123456789012", "token")
        self.assertFalse(raised.exception.retryable)


if __name__ == "__main__":
    unittest.main()
