from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from sagar_monitor.identity.shadow import (
    audit_connection,
    audit_database,
    persist_shadow_report,
)

NOW = datetime(2026, 8, 4, 12, 0, tzinfo=timezone.utc)


def iso(age_seconds: int) -> str:
    return (NOW - timedelta(seconds=age_seconds)).isoformat()


def payload(
    hostname: str,
    os_name: str,
    *,
    system_uuid: str = "",
    motherboard_serial: str = "",
    bios_serial: str = "",
    agent_install_id: str = "",
) -> str:
    return json.dumps(
        {
            "hostname": hostname,
            "os": {"name": os_name},
            "identity": {
                "hostname": hostname,
                "system_uuid": system_uuid,
                "motherboard_serial": motherboard_serial,
                "bios_serial": bios_serial,
                "agent_install_id": agent_install_id,
            },
        }
    )


def production_shape_rows() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = [
        {
            "machine_id": "UNKNOWN:UNKNOWN-HOST",
            "hostname": "unknown-host",
            "updated_at": iso(60),
            "summary_json": "{}",
            "payload_json": payload("unknown-host", "Unknown"),
        }
    ]

    for index in range(4):
        rows.append(
            {
                "machine_id": f"alias4-{index}",
                "hostname": "same-host-family-a",
                "updated_at": iso(300),
                "summary_json": "{}",
                "payload_json": payload(
                    "same-host-family-a",
                    "Windows 11",
                    system_uuid="uuid-family-a",
                    motherboard_serial="board-family-a",
                ),
            }
        )

    for family in ("b", "c"):
        for index in range(2):
            rows.append(
                {
                    "machine_id": f"alias2-{family}-{index}",
                    "hostname": f"same-host-family-{family}",
                    "updated_at": iso(300),
                    "summary_json": "{}",
                    "payload_json": payload(
                        f"same-host-family-{family}",
                        "Windows 11",
                        system_uuid=f"uuid-family-{family}",
                        bios_serial=f"bios-family-{family}",
                    ),
                }
            )

    for index in range(57):
        rows.append(
            {
                "machine_id": f"unique-cloned-{index}",
                "hostname": f"unique-host-{index}",
                "updated_at": iso(300),
                "summary_json": "{}",
                "payload_json": payload(
                    f"unique-host-{index}",
                    "Windows 11",
                    system_uuid="vendor-cloned-uuid",
                    motherboard_serial=f"unique-board-{index:03d}",
                ),
            }
        )

    for index in range(40):
        is_windows = index < 2
        is_online = index < 8
        rows.append(
            {
                "machine_id": f"unique-{index}",
                "hostname": f"another-unique-host-{index}",
                "updated_at": iso(300 if is_online else 600),
                "summary_json": "{}",
                "payload_json": payload(
                    f"another-unique-host-{index}",
                    "Windows 11" if is_windows else "Ubuntu 24.04",
                    system_uuid=f"unique-uuid-{index:03d}",
                    motherboard_serial=f"another-board-{index:03d}",
                ),
            }
        )

    assert len(rows) == 106
    return rows


def make_database(path: Path, rows: list[dict[str, str]]) -> None:
    connection = sqlite3.connect(path)
    try:
        connection.executescript(
            """
            CREATE TABLE latest(
                machine_id TEXT PRIMARY KEY,
                hostname TEXT,
                updated_at TEXT,
                summary_json TEXT,
                payload_json TEXT
            );
            CREATE TABLE heartbeats(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT,
                received_at TEXT,
                hostname TEXT,
                payload_json TEXT
            );
            """
        )
        for row in rows:
            connection.execute(
                "INSERT INTO latest(machine_id,hostname,updated_at,summary_json,payload_json) VALUES(?,?,?,?,?)",
                (
                    row["machine_id"],
                    row["hostname"],
                    row["updated_at"],
                    row["summary_json"],
                    row["payload_json"],
                ),
            )
            connection.execute(
                "INSERT INTO heartbeats(machine_id,received_at,hostname,payload_json) VALUES(?,?,?,?)",
                (row["machine_id"], row["updated_at"], row["hostname"], row["payload_json"]),
            )
        connection.commit()
    finally:
        connection.close()


