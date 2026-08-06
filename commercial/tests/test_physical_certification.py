from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
import json
import sqlite3
import unittest

from sagar_monitor.certification import (
    CERTIFICATION_STEPS,
    disk_capacity_probe,
    finalize_evidence,
    initialize_evidence,
    machine_snapshot,
    record_machine_snapshot,
    record_step,
    run_https_soak,
    service_probe,
    sqlite_probe,
    verify_evidence,
)


class PhysicalCertificationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.evidence = self.root / "release-evidence.json"
        initialize_evidence(
            self.evidence,
            release_candidate="commercial-v1-rc1",
            site="Bhopal staging lab",
            operator="Operator One",
            metadata={"ticket": "RC-1"},
        )
        self.attachment = self.root / "installer.log"
        self.attachment.write_text("verified installation output\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _record_all_required(self) -> None:
        for step in CERTIFICATION_STEPS:
            attachments = [self.attachment] if step.attachment_required else []
            record_step(
                self.evidence,
                step_id=step.step_id,
                status="PASS",
                platform_name=step.platform,
                operator="Operator One",
                notes=f"Verified {step.title}",
                duration_seconds=step.minimum_duration_seconds,
                metrics={"verified": True},
                attachments=attachments,
            )

    def test_partial_ledger_is_valid_but_not_complete(self) -> None:
        record_machine_snapshot(
            self.evidence,
            platform_name="windows",
            operator="Operator One",
            snapshot=machine_snapshot(self.root),
        )
        result = verify_evidence(self.evidence)
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["complete"])
        self.assertEqual(result["event_count"], 1)
        self.assertGreater(len(result["missing_steps"]), 0)

    def test_platform_specific_step_rejects_generic_platform(self) -> None:
        with self.assertRaises(ValueError):
            record_step(
                self.evidence,
                step_id="windows_server_clean_install",
                status="PASS",
                platform_name="cross-platform",
                operator="Operator One",
                notes="Wrong platform label",
                attachments=[self.attachment],
            )

    def test_required_attachment_is_copied_and_tamper_is_detected(self) -> None:
        event = record_step(
            self.evidence,
            step_id="windows_server_clean_install",
            status="PASS",
            platform_name="windows",
            operator="Operator One",
            notes="Clean installation completed",
            attachments=[self.attachment],
        )
        copied = self.evidence.parent / event["attachments"][0]["relative_path"]
        self.assertTrue(copied.is_file())
        self.assertTrue(verify_evidence(self.evidence)["ok"])
        copied.write_text("tampered\n", encoding="utf-8")
        result = verify_evidence(self.evidence)
        self.assertFalse(result["ok"])
        self.assertTrue(any("attachment" in error for error in result["errors"]))

    def test_latest_result_controls_completion_and_two_person_approval(self) -> None:
        self._record_all_required()
        complete = verify_evidence(self.evidence, require_complete=True)
        self.assertTrue(complete["ok"], complete)
        self.assertTrue(complete["complete"])
        with self.assertRaises(ValueError):
            finalize_evidence(self.evidence, approver="operator one")
        final = finalize_evidence(self.evidence, approver="Approver Two", notes="Release accepted")
        self.assertTrue(final["ok"], final)
        self.assertTrue(final["finalized"])
        with self.assertRaises(RuntimeError):
            record_step(
                self.evidence,
                step_id="controlled_pilot",
                status="FAIL",
                platform_name="cross-platform",
                operator="Operator One",
                notes="Must not modify finalized evidence",
                attachments=[self.attachment],
            )

    def test_failed_latest_result_blocks_then_retest_clears(self) -> None:
        self._record_all_required()
        record_step(
            self.evidence,
            step_id="invalid_tls_rejection",
            status="FAIL",
            platform_name="cross-platform",
            operator="Operator One",
            notes="Untrusted certificate was accepted",
            attachments=[self.attachment],
        )
        blocked = verify_evidence(self.evidence, require_complete=True)
        self.assertFalse(blocked["ok"])
        self.assertIn("invalid_tls_rejection", blocked["failed_steps"])
        record_step(
            self.evidence,
            step_id="invalid_tls_rejection",
            status="PASS",
            platform_name="cross-platform",
            operator="Operator One",
            notes="Retest confirms untrusted certificate rejection",
            attachments=[self.attachment],
        )
        cleared = verify_evidence(self.evidence, require_complete=True)
        self.assertTrue(cleared["ok"], cleared)

    def test_document_and_event_tampering_are_detected(self) -> None:
        record_step(
            self.evidence,
            step_id="windows_server_clean_install",
            status="FAIL",
            platform_name="windows",
            operator="Operator One",
            notes="Intentional failed test",
        )
        document = json.loads(self.evidence.read_text(encoding="utf-8"))
        document["events"][0]["notes"] = "changed outside certification tool"
        self.evidence.write_text(json.dumps(document), encoding="utf-8")
        result = verify_evidence(self.evidence)
        self.assertFalse(result["ok"])
        self.assertTrue(any("hash" in error for error in result["errors"]))

    def test_sqlite_disk_and_machine_probes(self) -> None:
        database = self.root / "probe.db"
        connection = sqlite3.connect(database)
        try:
            connection.execute("CREATE TABLE test(value TEXT)")
            connection.execute("INSERT INTO test(value) VALUES('ok')")
            connection.commit()
        finally:
            connection.close()
        self.assertTrue(sqlite_probe(database)["ok"])
        self.assertTrue(disk_capacity_probe(self.root, minimum_free_bytes=0)["ok"])
        snapshot = machine_snapshot(self.root)
        self.assertTrue(snapshot["hostname"])
        self.assertGreater(snapshot["disk"]["total_bytes"], 0)

    def test_windows_service_probe_requires_successful_command(self) -> None:
        with patch(
            "sagar_monitor.certification.probes.subprocess.run",
            return_value=SimpleNamespace(returncode=1, stdout="Status: Running", stderr="query failed"),
        ):
            failed = service_probe(platform_name="windows", service_name="SagarMonitorCommercialServer")
        self.assertFalse(failed["ok"])
        with patch(
            "sagar_monitor.certification.probes.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout="Status: Running", stderr=""),
        ):
            passed = service_probe(platform_name="windows", service_name="SagarMonitorCommercialServer")
        self.assertTrue(passed["ok"])

    def test_short_soak_uses_real_loop_logic_with_mocked_https_probe(self) -> None:
        with patch(
            "sagar_monitor.certification.probes.https_health_probe",
            return_value={"ok": True, "endpoints": {}},
        ):
            result = run_https_soak(
                "https://staging.example.test",
                duration_seconds=0.12,
                interval_seconds=0.05,
            )
        self.assertTrue(result["ok"])
        self.assertGreaterEqual(result["checks"], 2)
        self.assertEqual(result["failures"], 0)


if __name__ == "__main__":
    unittest.main()
