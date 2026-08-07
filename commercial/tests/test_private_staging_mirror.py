from __future__ import annotations

from pathlib import Path
from subprocess import CompletedProcess
from tempfile import TemporaryDirectory
from unittest.mock import patch
import unittest

from sagar_monitor.staging.mirror import (
    _origin_repository,
    issue_runner_registration_token,
    private_mirror_plan,
    sync_private_mirror,
)


SOURCE = "sagarkerhalkar/Systeam_Monitor_Tool"
TARGET = "sagarkerhalkar/Systeam_Monitor_Tool_Staging_Private"
COMMIT = "6de78e8dfb0a355770fc71cf572054d7adb1d3db"


def completed(stdout: str = "") -> CompletedProcess[str]:
    return CompletedProcess(["tool"], 0, stdout=stdout, stderr="")


class PrivateStagingMirrorTests(unittest.TestCase):
    def test_plan_rejects_same_repository_and_records_release_boundaries(self) -> None:
        with self.assertRaises(ValueError):
            private_mirror_plan(
                source_repository=SOURCE,
                target_repository=SOURCE,
                expected_source_commit=COMMIT,
            )
        plan = private_mirror_plan(
            source_repository=SOURCE,
            target_repository=TARGET,
            expected_source_commit=COMMIT,
        )
        self.assertEqual(plan["required_target_visibility"], "PRIVATE")
        self.assertEqual(plan["target_branch"], "commercial-v1")
        self.assertEqual(plan["required_environment"], "commercial-staging-certification")
        self.assertFalse(plan["production_deployment_authorized"])
        self.assertFalse(plan["contains_secrets"])

    def test_origin_parser_accepts_supported_github_forms_only(self) -> None:
        self.assertEqual(_origin_repository("https://github.com/sagarkerhalkar/Systeam_Monitor_Tool.git"), SOURCE)
        self.assertEqual(_origin_repository("git@github.com:sagarkerhalkar/Systeam_Monitor_Tool.git"), SOURCE)
        self.assertEqual(_origin_repository("ssh://git@github.com/sagarkerhalkar/Systeam_Monitor_Tool.git"), SOURCE)
        with self.assertRaises(RuntimeError):
            _origin_repository("https://example.com/sagarkerhalkar/Systeam_Monitor_Tool.git")

    def test_dry_run_requires_clean_complete_checkout_exact_commit_and_private_target(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()

            def fake_run(command: list[str], **_: object) -> CompletedProcess[str]:
                if "status" in command:
                    return completed("")
                if command[-2:] == ["rev-parse", "--is-shallow-repository"]:
                    return completed("false\n")
                if command[-3:] == ["remote", "get-url", "origin"]:
                    return completed("https://github.com/sagarkerhalkar/Systeam_Monitor_Tool.git\n")
                if "fetch" in command:
                    return completed("")
                if command[-2:] == ["rev-parse", "FETCH_HEAD"]:
                    return completed(COMMIT + "\n")
                if command[1:4] == ["auth", "status", "--hostname"]:
                    return completed("")
                raise AssertionError(f"unexpected command: {command}")

            with patch("sagar_monitor.staging.mirror._which", side_effect=lambda value: value), patch(
                "sagar_monitor.staging.mirror._run", side_effect=fake_run
            ), patch("sagar_monitor.staging.mirror._target_visibility", return_value="PRIVATE"):
                result = sync_private_mirror(
                    root,
                    source_repository=SOURCE,
                    target_repository=TARGET,
                    expected_source_commit=COMMIT,
                    dry_run=True,
                )
            self.assertTrue(result["ok"])
            self.assertTrue(result["dry_run"])
            self.assertEqual(result["source_commit"], COMMIT)
            self.assertEqual(result["target_visibility"], "PRIVATE")

    def test_shallow_checkout_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()

            def fake_run(command: list[str], **_: object) -> CompletedProcess[str]:
                if "status" in command:
                    return completed("")
                if command[-2:] == ["rev-parse", "--is-shallow-repository"]:
                    return completed("true\n")
                return completed("")

            with patch("sagar_monitor.staging.mirror._which", side_effect=lambda value: value), patch(
                "sagar_monitor.staging.mirror._run", side_effect=fake_run
            ):
                with self.assertRaisesRegex(RuntimeError, "non-shallow clone"):
                    sync_private_mirror(
                        root,
                        source_repository=SOURCE,
                        target_repository=TARGET,
                        expected_source_commit=COMMIT,
                        dry_run=True,
                    )

    def test_dry_run_rejects_wrong_fetched_commit(self) -> None:
        wrong = "0" * 40
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()

            def fake_run(command: list[str], **_: object) -> CompletedProcess[str]:
                if "status" in command:
                    return completed("")
                if command[-2:] == ["rev-parse", "--is-shallow-repository"]:
                    return completed("false\n")
                if command[-3:] == ["remote", "get-url", "origin"]:
                    return completed("https://github.com/sagarkerhalkar/Systeam_Monitor_Tool.git\n")
                if "fetch" in command:
                    return completed("")
                if command[-2:] == ["rev-parse", "FETCH_HEAD"]:
                    return completed(wrong + "\n")
                return completed("")

            with patch("sagar_monitor.staging.mirror._which", side_effect=lambda value: value), patch(
                "sagar_monitor.staging.mirror._run", side_effect=fake_run
            ):
                with self.assertRaisesRegex(RuntimeError, "certified source commit mismatch"):
                    sync_private_mirror(
                        root,
                        source_repository=SOURCE,
                        target_repository=TARGET,
                        expected_source_commit=COMMIT,
                        dry_run=True,
                    )

    def test_token_is_blocked_for_public_target(self) -> None:
        with TemporaryDirectory() as directory, patch(
            "sagar_monitor.staging.mirror._which", return_value="gh"
        ), patch("sagar_monitor.staging.mirror._run", return_value=completed()), patch(
            "sagar_monitor.staging.mirror._target_visibility", return_value="PUBLIC"
        ):
            with self.assertRaisesRegex(RuntimeError, "not PRIVATE"):
                issue_runner_registration_token(TARGET, Path(directory) / "token.txt")

    def test_token_file_is_outside_repo_and_token_is_never_returned(self) -> None:
        secret = "registration-token-value"
        with TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            outside = Path(directory) / "secure" / "token.txt"

            def fake_run(command: list[str], **_: object) -> CompletedProcess[str]:
                if "registration-token" in " ".join(command):
                    return completed(secret + "\n")
                return completed("")

            with patch("sagar_monitor.staging.mirror._which", return_value="gh"), patch(
                "sagar_monitor.staging.mirror._run", side_effect=fake_run
            ), patch("sagar_monitor.staging.mirror._target_visibility", return_value="PRIVATE"):
                with self.assertRaisesRegex(RuntimeError, "outside the source repository"):
                    issue_runner_registration_token(
                        TARGET,
                        root / "token.txt",
                        forbidden_root=root,
                    )
                result = issue_runner_registration_token(
                    TARGET,
                    outside,
                    forbidden_root=root,
                )
            self.assertEqual(outside.read_text(encoding="utf-8"), secret)
            self.assertNotIn(secret, str(result))
            self.assertFalse(result["token_printed"])

    def test_native_launchers_require_private_mirror_commands(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        windows = (repository / "commercial/staging/windows/bootstrap-private-staging.ps1").read_text(encoding="utf-8")
        ubuntu = (repository / "commercial/staging/ubuntu/bootstrap-private-staging.sh").read_text(encoding="utf-8")
        windows_token = (repository / "commercial/staging/windows/issue-private-runner-token.ps1").read_text(encoding="utf-8")
        ubuntu_token = (repository / "commercial/staging/ubuntu/issue-private-runner-token.sh").read_text(encoding="utf-8")
        self.assertIn("private-mirror-sync", windows)
        self.assertIn("private-mirror-sync", ubuntu)
        self.assertIn("issue-runner-token", windows_token)
        self.assertIn("issue-runner-token", ubuntu_token)
        self.assertIn("icacls.exe", windows_token)
        self.assertIn("chmod 0600", ubuntu_token)
        self.assertIn("No production deployment was performed", windows)
        self.assertIn("No production deployment was performed", ubuntu)


if __name__ == "__main__":
    unittest.main()