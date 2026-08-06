from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
import json
import sqlite3
import uuid

from .resolver import IdentityRecord, resolve_identities

UNKNOWN_HOSTS = {"", "unknown", "unknown-host", "unknown host", "none", "null"}


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _clean(value: object) -> str:
    return str(value or "").strip()


def _nested(mapping: Mapping[str, Any], *paths: str) -> Any:
    for path in paths:
        current: Any = mapping
        ok = True
        for part in path.split("."):
            if isinstance(current, Mapping) and part in current:
                current = current[part]
            else:
                ok = False
                break
        if ok and current not in (None, ""):
            return current
    return ""


def _parse_timestamp(value: object) -> datetime | None:
    text = _clean(value)
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _os_family(payload: Mapping[str, Any], summary: Mapping[str, Any]) -> str:
    raw = _clean(
        _nested(payload, "os.name", "os", "platform")
        or summary.get("os")
        or summary.get("os_name")
    ).lower()
    if "windows" in raw:
        return "windows"
    if any(token in raw for token in ("linux", "ubuntu", "debian", "centos", "fedora", "rhel")):
        return "linux"
    return "unknown"


def record_from_latest_row(row: Mapping[str, Any]) -> tuple[IdentityRecord, dict[str, Any]]:
    payload = _json_object(row.get("payload_json"))
    summary = _json_object(row.get("summary_json"))
    identity = payload.get("identity") if isinstance(payload.get("identity"), Mapping) else {}
    hostname = _clean(
        row.get("hostname")
        or identity.get("hostname")
        or payload.get("hostname")
        or summary.get("hostname")
    )
    row_id = _clean(row.get("machine_id"))
    invalid = (
        not row_id
        or hostname.lower() in UNKNOWN_HOSTS
        or row_id.lower().startswith("unknown:")
    )
    record = IdentityRecord.from_mapping(
        {
            "row_id": row_id,
            "hostname": hostname,
            "agent_install_id": identity.get("agent_install_id")
            or payload.get("agent_install_id")
            or summary.get("agent_install_id"),
            "persistent_client_id": identity.get("persistent_client_id")
            or payload.get("persistent_client_id"),
            "system_uuid": identity.get("system_uuid") or payload.get("system_uuid"),
            "motherboard_serial": identity.get("motherboard_serial")
            or payload.get("motherboard_serial"),
            "bios_serial": identity.get("bios_serial") or payload.get("bios_serial"),
            "chassis_serial": identity.get("chassis_serial") or payload.get("chassis_serial"),
            "disk_serial": identity.get("disk_serial") or payload.get("disk_serial"),
            "updated_at": row.get("updated_at"),
            "os_family": _os_family(payload, summary),
            "invalid": invalid,
        }
    )
    metadata = {
        "row_id": row_id,
        "hostname": hostname,
        "updated_at": _clean(row.get("updated_at")),
        "os_family": record.os_family,
        "agent_install_id": record.agent_install_id,
    }
    return record, metadata


