from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo
import hashlib
import json
import os
import re
import tempfile


_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_FIXED_TIME = (2026, 1, 1, 0, 0, 0)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _source_files(repository_root: Path) -> list[Path]:
    commercial = repository_root / "commercial"
    required_files = [
        commercial / "requirements.lock",
        commercial / "tools" / "run_commercial_server.py",
        commercial / "tools" / "run_physical_certification.py",
        commercial / "tools" / "run_staging_lab.py",
        commercial / "server" / "server-config.example.json",
    ]
    roots = [
        commercial / "sagar_monitor",
        commercial / "migrations",
        commercial / "server" / "windows",
        commercial / "server" / "ubuntu",
        commercial / "staging",
    ]
    files: list[Path] = []
    for item in required_files:
        if not item.is_file():
            raise FileNotFoundError(f"required package file is missing: {item}")
        files.append(item)
    for root in roots:
        if not root.is_dir():
            raise FileNotFoundError(f"required package directory is missing: {root}")
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            files.append(path)
    return sorted(set(files), key=lambda item: item.relative_to(repository_root).as_posix())


def _mode(path: Path) -> int:
    return 0o755 if path.suffix in {".sh", ".ps1"} else 0o644


def build_source_package(
    repository_root: str | Path,
    output_path: str | Path,
    *,
    version: str,
) -> dict[str, Any]:
    root = Path(repository_root).expanduser().resolve()
    output = Path(output_path).expanduser().resolve()
    clean_version = str(version or "").strip()
    if not _VERSION_RE.fullmatch(clean_version):
        raise ValueError("version must contain only letters, numbers, dot, underscore and hyphen")
    output.parent.mkdir(parents=True, exist_ok=True)
    prefix = f"sagar-monitor-commercial-server-{clean_version}"
    manifest_files: list[dict[str, Any]] = []
    source_entries: list[tuple[str, bytes, int]] = []
    for path in _source_files(root):
        relative = path.relative_to(root).as_posix()
        data = path.read_bytes()
        manifest_files.append({"path": relative, "size_bytes": len(data), "sha256": _sha256_bytes(data)})
        source_entries.append((f"{prefix}/{relative}", data, _mode(path)))
    manifest = {
        "format": "sagar-monitor-commercial-server-source-v1",
        "version": clean_version,
        "created_at": "2026-01-01T00:00:00+00:00",
        "files": manifest_files,
    }
    manifest_data = json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    source_entries.append((f"{prefix}/MANIFEST.json", manifest_data, 0o644))

    descriptor, temporary_name = tempfile.mkstemp(prefix=output.name + ".", suffix=".tmp", dir=output.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    try:
        with ZipFile(temporary, "w", compression=ZIP_DEFLATED, compresslevel=9) as archive:
            for name, data, mode in sorted(source_entries, key=lambda item: item[0]):
                info = ZipInfo(name, _FIXED_TIME)
                info.compress_type = ZIP_DEFLATED
                info.create_system = 3
                info.external_attr = (mode & 0xFFFF) << 16
                archive.writestr(info, data)
        os.replace(temporary, output)
        verification = verify_source_package(output)
        return {
            "ok": True,
            "package": str(output),
            "sha256": _sha256_file(output),
            "size_bytes": output.stat().st_size,
            "version": clean_version,
            "file_count": verification["file_count"],
        }
    finally:
        temporary.unlink(missing_ok=True)


def verify_source_package(package_path: str | Path) -> dict[str, Any]:
    package = Path(package_path).expanduser().resolve()
    if not package.is_file():
        raise FileNotFoundError(f"package does not exist: {package}")
    with ZipFile(package, "r") as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise RuntimeError("package contains duplicate entries")
        for name in names:
            pure = PurePosixPath(name)
            if pure.is_absolute() or ".." in pure.parts or "" in pure.parts:
                raise RuntimeError(f"unsafe package path: {name}")
        manifest_names = [name for name in names if name.endswith("/MANIFEST.json")]
        if len(manifest_names) != 1:
            raise RuntimeError("package must contain exactly one manifest")
        manifest_name = manifest_names[0]
        prefix = manifest_name[: -len("MANIFEST.json")]
        manifest = json.loads(archive.read(manifest_name).decode("utf-8"))
        if manifest.get("format") != "sagar-monitor-commercial-server-source-v1":
            raise RuntimeError("unsupported server package format")
        expected = manifest.get("files")
        if not isinstance(expected, list):
            raise RuntimeError("package manifest files list is invalid")
        for item in expected:
            if not isinstance(item, dict):
                raise RuntimeError("package manifest entry is invalid")
            relative = str(item.get("path") or "")
            entry_name = prefix + relative
            if entry_name not in names:
                raise RuntimeError(f"manifest file is missing from package: {relative}")
            data = archive.read(entry_name)
            if int(item.get("size_bytes") or -1) != len(data):
                raise RuntimeError(f"package size mismatch: {relative}")
            if str(item.get("sha256") or "") != _sha256_bytes(data):
                raise RuntimeError(f"package SHA-256 mismatch: {relative}")
        expected_names = {prefix + str(item["path"]) for item in expected}
        actual_names = set(names) - {manifest_name}
        if expected_names != actual_names:
            raise RuntimeError("package contains files not declared in the manifest")
        return {
            "ok": True,
            "package": str(package),
            "version": str(manifest.get("version") or ""),
            "file_count": len(expected),
            "sha256": _sha256_file(package),
        }
