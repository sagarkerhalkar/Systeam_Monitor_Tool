from __future__ import annotations

from datetime import datetime, timedelta, timezone
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sagar_monitor.database.maintenance import (
    RetentionPolicy,
    archive_and_prune,
    configure_database,
    create_retention_plan,
    database_health,
    passive_checkpoint,
    truncate_checkpoint,
)

NOW = datetime(2026, 8, 6, 12, 0, tzinfo=timezone.utc)


class DatabaseMaintenanceTests(unittest.TestCase):
    def test_configure_and_passive_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "monitor.db"
            connection = sqlite3.connect(db)
            try:
                settings = configure_database(
                    connection, wal_autocheckpoint_pages=64, busy_timeout_ms=2500
                )
                self.assertEqual(settings["journal_mode"], "wal")
                self.assertEqual(settings["wal_autocheckpoint_pages"], 64)
                self.assertEqual(settings["busy_timeout_ms"], 2500)
                connection.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT)")
                connection.executemany(
                    "INSERT INTO sample(value) VALUES(?)", [(str(i),) for i in range(100)]
                )
                connection.commit()
                checkpoint = passive_checkpoint(connection)
                self.assertIn("busy", checkpoint)
                self.assertGreaterEqual(checkpoint["checkpointed_pages"], 0)
            finally:
                connection.close()

    def test_health_reports_database_and_wal(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "monitor.db"
            connection = sqlite3.connect(db)
            try:
                configure_database(connection)
                connection.execute("CREATE TABLE sample(id INTEGER PRIMARY KEY, value TEXT)")
                connection.execute("INSERT INTO sample(value) VALUES('ok')")
                connection.commit()
                health = database_health(connection, db)
                self.assertTrue(health["ok"])
                self.assertEqual(health["quick_check"], "ok")
                self.assertGreater(health["database_bytes"], 0)
                self.assertGreaterEqual(health["wal_bytes"], 0)
            finally:
                connection.close()

    def test_truncate_requires_explicit_window(self):
        connection = sqlite3.connect(":memory:")
        try:
            with self.assertRaises(PermissionError):
                truncate_checkpoint(connection)
        finally:
            connection.close()

    def test_retention_plan_is_read_only(self):
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute(
                "CREATE TABLE notifications(id INTEGER PRIMARY KEY, created_at TEXT, message TEXT)"
            )
            for index in range(3):
                connection.execute(
                    "INSERT INTO notifications(created_at,message) VALUES(?,?)",
                    ((NOW - timedelta(days=40 + index)).isoformat(), f"old-{index}"),
                )
            connection.execute(
                "INSERT INTO notifications(created_at,message) VALUES(?,?)",
                ((NOW - timedelta(days=1)).isoformat(), "new"),
            )
            connection.commit()
            before = connection.total_changes
            plan = create_retention_plan(
                connection, [RetentionPolicy("notifications", 30)], now=NOW
            )
            self.assertEqual(plan[0]["planned_rows"], 3)
            self.assertEqual(connection.total_changes, before)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM notifications").fetchone()[0], 4)
        finally:
            connection.close()

    def test_execution_requires_backup_and_archive(self):
        connection = sqlite3.connect(":memory:")
        try:
            connection.execute(
                "CREATE TABLE notifications(id INTEGER PRIMARY KEY, created_at TEXT, message TEXT)"
            )
            connection.execute(
                "INSERT INTO notifications(created_at,message) VALUES(?,?)",
                ((NOW - timedelta(days=100)).isoformat(), "old"),
            )
            connection.commit()
            with self.assertRaises(PermissionError):
                archive_and_prune(
                    connection,
                    RetentionPolicy("notifications", 30),
                    now=NOW,
                    dry_run=False,
                )
        finally:
            connection.close()

    def test_archive_is_verified_before_prune_and_rerun_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            main_db = Path(directory) / "monitor.db"
            archive_db = Path(directory) / "archive.db"
            connection = sqlite3.connect(main_db)
            try:
                connection.execute(
                    "CREATE TABLE notifications(id INTEGER PRIMARY KEY, created_at TEXT, message TEXT)"
                )
                for index in range(10):
                    connection.execute(
                        "INSERT INTO notifications(created_at,message) VALUES(?,?)",
                        ((NOW - timedelta(days=40 + index)).isoformat(), f"old-{index}"),
                    )
                for index in range(5):
                    connection.execute(
                        "INSERT INTO notifications(created_at,message) VALUES(?,?)",
                        ((NOW - timedelta(days=index)).isoformat(), f"new-{index}"),
                    )
                connection.commit()
                result = archive_and_prune(
                    connection,
                    RetentionPolicy("notifications", 30),
                    archive_path=archive_db,
                    backup_verified=True,
                    now=NOW,
                    batch_size=3,
                    dry_run=False,
                )
                self.assertEqual(result["planned_rows"], 10)
                self.assertEqual(result["archived_rows"], 10)
                self.assertEqual(result["pruned_rows"], 10)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM notifications").fetchone()[0], 5)
                rerun = archive_and_prune(
                    connection,
                    RetentionPolicy("notifications", 30),
                    archive_path=archive_db,
                    backup_verified=True,
                    now=NOW,
                    dry_run=False,
                )
                self.assertEqual(rerun["planned_rows"], 0)
            finally:
                connection.close()
            archive = sqlite3.connect(archive_db)
            try:
                self.assertEqual(
                    archive.execute("SELECT COUNT(*) FROM archived_notifications_v1").fetchone()[0],
                    10,
                )
            finally:
                archive.close()

    def test_allowlist_rejects_arbitrary_table(self):
        connection = sqlite3.connect(":memory:")
        try:
            with self.assertRaises(ValueError):
                create_retention_plan(connection, [RetentionPolicy("users", 30)], now=NOW)
        finally:
            connection.close()


if __name__ == "__main__":
    unittest.main()
