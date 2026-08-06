from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import http.client
import json
import sqlite3
import unittest

from sagar_monitor.api.application import Request
from sagar_monitor.security import create_enrollment_token
from sagar_monitor.server.application import CombinedAPI
from sagar_monitor.server.backup import backup_database, restore_database, verify_backup
from sagar_monitor.server.bootstrap import bootstrap_database, migration_status, run_all_migrations
from sagar_monitor.server.config import ServerConfig, load_server_config
from sagar_monitor.server.health import local_health, remote_health
from sagar_monitor.server.runtime import CommercialHTTPServer


STRONG_PASSWORD = "Commercial!Admin2026"


class CommercialServerPackageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / "data" / "commercial.db"
        self.backups = self.root / "backups"

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def config(self, *, port: int = 8443) -> ServerConfig:
        return ServerConfig(
            bind_host="127.0.0.1",
            port=port,
            database_path=self.database,
            certificate_file=self.root / "tls" / "server.crt",
            private_key_file=self.root / "tls" / "server.key",
            backup_directory=self.backups,
            allow_loopback_http=True,
        )

    def bootstrap(self) -> dict[str, str]:
        return bootstrap_database(
            self.database,
            organization_name="Next Toppers",
            organization_id="org-test",
            admin_username="admin.user",
            admin_password=STRONG_PASSWORD,
        )

    def test_config_supports_bom_and_restricts_plain_http(self) -> None:
        config_path = self.root / "server.json"
        config_path.write_text(
            "\ufeff" + json.dumps(
                {
                    "bind_host": "127.0.0.1",
                    "port": 9443,
                    "database_path": "data/server.db",
                    "certificate_file": "tls/server.crt",
                    "private_key_file": "tls/server.key",
                    "backup_directory": "backups",
                    "allow_loopback_http": True,
                }
            ),
            encoding="utf-8",
        )
        config = load_server_config(config_path)
        self.assertEqual(config.port, 9443)
        self.assertEqual(config.database_path, (self.root / "data" / "server.db").resolve())
        with self.assertRaises(ValueError):
            ServerConfig(
                bind_host="0.0.0.0",
                port=8443,
                database_path=self.database,
                certificate_file=self.root / "missing.crt",
                private_key_file=self.root / "missing.key",
                backup_directory=self.backups,
                allow_loopback_http=True,
            ).validate(require_existing_tls=False)

    def test_bootstrap_is_one_time_and_migrations_are_immutable(self) -> None:
        result = self.bootstrap()
        self.assertEqual(result["organization_id"], "org-test")
        status = migration_status(self.database)
        self.assertEqual(status["pending"], [])
        self.assertEqual(status["mismatched"], [])
        connection = sqlite3.connect(self.database)
        try:
            stored = connection.execute(
                "SELECT username,password_hash,role FROM users_v1"
            ).fetchone()
            self.assertEqual(stored[0], "admin.user")
            self.assertTrue(str(stored[1]).startswith("scrypt$"))
            self.assertNotIn(STRONG_PASSWORD, str(stored[1]))
            self.assertEqual(stored[2], "admin")
            repeat = run_all_migrations(connection)
            self.assertEqual(repeat["applied"], 0)
        finally:
            connection.close()
        with self.assertRaises(RuntimeError):
            self.bootstrap()

    def test_backup_verify_restore_and_pre_restore_copy(self) -> None:
        self.bootstrap()
        backup = self.backups / "verified.db"
        result = backup_database(self.database, backup)
        self.assertEqual(result["quick_check"].lower(), "ok")
        verified = verify_backup(backup)
        self.assertTrue(verified["ok"])

        connection = sqlite3.connect(self.database)
        try:
            connection.execute("UPDATE organizations_v1 SET name='Changed' WHERE organization_id='org-test'")
            connection.commit()
        finally:
            connection.close()
        with self.assertRaises(RuntimeError):
            restore_database(backup, self.database)
        restored = restore_database(
            backup,
            self.database,
            pre_restore_directory=self.backups / "pre-restore",
            service_stopped=True,
        )
        self.assertIsNotNone(restored["pre_restore_backup"])
        connection = sqlite3.connect(self.database)
        try:
            name = connection.execute(
                "SELECT name FROM organizations_v1 WHERE organization_id='org-test'"
            ).fetchone()[0]
            self.assertEqual(name, "Next Toppers")
        finally:
            connection.close()

    def test_tampered_backup_is_rejected(self) -> None:
        self.bootstrap()
        backup = self.backups / "tampered.db"
        backup_database(self.database, backup)
        with backup.open("ab") as handle:
            handle.write(b"tamper")
        with self.assertRaises(RuntimeError):
            verify_backup(backup)

    def test_combined_router_readiness_and_agent_registration(self) -> None:
        bootstrap = self.bootstrap()
        connection = sqlite3.connect(self.database)
        try:
            enrollment = create_enrollment_token(
                connection,
                organization_id=bootstrap["organization_id"],
                ttl_seconds=600,
                max_uses=1,
            )
        finally:
            connection.close()
        api = CombinedAPI(self.database)
        ready = api.handle(Request(method="GET", target="/api/v1/health/ready"))
        self.assertEqual(ready.status, 200)
        registration = api.handle(
            Request(
                method="POST",
                target="/api/v1/agents/register",
                headers={
                    "Authorization": f"Enrollment {enrollment}",
                    "Content-Type": "application/json",
                },
                body=json.dumps(
                    {
                        "agent_install_id": "2f915a38-1170-4ff7-a4b0-c663bb3a7860",
                        "platform": "windows",
                        "hostname": "pilot-01",
                    }
                ).encode("utf-8"),
                remote_addr="127.0.0.1",
            )
        )
        self.assertEqual(registration.status, 201)
        self.assertTrue(registration.payload["agent_token"])

    def test_real_loopback_http_server_and_health(self) -> None:
        self.bootstrap()
        api = CombinedAPI(self.database)
        server = CommercialHTTPServer(self.config(port=0), api)
        port = int(server.server_address[1])
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("GET", "/api/v1/health/live")
            response = connection.getresponse()
            payload = json.loads(response.read().decode("utf-8"))
            self.assertEqual(response.status, 200)
            self.assertTrue(payload["ok"])
            self.assertEqual(response.getheader("X-Content-Type-Options"), "nosniff")
            connection.close()

            remote = remote_health(f"http://127.0.0.1:{port}")
            self.assertTrue(remote["ok"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_local_health_requires_bootstrap(self) -> None:
        config = self.config()
        before = local_health(config)
        self.assertFalse(before["ok"])
        self.bootstrap()
        after = local_health(config)
        self.assertTrue(after["ok"], after)


if __name__ == "__main__":
    unittest.main()
