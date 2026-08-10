from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import unittest


MODULE_PATH = Path(__file__).resolve().parents[1] / "services" / "ai_ops" / "app.py"
spec = spec_from_file_location("hackathon_ai_ops", MODULE_PATH)
assert spec and spec.loader
ai_ops = module_from_spec(spec)
spec.loader.exec_module(ai_ops)


class AIOpsTests(unittest.TestCase):
    def baseline(self):
        return [
            {
                "cpu_pct": 38 + (index % 4),
                "memory_pct": 58 + (index % 3),
                "disk_pct": 70,
                "latency_ms": 30 + index,
                "packet_loss_pct": 0.1,
            }
            for index in range(10)
        ]

    def test_normal_telemetry_is_healthy_or_watch(self):
        result = ai_ops.analyze(
            {
                "machine_id": "normal",
                "metrics": {
                    "cpu_pct": 42,
                    "memory_pct": 61,
                    "disk_pct": 71,
                    "latency_ms": 40,
                    "packet_loss_pct": 0.2,
                },
                "history": self.baseline(),
            }
        )
        self.assertTrue(result["ok"])
        self.assertIn(result["health"], {"healthy", "watch"})
        self.assertLess(result["anomaly_score"], 60)

    def test_extreme_network_and_resource_values_are_flagged(self):
        result = ai_ops.analyze(
            {
                "machine_id": "bad",
                "metrics": {
                    "cpu_pct": 98,
                    "memory_pct": 97,
                    "disk_pct": 96,
                    "latency_ms": 320,
                    "packet_loss_pct": 9,
                },
                "history": self.baseline(),
            }
        )
        self.assertIn(result["health"], {"degraded", "critical"})
        features = {item["feature"] for item in result["anomalies"]}
        self.assertIn("packet_loss_pct", features)
        self.assertIn("cpu_pct", features)
        self.assertGreaterEqual(result["anomaly_score"], 60)

    def test_missing_supported_metrics_is_rejected(self):
        with self.assertRaises(ValueError):
            ai_ops.analyze({"metrics": {"unknown": 1}, "history": []})


if __name__ == "__main__":
    unittest.main()
