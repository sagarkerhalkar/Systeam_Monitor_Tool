from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import argparse
import json
import logging
import os
import sqlite3
import sys

from .backup import backup_database, restore_database, verify_backup
from .bootstrap import bootstrap_database, migration_status, run_all_migrations
from .config import load_server_config
from .health import local_health, remote_health
from .runtime import serve


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2), flush=True)


def _read_secret(path: str | Path) -> str:
    secret_path = Path(path).expanduser().resolve()
    try:
        value = secret_path.read_text(encoding="utf-8-sig").strip("\r\n")
    except OSError as exc:
        raise RuntimeError(f"cannot read password file: {exc}") from exc
    if not value:
        raise RuntimeError("password file is empty")
    return value


def _remove_secret(path: str | Path) -> None:
    secret_path = Path(path).expanduser().resolve()
    if not secret_path.exists():
        return
    try:
        size = min(secret_path.stat().st_size, 1024 * 1024)
        with secret_path.open("r+b") as handle:
            handle.write(b"\x00" * size)
            handle.flush()
            os.fsync(handle.fileno())
        secret_path.unlink(missing_ok=True)
    except OSError:
        pass


def _backup_name() -> str:
    return "commercial-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + ".db"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Sagar Monitor commercial server operations")
    result.add_argument("--config", required=True, help="Path to commercial server JSON configuration")
    subcommands = result.add_subparsers(dest="command", required=True)

    bootstrap = subcommands.add_parser("bootstrap", help="Create first organization and administrator")
    bootstrap.add_argument("--organization-name", required=True)
    bootstrap.add_argument("--organization-id")
    bootstrap.add_argument("--admin-username", required=True)
    bootstrap.add_argument("--password-file", required=True)
    bootstrap.add_argument("--keep-password-file", action="store_true")

    subcommands.add_parser("migrate", help="Apply checksum-verified commercial migrations")
    subcommands.add_parser("migration-status", help="Show migration state without modifying the database")
    subcommands.add_parser("serve", help="Run the commercial HTTPS service")

    health = subcommands.add_parser("health", help="Check local state and optionally the running endpoint")
    health.add_argument("--remote", action="store_true")
    health.add_argument("--url", help="Explicit HTTPS health URL whose certificate name matches")
    health.add_argument("--ca-bundle")

    backup = subcommands.add_parser("backup", help="Create a verified online database backup")
    backup.add_argument("--output")

    verify = subcommands.add_parser("verify-backup", help="Verify backup manifest, hash and SQLite integrity")
    verify.add_argument("--backup", required=True)

    restore = subcommands.add_parser("restore", help="Restore a verified backup while service is stopped")
    restore.add_argument("--backup", required=True)
    restore.add_argument("--confirm-service-stopped", action="store_true")
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        config = load_server_config(arguments.config)
        if arguments.command == "bootstrap":
            password = _read_secret(arguments.password_file)
            try:
                result = bootstrap_database(
                    config.database_path,
                    organization_name=arguments.organization_name,
                    organization_id=arguments.organization_id or None,
                    admin_username=arguments.admin_username,
                    admin_password=password,
                )
            finally:
                password = ""
                if not arguments.keep_password_file:
                    _remove_secret(arguments.password_file)
            _print({"ok": True, **result})
            return 0
        if arguments.command == "migrate":
            connection = sqlite3.connect(config.database_path, timeout=10.0)
            try:
                result = run_all_migrations(connection)
            finally:
                connection.close()
            _print({"ok": True, **result})
            return 0
        if arguments.command == "migration-status":
            result = migration_status(config.database_path)
            _print({"ok": not result.get("pending") and not result.get("mismatched"), **result})
            return 0 if not result.get("pending") and not result.get("mismatched") else 2
        if arguments.command == "serve":
            logging.basicConfig(
                level=logging.INFO,
                format="%(asctime)s %(levelname)s %(name)s %(message)s",
            )
            serve(config)
            return 0
        if arguments.command == "health":
            result = local_health(config)
            if arguments.remote:
                target_url = arguments.url or config.local_url
                result["remote"] = remote_health(
                    target_url,
                    ca_bundle=arguments.ca_bundle,
                )
                result["ok"] = bool(result["ok"] and result["remote"].get("ok"))
            _print(result)
            return 0 if result["ok"] else 2
        if arguments.command == "backup":
            output = (
                Path(arguments.output).expanduser().resolve()
                if arguments.output
                else config.backup_directory / _backup_name()
            )
            _print({"ok": True, **backup_database(config.database_path, output)})
            return 0
        if arguments.command == "verify-backup":
            _print(verify_backup(arguments.backup))
            return 0
        if arguments.command == "restore":
            result = restore_database(
                arguments.backup,
                config.database_path,
                pre_restore_directory=config.backup_directory / "pre-restore",
                service_stopped=bool(arguments.confirm_service_stopped),
            )
            _print(result)
            return 0
        raise RuntimeError("unsupported command")
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(
            json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, sort_keys=True),
            file=sys.stderr,
            flush=True,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
