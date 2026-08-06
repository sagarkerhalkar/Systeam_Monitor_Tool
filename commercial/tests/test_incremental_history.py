from __future__ import annotations

from datetime import datetime, timezone
import sqlite3
import unittest

from sagar_monitor.history.incremental import (
    HistoryEvent,
    apply_history_migration,
    ingest_event,
    merge_canonical_clients,
    read_daily_rollup,
)


def event(
    event_id: str,
    at: str,
    down: int,
    up: int = 0,
    *,
    client: str = "client-a",
    hostname: str = "pc-a",
    timezone_name: str = "Asia/Kolkata",
    cpu: float | None = None,
    ram: float | None = None,
) -> HistoryEvent:
    return HistoryEvent(
        event_id=event_id,
        canonical_client_id=client,
        event_at=at,
        timezone_name=timezone_name,
        hostname=hostname,
        download_counter_bytes=down,
        upload_counter_bytes=up,
        cpu_percent=cpu,
        ram_percent=ram,
    )


class IncrementalHistoryTests(unittest.TestCase):
    def setUp(self):
        self.connection = sqlite3.connect(":memory:")
        apply_history_migration(self.connection)

    def tearDown(self):
        self.connection.close()

    def test_normal_counter_growth_updates_one_rollup(self):
        ingest_event(self.connection, event("a", "2026-08-04T00:00:00+00:00", 100, 10))
        result = ingest_event(self.connection, event("b", "2026-08-04T00:00:05+00:00", 150, 30))
        rollup = result["rollup"]
        self.assertEqual(rollup["sample_count"], 2)
        self.assertEqual(rollup["download_bytes"], 150)
        self.assertEqual(rollup["upload_bytes"], 30)
        self.assertEqual(rollup["online_seconds"], 5)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM history_daily_rollup_v1").fetchone()[0],
            1,
        )

    def test_counter_restart_adds_new_segment(self):
        ingest_event(self.connection, event("a", "2026-08-04T00:00:00+00:00", 100, 50))
        ingest_event(self.connection, event("b", "2026-08-04T00:00:05+00:00", 20, 5))
        result = ingest_event(self.connection, event("c", "2026-08-04T00:00:10+00:00", 40, 15))
        rollup = result["rollup"]
        self.assertEqual(rollup["download_bytes"], 140)
        self.assertEqual(rollup["upload_bytes"], 65)
        self.assertEqual(rollup["download_counter_resets"], 1)
        self.assertEqual(rollup["upload_counter_resets"], 1)

    def test_duplicate_event_is_idempotent(self):
        first = ingest_event(self.connection, event("same", "2026-08-04T00:00:00+00:00", 100))
        second = ingest_event(self.connection, event("same", "2026-08-04T00:00:00+00:00", 999))
        self.assertTrue(first["inserted"])
        self.assertFalse(second["inserted"])
        self.assertEqual(second["rollup"]["download_bytes"], 100)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM history_samples_v1").fetchone()[0],
            1,
        )

    def test_late_event_rebuilds_only_affected_client_day(self):
        ingest_event(self.connection, event("a", "2026-08-04T00:00:00+00:00", 100))
        ingest_event(self.connection, event("c", "2026-08-04T00:10:00+00:00", 200))
        result = ingest_event(self.connection, event("b", "2026-08-04T00:05:00+00:00", 150))
        self.assertEqual(result["rollup"]["download_bytes"], 200)
        self.assertEqual(result["rollup"]["sample_count"], 3)
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM history_daily_rollup_v1").fetchone()[0],
            1,
        )

    def test_hostname_change_keeps_one_canonical_rollup(self):
        ingest_event(
            self.connection,
            event("a", "2026-08-04T00:00:00+00:00", 100, hostname="old-name"),
        )
        result = ingest_event(
            self.connection,
            event("b", "2026-08-04T00:00:05+00:00", 150, hostname="new-name"),
        )
        self.assertEqual(result["rollup"]["hostname_last"], "new-name")
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM history_daily_rollup_v1").fetchone()[0],
            1,
        )

    def test_local_midnight_creates_separate_days(self):
        first = ingest_event(
            self.connection,
            event("a", "2026-08-03T18:29:59+00:00", 100, timezone_name="Asia/Kolkata"),
        )
        second = ingest_event(
            self.connection,
            event("b", "2026-08-03T18:30:00+00:00", 10, timezone_name="Asia/Kolkata"),
        )
        self.assertEqual(first["local_day"], "2026-08-03")
        self.assertEqual(second["local_day"], "2026-08-04")
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM history_daily_rollup_v1").fetchone()[0],
            2,
        )

    def test_alias_merge_retains_samples_and_rebuilds_affected_day(self):
        ingest_event(
            self.connection,
            event("source-a", "2026-08-04T00:00:00+00:00", 50, client="legacy-client"),
        )
        ingest_event(
            self.connection,
            event("target-b", "2026-08-04T00:00:05+00:00", 100, client="canonical-client"),
        )
        result = merge_canonical_clients(
            self.connection,
            source_canonical_client_id="legacy-client",
            target_canonical_client_id="canonical-client",
        )
        self.assertTrue(result["merged"])
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM history_samples_v1").fetchone()[0],
            2,
        )
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM history_samples_v1 WHERE canonical_client_id='legacy-client'"
            ).fetchone()[0],
            0,
        )
        rollup = read_daily_rollup(
            self.connection,
            "default",
            "canonical-client",
            "2026-08-04",
        )
        self.assertIsNotNone(rollup)
        self.assertEqual(rollup["download_bytes"], 100)
        self.assertEqual(
            self.connection.execute(
                "SELECT COUNT(*) FROM history_daily_rollup_v1 WHERE canonical_client_id='legacy-client'"
            ).fetchone()[0],
            0,
        )
        self.assertEqual(
            self.connection.execute("SELECT COUNT(*) FROM history_alias_merge_audit_v1").fetchone()[0],
            1,
        )

    def test_read_rollup_never_writes(self):
        ingest_event(self.connection, event("a", "2026-08-04T00:00:00+00:00", 100))
        before = self.connection.total_changes
        rollup = read_daily_rollup(self.connection, "default", "client-a", "2026-08-04")
        after = self.connection.total_changes
        self.assertIsNotNone(rollup)
        self.assertEqual(before, after)

    def test_metrics_are_aggregated_deterministically(self):
        ingest_event(
            self.connection,
            event("a", "2026-08-04T00:00:00+00:00", 10, cpu=20, ram=40),
        )
        result = ingest_event(
            self.connection,
            event("b", "2026-08-04T00:00:05+00:00", 20, cpu=60, ram=80),
        )
        self.assertEqual(result["rollup"]["avg_cpu_percent"], 40)
        self.assertEqual(result["rollup"]["peak_cpu_percent"], 60)
        self.assertEqual(result["rollup"]["avg_ram_percent"], 60)
        self.assertEqual(result["rollup"]["peak_ram_percent"], 80)

    def test_migration_is_idempotent(self):
        apply_history_migration(self.connection)
        apply_history_migration(self.connection)
        tables = {
            row[0]
            for row in self.connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("history_samples_v1", tables)
        self.assertIn("history_daily_rollup_v1", tables)

    def test_invalid_timezone_is_rejected(self):
        with self.assertRaises(ValueError):
            ingest_event(
                self.connection,
                event(
                    "a",
                    datetime(2026, 8, 4, tzinfo=timezone.utc).isoformat(),
                    10,
                    timezone_name="Invalid/Timezone",
                ),
            )


if __name__ == "__main__":
    unittest.main()