def _latest_rows(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(latest)").fetchall()
    }
    if "machine_id" not in columns:
        raise RuntimeError("latest table does not contain machine_id")
    wanted = ["machine_id", "hostname", "updated_at", "summary_json", "payload_json"]
    select = [name if name in columns else f"'' AS {name}" for name in wanted]
    cursor = connection.execute(f"SELECT {', '.join(select)} FROM latest")
    names = [item[0] for item in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def audit_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    now: datetime | None = None,
    offline_seconds: int = 600,
) -> dict[str, Any]:
    if offline_seconds <= 0:
        raise ValueError("offline_seconds must be positive")
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

    records: list[IdentityRecord] = []
    metadata: dict[str, dict[str, Any]] = {}
    for row in rows:
        record, detail = record_from_latest_row(row)
        records.append(record)
        if record.row_id:
            metadata[record.row_id] = detail

    resolution = resolve_identities(records)
    members: list[dict[str, Any]] = []
    os_counts: Counter[str] = Counter()
    online_clients = 0

    for canonical_id, row_ids in sorted(resolution.groups.items()):
        group_details = [metadata[row_id] for row_id in row_ids if row_id in metadata]
        newest = max(
            group_details,
            key=lambda item: _parse_timestamp(item.get("updated_at"))
            or datetime.min.replace(tzinfo=timezone.utc),
        )
        updated = _parse_timestamp(newest.get("updated_at"))
        age_seconds = float("inf") if updated is None else max(0.0, (now - updated).total_seconds())
        online = age_seconds < offline_seconds
        if online:
            online_clients += 1
        os_counts[newest.get("os_family") or "unknown"] += 1
        for row_id in row_ids:
            detail = metadata.get(row_id, {})
            members.append(
                {
                    "row_id": row_id,
                    "canonical_client_id": canonical_id,
                    "source": resolution.source_by_row.get(row_id, ""),
                    "hostname": detail.get("hostname", ""),
                    "os_family": detail.get("os_family", "unknown"),
                    "updated_at": detail.get("updated_at", ""),
                    "online": online,
                }
            )

    aliases = [
        {"canonical_client_id": canonical, "row_ids": row_ids, "size": len(row_ids)}
        for canonical, row_ids in sorted(resolution.groups.items())
        if len(row_ids) > 1
    ]
    physical = resolution.physical_client_count
    return {
        "generated_at": now.isoformat(),
        "offline_boundary_seconds": offline_seconds,
        "raw_rows": len(rows),
        "excluded_rows": len(resolution.excluded_rows),
        "excluded_row_ids": sorted(resolution.excluded_rows),
        "physical_clients": physical,
        "online_clients": online_clients,
        "offline_clients": physical - online_clients,
        "os_counts": {
            "windows": os_counts.get("windows", 0),
            "linux": os_counts.get("linux", 0),
            "unknown": os_counts.get("unknown", 0),
        },
        "alias_groups": aliases,
        "quarantined_tokens": [
            {"type": token_type, "value": value}
            for token_type, value in sorted(resolution.quarantined_tokens)
        ],
        "members": members,
    }


def audit_connection(
    connection: sqlite3.Connection,
    *,
    now: datetime | None = None,
    offline_seconds: int = 600,
) -> dict[str, Any]:
    return audit_rows(_latest_rows(connection), now=now, offline_seconds=offline_seconds)


def open_read_only_database(path: str | Path) -> sqlite3.Connection:
    resolved = Path(path).expanduser().resolve().as_posix()
    connection = sqlite3.connect(f"file:{resolved}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def audit_database(
    path: str | Path,
    *,
    now: datetime | None = None,
    offline_seconds: int = 600,
) -> dict[str, Any]:
    connection = open_read_only_database(path)
    try:
        return audit_connection(connection, now=now, offline_seconds=offline_seconds)
    finally:
        connection.close()


def apply_shadow_migration(connection: sqlite3.Connection) -> None:
    migration = Path(__file__).resolve().parents[2] / "migrations" / "0002_identity_shadow.sql"
    connection.executescript(migration.read_text(encoding="utf-8"))


def persist_shadow_report(
    connection: sqlite3.Connection,
    report: Mapping[str, Any],
    *,
    source_db_path: str = "",
) -> str:
    """Persist only shadow evidence; never update latest or heartbeats."""
    apply_shadow_migration(connection)
    run_id = str(uuid.uuid4())
    os_counts = report.get("os_counts") if isinstance(report.get("os_counts"), Mapping) else {}
    connection.execute(
        """INSERT INTO identity_shadow_runs(
            run_id, generated_at, source_db_path, raw_rows, excluded_rows,
            physical_clients, online_clients, offline_clients, windows_clients,
            linux_clients, report_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            run_id,
            _clean(report.get("generated_at")),
            source_db_path,
            int(report.get("raw_rows") or 0),
            int(report.get("excluded_rows") or 0),
            int(report.get("physical_clients") or 0),
            int(report.get("online_clients") or 0),
            int(report.get("offline_clients") or 0),
            int(os_counts.get("windows") or 0),
            int(os_counts.get("linux") or 0),
            json.dumps(dict(report), ensure_ascii=False, sort_keys=True),
        ),
    )
    for member in report.get("members") or []:
        if not isinstance(member, Mapping):
            continue
        connection.execute(
            """INSERT INTO identity_shadow_members(
                run_id, row_id, canonical_client_id, source, hostname,
                os_family, updated_at, online
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (
                run_id,
                _clean(member.get("row_id")),
                _clean(member.get("canonical_client_id")),
                _clean(member.get("source")),
                _clean(member.get("hostname")),
                _clean(member.get("os_family")),
                _clean(member.get("updated_at")),
                1 if member.get("online") else 0,
            ),
        )
    connection.commit()
    return run_id