class IdentityShadowTests(unittest.TestCase):
    def test_live_shape_produces_verified_counts(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute(
            "CREATE TABLE latest(machine_id TEXT PRIMARY KEY,hostname TEXT,updated_at TEXT,summary_json TEXT,payload_json TEXT)"
        )
        for row in production_shape_rows():
            connection.execute(
                "INSERT INTO latest VALUES(?,?,?,?,?)",
                tuple(row[key] for key in ("machine_id", "hostname", "updated_at", "summary_json", "payload_json")),
            )
        report = audit_connection(connection, now=NOW, offline_seconds=600)
        self.assertEqual(report["raw_rows"], 106)
        self.assertEqual(report["excluded_rows"], 1)
        self.assertEqual(report["physical_clients"], 100)
        self.assertEqual(report["online_clients"], 68)
        self.assertEqual(report["offline_clients"], 32)
        self.assertEqual(report["os_counts"], {"windows": 62, "linux": 38, "unknown": 0})
        self.assertEqual(sorted(group["size"] for group in report["alias_groups"]), [2, 2, 4])
        self.assertIn(
            {"type": "system_uuid", "value": "vendor-cloned-uuid"},
            report["quarantined_tokens"],
        )
        connection.close()

    def test_exact_ten_minute_boundary_is_offline(self):
        rows = [
            {
                "machine_id": "a",
                "hostname": "pc-a",
                "updated_at": iso(599),
                "summary_json": "{}",
                "payload_json": payload("pc-a", "Windows", system_uuid="uuid-a-123456"),
            },
            {
                "machine_id": "b",
                "hostname": "pc-b",
                "updated_at": iso(600),
                "summary_json": "{}",
                "payload_json": payload("pc-b", "Ubuntu", system_uuid="uuid-b-123456"),
            },
        ]
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute(
            "CREATE TABLE latest(machine_id TEXT PRIMARY KEY,hostname TEXT,updated_at TEXT,summary_json TEXT,payload_json TEXT)"
        )
        for row in rows:
            connection.execute("INSERT INTO latest VALUES(?,?,?,?,?)", tuple(row.values()))
        report = audit_connection(connection, now=NOW)
        self.assertEqual(report["online_clients"], 1)
        self.assertEqual(report["offline_clients"], 1)
        connection.close()

    def test_permanent_id_survives_hostname_change(self):
        agent_id = "9f49b8bc-e69d-4610-bab7-9fa3bd65f6b0"
        rows = [
            {
                "machine_id": "old",
                "hostname": "old-name",
                "updated_at": iso(700),
                "summary_json": "{}",
                "payload_json": payload("old-name", "Windows", agent_install_id=agent_id),
            },
            {
                "machine_id": "new",
                "hostname": "new-name",
                "updated_at": iso(10),
                "summary_json": "{}",
                "payload_json": payload("new-name", "Windows", agent_install_id=agent_id),
            },
        ]
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute(
            "CREATE TABLE latest(machine_id TEXT PRIMARY KEY,hostname TEXT,updated_at TEXT,summary_json TEXT,payload_json TEXT)"
        )
        for row in rows:
            connection.execute("INSERT INTO latest VALUES(?,?,?,?,?)", tuple(row.values()))
        report = audit_connection(connection, now=NOW)
        self.assertEqual(report["physical_clients"], 1)
        self.assertEqual(report["alias_groups"][0]["size"], 2)
        self.assertTrue(all(member["source"] == "agent_install_id" for member in report["members"]))
        connection.close()

    def test_read_only_audit_does_not_change_production_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "monitor.db"
            make_database(db, production_shape_rows())
            connection = sqlite3.connect(db)
            try:
                before_latest = connection.execute("SELECT COUNT(*) FROM latest").fetchone()[0]
                before_heartbeats = connection.execute("SELECT COUNT(*) FROM heartbeats").fetchone()[0]
            finally:
                connection.close()
            report = audit_database(db, now=NOW)
            self.assertEqual(report["physical_clients"], 100)
            connection = sqlite3.connect(db)
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM latest").fetchone()[0], before_latest)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM heartbeats").fetchone()[0], before_heartbeats)
            finally:
                connection.close()

    def test_persist_writes_only_shadow_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            db = Path(directory) / "monitor.db"
            make_database(db, production_shape_rows())
            report = audit_database(db, now=NOW)
            connection = sqlite3.connect(db)
            try:
                before_latest = connection.execute("SELECT COUNT(*) FROM latest").fetchone()[0]
                before_heartbeats = connection.execute("SELECT COUNT(*) FROM heartbeats").fetchone()[0]
                run_id = persist_shadow_report(connection, report, source_db_path=str(db))
                self.assertTrue(run_id)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM identity_shadow_runs").fetchone()[0], 1)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM identity_shadow_members").fetchone()[0], 105)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM latest").fetchone()[0], before_latest)
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM heartbeats").fetchone()[0], before_heartbeats)
            finally:
                connection.close()


if __name__ == "__main__":
    unittest.main()
