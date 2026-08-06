from __future__ import annotations

import tempfile
import unittest
import uuid
from pathlib import Path

from sagar_monitor.identity.agent_id import load_or_create_agent_install_id, normalize_agent_install_id


class AgentInstallIdTests(unittest.TestCase):
    def test_valid_id_survives_restarts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent_install_id"
            first = load_or_create_agent_install_id(path)
            second = load_or_create_agent_install_id(path)
            self.assertEqual(first, second)
            self.assertEqual(str(uuid.UUID(first)), first)

    def test_invalid_id_is_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "agent_install_id"
            path.write_text("not-a-valid-id\n", encoding="utf-8")
            value = load_or_create_agent_install_id(path)
            self.assertEqual(normalize_agent_install_id(path.read_text()), value)
            self.assertNotEqual(value, "not-a-valid-id")

    def test_normalizer_returns_canonical_uuid(self):
        self.assertEqual(
            normalize_agent_install_id("A8098C1A-F86E-11DA-BD1A-00112444BE1E"),
            "a8098c1a-f86e-11da-bd1a-00112444be1e",
        )
        self.assertEqual(normalize_agent_install_id("bad"), "")


if __name__ == "__main__":
    unittest.main()
