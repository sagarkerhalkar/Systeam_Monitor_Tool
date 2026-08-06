from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import unittest

from sagar_monitor.qualification import (
    QualificationConfig,
    QualificationThresholds,
    run_forced_process_recovery,
    run_qualification_scenario,
    write_evidence,
)


class StagingQualificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def permissive_thresholds() -> QualificationThresholds:
        return QualificationThresholds(
            max_error_rate=0.0,
            max_registration_p95_ms=60_000,
            max_heartbeat_p95_ms=60_000,
            max_admin_p95_ms=60_000,
            max_wal_bytes=1024 * 1024 * 1024,
            max_peak_traced_memory_bytes=1024 * 1024 * 1024,
        )

    def test_real_api_scenario_is_idempotent_and_restorable(self) -> None:
        config = QualificationConfig(
            agent_count=8,
            concurrency=4,
            heartbeat_rounds=2,
            duplicate_replay_count=5,
            message_target_count=4,
            admin_request_count=8,
            thresholds=self.permissive_thresholds(),
        )
        report = run_qualification_scenario(self.root / "scenario" / "commercial.db", config)
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["totals"]["registered_agents"], 8)
        self.assertEqual(report["totals"]["duplicate_insertions"], 0)
        self.assertEqual(report["totals"]["claimed_messages"], 4)
        self.assertEqual(report["totals"]["failures"], 0)
        self.assertTrue(all(report["invariants"].values()), report["invariants"])
        self.assertEqual(
            report["database"]["source_counts"],
            report["database"]["restored_counts"],
        )
        self.assertEqual(report["database"]["checkpoint_after"]["busy"], 0)

    def test_forced_process_restart_preserves_authenticated_agent_state(self) -> None:
        report = run_forced_process_recovery(self.root / "process-recovery")
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["sqlite_quick_check"].lower(), "ok")
        self.assertEqual(report["counts"]["credentials"], 1)
        self.assertEqual(report["counts"]["heartbeats"], 1)
        self.assertEqual(report["counts"]["history_samples"], 1)
        self.assertEqual(report["counts"]["current_clients"], 1)

    def test_evidence_file_has_reproducible_integrity_hash(self) -> None:
        document = {
            "schema": "test",
            "passed": True,
            "metrics": {"p95": 12.5},
        }
        path = write_evidence(self.root / "evidence.json", document)
        stored = json.loads(path.read_text(encoding="utf-8"))
        digest = stored.pop("evidence_sha256")
        expected = hashlib.sha256(
            json.dumps(stored, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        self.assertEqual(digest, expected)

    def test_threshold_failure_blocks_qualification(self) -> None:
        config = QualificationConfig(
            agent_count=1,
            concurrency=1,
            heartbeat_rounds=1,
            duplicate_replay_count=1,
            message_target_count=0,
            admin_request_count=1,
            thresholds=QualificationThresholds(
                max_error_rate=0.0,
                max_registration_p95_ms=-1.0,
                max_heartbeat_p95_ms=60_000,
                max_admin_p95_ms=60_000,
                max_wal_bytes=1024 * 1024 * 1024,
                max_peak_traced_memory_bytes=1024 * 1024 * 1024,
            ),
        )
        report = run_qualification_scenario(self.root / "blocked" / "commercial.db", config)
        self.assertFalse(report["passed"])
        self.assertFalse(report["threshold_results"]["registration_p95"])
        self.assertTrue(all(report["invariants"].values()), report["invariants"])


if __name__ == "__main__":
    unittest.main()
