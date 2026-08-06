#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from sagar_monitor.identity.shadow import audit_database, persist_shadow_report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Read the current latest table and calculate conservative physical-client identity without changing production rows."
    )
    result.add_argument("--db", required=True, help="Path to monitor.db")
    result.add_argument("--offline-seconds", type=int, default=600)
    result.add_argument("--expect-physical", type=int)
    result.add_argument("--output", help="Optional JSON report path")
    result.add_argument(
        "--persist-shadow",
        action="store_true",
        help="Persist evidence only to identity_shadow_* tables; latest and heartbeats remain unchanged.",
    )
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    db_path = Path(args.db).expanduser().resolve()
    report = audit_database(db_path, offline_seconds=args.offline_seconds)

    if args.persist_shadow:
        connection = sqlite3.connect(db_path)
        try:
            run_id = persist_shadow_report(connection, report, source_db_path=str(db_path))
        finally:
            connection.close()
        report["persisted_shadow_run_id"] = run_id

    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)

    if args.expect_physical is not None and report["physical_clients"] != args.expect_physical:
        print(
            f"ERROR: expected {args.expect_physical} physical clients, got {report['physical_clients']}",
            file=sys.stderr,
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
