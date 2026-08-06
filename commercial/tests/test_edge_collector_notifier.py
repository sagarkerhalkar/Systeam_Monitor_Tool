from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import subprocess
import unittest

from sagar_monitor.edge.collectors import SystemCollector
from sagar_monitor.edge.inbox import LocalInbox, UserNotifier


class EdgeCollectorNotifierTests(unittest.TestCase):
    def test_collector_produces_history_compatible_shape(self) -> None:
        collector = SystemCollector(clock=lambda: 100.0)
        with (
            patch.object(collector, "_cpu", return_value={"usage_percent": 12.5, "logical_cores": 4}),
            patch.object(
                collector,
                "_memory",
                return_value={"total_bytes": 1000, "available_bytes": 400, "used_bytes": 600, "used_percent": 60.0},
            ),
            patch.object(collector, "_network", return_value=(5000, 2000, [{"name": "eth0"}])),
            patch.object(collector, "_volumes", return_value=[{"mount": "/", "total_bytes": 1000}]),
        ):
            first = collector.sample()
        collector.clock = lambda: 110.0
        with (
            patch.object(collector, "_cpu", return_value={"usage_percent": 20.0, "logical_cores": 4}),
            patch.object(
                collector,
                "_memory",
                return_value={"total_bytes": 1000, "available_bytes": 300, "used_bytes": 700, "used_percent": 70.0},
            ),
            patch.object(collector, "_network", return_value=(6_000_000, 3_000_000, [{"name": "eth0"}])),
            patch.object(collector, "_volumes", return_value=[]),
        ):
            second = collector.sample()
        self.assertIn("identity", first)
        self.assertEqual(first["network"]["traffic"]["current_download_mbps"], 0.0)
        self.assertGreater(second["network"]["traffic"]["current_download_mbps"], 0.0)
        self.assertEqual(second["hardware"]["memory"]["used_percent"], 70.0)
        self.assertEqual(second["network"]["traffic"]["raw_upload_total_bytes"], 3_000_000)

    def test_notifier_marks_only_successfully_displayed_messages(self) -> None:
        with TemporaryDirectory() as temporary:
            inbox = LocalInbox(Path(temporary) / "messages")
            delivery_id = "12345678-1234-1234-1234-123456789012"
            inbox.stage(
                {
                    "delivery_id": delivery_id,
                    "message_id": "message-a",
                    "dispatch_token": "lease-one",
                    "title": "Notice",
                    "body": "Hello",
                    "severity": "info",
                }
            )
            calls = []

            def successful(command, **kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, "", "")

            notifier = UserNotifier(inbox, command_runner=successful)
            self.assertEqual(notifier.display_once(), 1)
            self.assertEqual(len(calls), 1)
            self.assertEqual(len(inbox.displayed_messages()), 1)

    def test_notifier_failure_does_not_create_false_acknowledgement(self) -> None:
        with TemporaryDirectory() as temporary:
            inbox = LocalInbox(Path(temporary) / "messages")
            inbox.stage(
                {
                    "delivery_id": "12345678-1234-1234-1234-123456789012",
                    "message_id": "message-a",
                    "dispatch_token": "lease-one",
                    "title": "Notice",
                    "body": "Hello",
                    "severity": "critical",
                }
            )

            def failed(command, **kwargs):
                return subprocess.CompletedProcess(command, 1, "", "not available")

            notifier = UserNotifier(inbox, command_runner=failed)
            self.assertEqual(notifier.display_once(), 0)
            self.assertEqual(inbox.displayed_messages(), [])
            self.assertEqual(len(inbox.pending_messages()), 1)


if __name__ == "__main__":
    unittest.main()
