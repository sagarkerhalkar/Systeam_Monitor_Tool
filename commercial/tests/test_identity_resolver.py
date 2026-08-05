from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path

from sagar_monitor.identity.resolver import IdentityRecord, new_agent_install_id, resolve_identities

ROOT = Path(__file__).resolve().parents[1]


def production_shape_fixture() -> list[IdentityRecord]:
    """Pseudonymized shape of the 2026-08-04 live diagnostic.

    106 raw rows:
    - 1 invalid UNKNOWN row
    - one 4-row legacy alias family
    - two 2-row legacy alias families
    - 97 independent rows

    Result: 100 physical clients.
    """
    rows: list[IdentityRecord] = [
        IdentityRecord("invalid", hostname="unknown-host", invalid=True),
    ]

    for index in range(4):
        rows.append(
            IdentityRecord(
                f"alias4-{index}",
                hostname="same-host-family-a",
                system_uuid="uuid-family-a",
                motherboard_serial="board-family-a",
            )
        )

    for family in ("b", "c"):
        for index in range(2):
            rows.append(
                IdentityRecord(
                    f"alias2-{family}-{index}",
                    hostname=f"same-host-family-{family}",
                    system_uuid=f"uuid-family-{family}",
                    bios_serial=f"bios-family-{family}",
                )
            )

    # Simulate a cloned/vendor UUID shared by many distinct computers.
    for index in range(57):
        rows.append(
            IdentityRecord(
                f"unique-cloned-{index}",
                hostname=f"unique-host-{index}",
                system_uuid="vendor-cloned-uuid",
                motherboard_serial=f"unique-board-{index:03d}",
            )
        )

    for index in range(40):
        rows.append(
            IdentityRecord(
                f"unique-{index}",
                hostname=f"another-unique-host-{index}",
                system_uuid=f"unique-uuid-{index:03d}",
                motherboard_serial=f"another-board-{index:03d}",
            )
        )

    assert len(rows) == 106
    return rows


class IdentityResolverTests(unittest.TestCase):
    def test_live_diagnostic_shape_is_100_physical_clients(self):
        rows = production_shape_fixture()
        result = resolve_identities(rows)
        self.assertEqual(len(rows), 106)
        self.assertEqual(len(result.excluded_rows), 1)
        self.assertEqual(result.physical_client_count, 100)
        merged_sizes = sorted(
            (len(value) for value in result.groups.values() if len(value) > 1),
            reverse=True,
        )
        self.assertEqual(merged_sizes, [4, 2, 2])
        self.assertIn(("system_uuid", "vendor-cloned-uuid"), result.quarantined_tokens)

    def test_shared_uuid_different_hostname_does_not_merge(self):
        records = [
            IdentityRecord("a", hostname="pc-a", system_uuid="shared-uuid-123"),
            IdentityRecord("b", hostname="pc-b", system_uuid="shared-uuid-123"),
        ]
        result = resolve_identities(records)
        self.assertEqual(result.physical_client_count, 2)
        self.assertIn(("system_uuid", "shared-uuid-123"), result.quarantined_tokens)

    def test_same_hostname_and_one_stable_token_merges_legacy_alias(self):
        records = [
            IdentityRecord("old", hostname="studio-1", bios_serial="bios-123456"),
            IdentityRecord("new", hostname="studio-1", bios_serial="bios-123456"),
        ]
        self.assertEqual(resolve_identities(records).physical_client_count, 1)

    def test_same_hostname_without_hardware_evidence_does_not_merge(self):
        records = [
            IdentityRecord("a", hostname="studio-1"),
            IdentityRecord("b", hostname="studio-1"),
        ]
        self.assertEqual(resolve_identities(records).physical_client_count, 2)

    def test_agent_install_id_survives_hostname_change(self):
        records = [
            IdentityRecord("old", hostname="old-name", agent_install_id="agent-123456"),
            IdentityRecord("new", hostname="new-name", agent_install_id="agent-123456"),
        ]
        result = resolve_identities(records)
        self.assertEqual(result.physical_client_count, 1)
        self.assertEqual(result.source_by_row["old"], "agent_install_id")

    def test_generated_agent_id_is_uuid(self):
        first = new_agent_install_id()
        second = new_agent_install_id()
        self.assertNotEqual(first, second)
        self.assertEqual(len(first), 36)

    def test_migration_is_idempotent(self):
        sql = (ROOT / "migrations" / "0001_agent_identity.sql").read_text(encoding="utf-8")
        con = sqlite3.connect(":memory:")
        con.executescript(sql)
        con.executescript(sql)
        tables = {
            row[0]
            for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        self.assertTrue(
            {
                "schema_migrations",
                "agent_installations",
                "client_identity_aliases",
                "identity_quarantine",
            }
            <= tables
        )


if __name__ == "__main__":
    unittest.main()
