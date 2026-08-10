from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "services" / "dora_collector" / "app.py"
spec = spec_from_file_location("hackathon_dora", MODULE_PATH)
assert spec and spec.loader
dora = module_from_spec(spec)
spec.loader.exec_module(dora)


class DoraCollectorTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        dora.DB_PATH = Path(self.temp.name) / "dora.db"
        self.connection = dora.connect()

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def iso(self, dt):
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

    def test_metrics_are_derived_from_real_events(self):
        now = datetime.now(timezone.utc)
        first = dora.record_deployment(
            self.connection,
            {
                "id": "dep-1",
                "service": "monitor",
                "commit_sha": "a" * 40,
                "environment": "production",
                "change_started_at": self.iso(now - timedelta(hours=2)),
                "deployed_at": self.iso(now - timedelta(hours=1)),
                "status": "success",
                "rollout_strategy": "canary",
            },
        )
        self.assertEqual(first["lead_time_seconds"], 3600.0)

        dora.record_deployment(
            self.connection,
            {
                "id": "dep-2",
                "service": "monitor",
                "commit_sha": "b" * 40,
                "environment": "production",
                "change_started_at": self.iso(now - timedelta(minutes=40)),
                "deployed_at": self.iso(now - timedelta(minutes=30)),
                "status": "failed",
                "rollout_strategy": "canary",
            },
        )
        dora.record_incident(
            self.connection,
            {
                "id": "incident-1",
                "deployment_id": "dep-2",
                "service": "monitor",
                "environment": "production",
                "severity": "high",
                "reason": "canary error rate exceeded threshold",
                "started_at": self.iso(now - timedelta(minutes=29)),
                "recovered_at": self.iso(now - timedelta(minutes=19)),
                "rollback_triggered": True,
            },
        )

        metrics = dora.dora_metrics(self.connection, "production", 30)
        self.assertEqual(metrics["successful_deployments"], 1)
        self.assertEqual(metrics["failed_deployments"], 1)
        self.assertEqual(metrics["change_failure_rate_pct"], 50.0)
        self.assertEqual(metrics["mean_time_to_recovery_seconds"], 600.0)
        self.assertEqual(metrics["rollback_incidents"], 1)
        self.assertEqual(metrics["median_lead_time_seconds"], 3600.0)

    def test_incident_recovery_updates_mttr(self):
        now = datetime.now(timezone.utc)
        dora.record_incident(
            self.connection,
            {
                "id": "incident-open",
                "service": "ai-ops",
                "environment": "production",
                "started_at": self.iso(now - timedelta(minutes=5)),
                "reason": "health check failed",
            },
        )
        result = dora.recover_incident(
            self.connection,
            "incident-open",
            {"recovered_at": self.iso(now)},
        )
        self.assertAlmostEqual(result["mttr_seconds"], 300.0, delta=1.0)


if __name__ == "__main__":
    unittest.main()
