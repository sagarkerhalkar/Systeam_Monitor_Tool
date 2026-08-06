from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from sagar_monitor.server.cli import main


class CommercialServerCLITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.config = self.root / "server.json"
        self.database = self.root / "data" / "commercial.db"
        self.backups = self.root / "backups"
        self.config.write_text(
            json.dumps(
                {
                    "bind_host": "127.0.0.1",
                    "port": 8443,
                    "database_path": str(self.database),
                    "certificate_file": str(self.root / "server.crt"),
                    "private_key_file": str(self.root / "server.key"),
                    "backup_directory": str(self.backups),
                    "allow_loopback_http": True,
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def invoke(self, *arguments: str) -> tuple[int, str, str]:
        output = StringIO()
        error = StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = main(["--config", str(self.config), *arguments])
        return code, output.getvalue(), error.getvalue()

    def test_bootstrap_reads_bom_password_file_and_removes_temporary_secret(self) -> None:
        password_file = self.root / "password.txt"
        password_file.write_text("\ufeffCommercial!Admin2026\r\n", encoding="utf-8")
        code, output, error = self.invoke(
            "bootstrap",
            "--organization-name",
            "Next Toppers",
            "--organization-id",
            "org-cli",
            "--admin-username",
            "admin.cli",
            "--password-file",
            str(password_file),
        )
        self.assertEqual(code, 0, error)
        self.assertFalse(password_file.exists())
        payload = json.loads(output)
        self.assertTrue(payload["ok"])
        self.assertNotIn("Commercial!Admin2026", output)

    def test_backup_and_restore_commands_require_explicit_stop_confirmation(self) -> None:
        password_file = self.root / "password.txt"
        password_file.write_text("Commercial!Admin2026", encoding="utf-8")
        self.assertEqual(
            self.invoke(
                "bootstrap",
                "--organization-name",
                "Next Toppers",
                "--admin-username",
                "admin.cli",
                "--password-file",
                str(password_file),
            )[0],
            0,
        )
        backup = self.backups / "cli.db"
        code, output, error = self.invoke("backup", "--output", str(backup))
        self.assertEqual(code, 0, error)
        self.assertTrue(backup.exists())
        self.assertTrue(Path(str(backup) + ".manifest.json").exists())
        code, _, error = self.invoke("restore", "--backup", str(backup))
        self.assertEqual(code, 1)
        self.assertIn("service is stopped", error)
        code, output, error = self.invoke(
            "restore",
            "--backup",
            str(backup),
            "--confirm-service-stopped",
        )
        self.assertEqual(code, 0, error)
        self.assertTrue(json.loads(output)["ok"])

    def test_installer_contracts_preserve_secrets_and_state(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        windows = (repository / "commercial/server/windows/install-commercial-server.ps1").read_text(encoding="utf-8")
        ubuntu = (repository / "commercial/server/ubuntu/install-commercial-server.sh").read_text(encoding="utf-8")
        unit = (repository / "commercial/server/ubuntu/sagar-monitor-commercial-server.service").read_text(encoding="utf-8")
        windows_uninstall = (repository / "commercial/server/windows/uninstall-commercial-server.ps1").read_text(encoding="utf-8")
        ubuntu_uninstall = (repository / "commercial/server/ubuntu/uninstall-commercial-server.sh").read_text(encoding="utf-8")

        self.assertIn("pre-upgrade-", windows)
        self.assertIn(".bootstrap-password", windows)
        self.assertIn("SYSTEM", windows)
        self.assertIn("pre-upgrade-", ubuntu)
        self.assertIn("runuser -u", ubuntu)
        self.assertIn("DATABASE_EXISTED_BEFORE", ubuntu)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("NoNewPrivileges=true", unit)
        self.assertIn("[switch]$RemoveData", windows_uninstall)
        self.assertIn("--remove-data", ubuntu_uninstall)


if __name__ == "__main__":
    unittest.main()
