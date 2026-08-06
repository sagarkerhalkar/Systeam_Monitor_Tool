from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest

from sagar_monitor.edge.cli import _load_config, _read_enrollment_token, _remove_enrollment_token


class EdgeCLITests(unittest.TestCase):
    def test_windows_utf8_bom_is_accepted_for_config_and_token(self) -> None:
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            token_path = root / "enrollment.token"
            token_path.write_bytes(b"\xef\xbb\xbfenrollment-secret\r\n")
            config_path = root / "agent.json"
            config_path.write_bytes(
                b"\xef\xbb\xbf"
                + json.dumps(
                    {
                        "server_url": "https://monitor.example.com",
                        "state_directory": str(root / "state"),
                        "enrollment_token_file": str(token_path),
                    }
                ).encode("utf-8")
            )
            config = _load_config(config_path)
            self.assertEqual(config["server_url"], "https://monitor.example.com")
            self.assertEqual(_read_enrollment_token(config), "enrollment-secret")
            _remove_enrollment_token(config)
            self.assertFalse(token_path.exists())

    def test_invalid_config_is_rejected(self) -> None:
        with TemporaryDirectory() as temporary:
            path = Path(temporary) / "agent.json"
            path.write_text("[]", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                _load_config(path)


if __name__ == "__main__":
    unittest.main()
