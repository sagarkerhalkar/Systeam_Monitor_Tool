from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch
from zipfile import ZipFile
import json
import unittest

from sagar_monitor.staging import (
    HOST_ROLES,
    build_release_candidate,
    create_host_marker,
    create_runner_receipt,
    load_and_verify_marker,
    require_private_repository,
    staging_plan_document,
    verify_release_candidate,
    verify_runner_receipt,
)


class StagingLabTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.preflight = {
            "ok": True,
            "plan_sha256": staging_plan_document()["plan_sha256"],
            "preflight_sha256": "a" * 64,
            "snapshot": {
                "platform": "windows",
                "hostname": "staging-win-01",
            },
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_plan_requires_seven_isolated_hosts_and_private_repository(self) -> None:
        plan = staging_plan_document()
        self.assertEqual(len(HOST_ROLES), 7)
        self.assertEqual(len(plan["hosts"]), 7)
        self.assertEqual(plan["required_repository_visibility"], "PRIVATE")
        self.assertTrue(plan["security"]["offline_first"])
        self.assertTrue(plan["security"]["runner_registration_is_ephemeral"])
        self.assertEqual(plan["production_port_must_be_unused"], 2278)

    def test_host_marker_and_runner_receipt_are_hashed_and_bound(self) -> None:
        marker = self.root / "host-marker.json"
        receipt = self.root / "runner-receipt.json"
        create_host_marker(
            marker,
            role_id="windows_server",
            site="Bhopal isolated lab",
            operator="Operator One",
            preflight=self.preflight,
        )
        marker_document = load_and_verify_marker(marker, expected_role="windows_server")
        self.assertEqual(marker_document["hostname"], "staging-win-01")

        create_runner_receipt(
            receipt,
            marker_path=marker,
            repository="owner/private-repo",
            platform_name="windows",
            runner_name="staging-win-01",
        )
        verified = verify_runner_receipt(
            receipt,
            marker_path=marker,
            repository="owner/private-repo",
            platform_name="windows",
        )
        self.assertTrue(verified["ok"], verified)

        document = json.loads(receipt.read_text(encoding="utf-8"))
        document["ephemeral"] = False
        receipt.write_text(json.dumps(document), encoding="utf-8")
        tampered = verify_runner_receipt(
            receipt,
            marker_path=marker,
            repository="owner/private-repo",
            platform_name="windows",
        )
        self.assertFalse(tampered["ok"])
        self.assertTrue(any("ephemeral" in error or "SHA-256" in error for error in tampered["errors"]))

    def test_marker_tampering_is_rejected(self) -> None:
        marker = self.root / "host-marker.json"
        create_host_marker(
            marker,
            role_id="windows_server",
            site="Bhopal isolated lab",
            operator="Operator One",
            preflight=self.preflight,
        )
        document = json.loads(marker.read_text(encoding="utf-8"))
        document["hostname"] = "production-server"
        marker.write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(RuntimeError):
            load_and_verify_marker(marker)

    @patch("sagar_monitor.staging.repository.shutil.which", return_value="/usr/bin/gh")
    @patch("sagar_monitor.staging.repository.subprocess.run")
    def test_repository_gate_rejects_public_and_accepts_private(self, run, _which) -> None:
        run.return_value = CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"visibility":"PUBLIC"}',
            stderr="",
        )
        with self.assertRaises(RuntimeError):
            require_private_repository("owner/repository")

        run.return_value = CompletedProcess(
            args=[],
            returncode=0,
            stdout='{"visibility":"PRIVATE"}',
            stderr="",
        )
        result = require_private_repository("owner/repository")
        self.assertTrue(result["ok"])

    def test_release_candidate_is_deterministic_nested_and_tamper_evident(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        first = self.root / "first.zip"
        second = self.root / "second.zip"
        one = build_release_candidate(
            repository,
            first,
            version="1.0.0-rc1",
            source_commit="0123456789abcdef",
        )
        two = build_release_candidate(
            repository,
            second,
            version="1.0.0-rc1",
            source_commit="0123456789abcdef",
        )
        self.assertEqual(one["sha256"], two["sha256"])
        verified = verify_release_candidate(first)
        self.assertTrue(verified["ok"])
        with ZipFile(first, "a") as archive:
            archive.writestr("undeclared.txt", "bad")
        with self.assertRaises(RuntimeError):
            verify_release_candidate(first)

    def test_runner_scripts_are_private_ephemeral_and_token_file_based(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        scripts = (
            repository / "commercial/staging/windows/install-ephemeral-runner.ps1",
            repository / "commercial/staging/ubuntu/install-ephemeral-runner.sh",
        )
        for script in scripts:
            text = script.read_text(encoding="utf-8")
            self.assertIn("repository-check", text)
            self.assertIn("--ephemeral", text)
            self.assertIn("RegistrationTokenFile" if script.suffix == ".ps1" else "REGISTRATION_TOKEN_FILE", text)
            self.assertNotIn("ghp_", text)
            self.assertNotIn("github_pat_", text)

    def test_physical_workflow_blocks_public_and_noncommercial_refs(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        workflow = (repository / ".github/workflows/commercial-physical-certification.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("github.event.repository.private", workflow)
        self.assertIn("refs/heads/commercial-v1", workflow)
        self.assertIn("needs: repository-safety", workflow)
        self.assertIn("commercial-staging-certification", workflow)


if __name__ == "__main__":
    unittest.main()
