from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import unittest

from sagar_monitor.server.package import build_source_package, verify_source_package


class CommercialServerPackageBuilderTests(unittest.TestCase):
    def test_package_is_deterministic_manifested_and_allowlisted(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        with TemporaryDirectory() as directory:
            first = Path(directory) / "first.zip"
            second = Path(directory) / "second.zip"
            one = build_source_package(repository, first, version="1.0.0-test")
            two = build_source_package(repository, second, version="1.0.0-test")
            self.assertEqual(one["sha256"], two["sha256"])
            verified = verify_source_package(first)
            self.assertTrue(verified["ok"])
            with ZipFile(first, "r") as archive:
                names = archive.namelist()
            self.assertTrue(any(name.endswith("/MANIFEST.json") for name in names))
            self.assertTrue(any(name.endswith("/commercial/tools/run_physical_certification.py") for name in names))
            self.assertTrue(any(name.endswith("/commercial/tools/run_staging_lab.py") for name in names))
            self.assertTrue(any(name.endswith("/commercial/sagar_monitor/staging/mirror.py") for name in names))
            self.assertTrue(any(name.endswith("/commercial/server/windows/run-physical-certification.ps1") for name in names))
            self.assertTrue(any(name.endswith("/commercial/server/ubuntu/run-physical-certification.sh") for name in names))
            self.assertTrue(any(name.endswith("/commercial/staging/windows/install-ephemeral-runner.ps1") for name in names))
            self.assertTrue(any(name.endswith("/commercial/staging/ubuntu/install-ephemeral-runner.sh") for name in names))
            self.assertTrue(any(name.endswith("/commercial/staging/windows/bootstrap-private-staging.ps1") for name in names))
            self.assertTrue(any(name.endswith("/commercial/staging/windows/issue-private-runner-token.ps1") for name in names))
            self.assertTrue(any(name.endswith("/commercial/staging/ubuntu/bootstrap-private-staging.sh") for name in names))
            self.assertTrue(any(name.endswith("/commercial/staging/ubuntu/issue-private-runner-token.sh") for name in names))
            self.assertFalse(any(name.endswith("/server.py") and "/commercial/" not in name for name in names))
            self.assertFalse(any("workingcode" in name.lower() for name in names))

    def test_undeclared_archive_file_is_rejected(self) -> None:
        repository = Path(__file__).resolve().parents[2]
        with TemporaryDirectory() as directory:
            package = Path(directory) / "package.zip"
            build_source_package(repository, package, version="1.0.0-test")
            with ZipFile(package, "a") as archive:
                archive.writestr("sagar-monitor-commercial-server-1.0.0-test/undeclared.txt", "bad")
            with self.assertRaises(RuntimeError):
                verify_source_package(package)


if __name__ == "__main__":
    unittest.main()