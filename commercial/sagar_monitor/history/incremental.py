from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import hashlib
import json
import math
import sqlite3
import uuid


MIGRATION_PATH = Path(__file__).resolve().parents[2] / "migrations" / "0003_incremental_history.sql"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | str) -> datetime:
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _iso(value: datetime | str) -> str:
    return _as_utc(value).isoformat()


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone: {name}") from exc


def _non_negative_int(value: object) -> int:
    try:
        number = int(float(value or 0))
    except (TypeError, ValueError, OverflowError):
        return 0
    return max(0, number)


def _finite_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _peak(values: list[float]) -> float | None:
    return round(max(values), 4) if values else None


@dataclass(frozen=True)
class HistoryEvent:
    event_id: str
    canonical_client_id: str
    event_at: datetime | str
    timezone_name: str = "Asia/Kolkata"
    organization_id: str = "default"
    hostname: str = ""
    download_counter_bytes: int = 0
    upload_counter_bytes: int = 0
    current_download_mbps: float | None = None
    current_upload_mbps: float | None = None
    cpu_percent: float | None = None
    ram_percent: float | None = None
    payload_hash: str = ""

    def normalized(self) -> "HistoryEvent":
        event_id = str(self.event_id or "").strip()
        canonical = str(self.canonical_client_id or "").strip()
        organization = str(self.organization_id or "default").strip() or "default"
        timezone_name = str(self.timezone_name or "Asia/Kolkata").strip() or "Asia/Kolkata"
        if not event_id:
            raise ValueError("event_id is required")
        if not canonical:
            raise ValueError("canonical_client_id is required")
        _zone(timezone_name)
        return HistoryEvent(
            event_id=event_id,
            canonical_client_id=canonical,
            event_at=_iso(self.event_at),
            timezone_name=timezone_name,
            organization_id=organization,
            hostname=str(self.hostname or "").strip(),
            download_counter_bytes=_non_negative_int(self.download_counter_bytes),
            upload_counter_bytes=_non_negative_int(self.upload_counter_bytes),
            current_download_mbps=_finite_float(self.current_download_mbps),
            current_upload_mbps=_finite_float(self.current_upload_mbps),
            cpu_percent=_finite_float(self.cpu_percent),
            ram_percent=_finite_float(self.ram_percent),
            payload_hash=str(self.payload_hash or "").strip(),
        )

    @property
    def local_day(self) -> str:
        normalized = self.normalized()
        return _as_utc(normalized.event_at).astimezone(_zone(normalized.timezone_name)).date().isoformat()

    @classmethod
    def from_payload(
        cls,
        *,
        event_id: str,
        canonical_client_id: str,
        received_at: datetime | str,
        payload: Mapping[str, Any],
        organization_id: str = "default",
        timezone_name: str = "Asia/Kolkata",
    ) -> "HistoryEvent":
        network = payload.get("network") if isinstance(payload.get("network"), Mapping) else {}
        traffic = network.get("traffic") if isinstance(network.get("traffic"), Mapping) else {}
        hardware = payload.get("hardware") if isinstance(payload.get("hardware"), Mapping) else {}
        cpu = hardware.get("cpu") if isinstance(hardware.get("cpu"), Mapping) else {}
        memory = hardware.get("memory") if isinstance(hardware.get("memory"), Mapping) else {}
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return cls(
            event_id=event_id,
            canonical_client_id=canonical_client_id,
            event_at=received_at,
            timezone_name=timezone_name,
            organization_id=organization_id,
            hostname=str(payload.get("hostname") or ""),
            download_counter_bytes=_non_negative_int(traffic.get("today_download_bytes"))
            or int(max(0.0, float(traffic.get("today_download_gb") or 0)) * 1024**3),
            upload_counter_bytes=_non_negative_int(traffic.get("today_upload_bytes"))
            or int(max(0.0, float(traffic.get("today_upload_gb") or 0)) * 1024**3),
            current_download_mbps=_finite_float(
                traffic.get("current_download_mbps") or network.get("current_download_mbps")
            ),
            current_upload_mbps=_finite_float(
                traffic.get("current_upload_mbps") or network.get("current_upload_mbps")
            ),
            cpu_percent=_finite_float(cpu.get("usage_percent")),
            ram_percent=_finite_float(memory.get("used_percent")),
            payload_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        )


def apply_history_migration(connection: sqlite3.Connection) -> None:
    connection.executescript(MIGRATION_PATH.read_text(encoding="utf-8"))


def _counter_total(rows: list[sqlite3.Row], field: str) -> tuple[int, int]:
    total = 0
    resets = 0
    previous: int | None = None
    for row in rows:
        current = _non_negative_int(row[field])
        if previous is None:
            total += current
        elif current >= previous:
            total += current - previous
        else:
            total += current
            resets += 1
        previous = current
    return total, resets


def _online_seconds(rows: list[sqlite3.Row], gap_limit_seconds: int) -> int:
    total = 0.0
    previous: datetime | None = None
    for row in rows:
        current = _as_utc(row["event_at"])
        if previous is not None:
            gap = max(0.0, (current - previous).total_seconds())
            total += min(gap, float(gap_limit_seconds))
        previous = current
    return int(round(total))


def rebuild_rollup_for_key(
    connection: sqlite3.Connection,
    organization_id: str,
    canonical_client_id: str,
    local_day: str,
    *,
    gap_limit_seconds: int = 600,
) -> dict[str, Any] | None:
    """Recalculate exactly one client/day row from its ordered samples."""
    if gap_limit_seconds <= 0:
        raise ValueError("gap_limit_seconds must be positive")
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """SELECT * FROM history_samples_v1
           WHERE organization_id=? AND canonical_client_id=? AND local_day=?
           ORDER BY event_at, event_id""",
        (organization_id, canonical_client_id, local_day),
    ).fetchall()
    if not rows:
        connection.execute(
            "DELETE FROM history_daily_rollup_v1 WHERE organization_id=? AND canonical_client_id=? AND local_day=?",
            (organization_id, canonical_client_id, local_day),
        )
        return None

    download_bytes, download_resets = _counter_total(rows, "download_counter_bytes")
    upload_bytes, upload_resets = _counter_total(rows, "upload_counter_bytes")
    down_speeds = [float(row["current_download_mbps"]) for row in rows if row["current_download_mbps"] is not None]
    up_speeds = [float(row["current_upload_mbps"]) for row in rows if row["current_upload_mbps"] is not None]
    cpu_values = [float(row["cpu_percent"]) for row in rows if row["cpu_percent"] is not None]
    ram_values = [float(row["ram_percent"]) for row in rows if row["ram_percent"] is not None]
    last_hostname = next((str(row["hostname"]) for row in reversed(rows) if row["hostname"]), "")
    values = {
        "organization_id": organization_id,
        "canonical_client_id": canonical_client_id,
        "local_day": local_day,
        "first_seen_at": rows[0]["event_at"],
        "last_seen_at": rows[-1]["event_at"],
        "hostname_last": last_hostname,
        "sample_count": len(rows),
        "download_bytes": download_bytes,
        "upload_bytes": upload_bytes,
        "download_counter_resets": download_resets,
        "upload_counter_resets": upload_resets,
        "online_seconds": _online_seconds(rows, gap_limit_seconds),
        "peak_download_mbps": _peak(down_speeds),
        "peak_upload_mbps": _peak(up_speeds),
        "avg_cpu_percent": _average(cpu_values),
        "peak_cpu_percent": _peak(cpu_values),
        "avg_ram_percent": _average(ram_values),
        "peak_ram_percent": _peak(ram_values),
        "updated_at": _utc_now().isoformat(),
    }
    connection.execute(
        """INSERT INTO history_daily_rollup_v1(
            organization_id, canonical_client_id, local_day, first_seen_at,
            last_seen_at, hostname_last, sample_count, download_bytes,
            upload_bytes, download_counter_resets, upload_counter_resets,
            online_seconds, peak_download_mbps, peak_upload_mbps,
            avg_cpu_percent, peak_cpu_percent, avg_ram_percent,
            peak_ram_percent, updated_at
        ) VALUES(
            :organization_id, :canonical_client_id, :local_day, :first_seen_at,
            :last_seen_at, :hostname_last, :sample_count, :download_bytes,
            :upload_bytes, :download_counter_resets, :upload_counter_resets,
            :online_seconds, :peak_download_mbps, :peak_upload_mbps,
            :avg_cpu_percent, :peak_cpu_percent, :avg_ram_percent,
            :peak_ram_percent, :updated_at
        )
        ON CONFLICT(organization_id, canonical_client_id, local_day) DO UPDATE SET
            first_seen_at=excluded.first_seen_at,
            last_seen_at=excluded.last_seen_at,
            hostname_last=excluded.hostname_last,
            sample_count=excluded.sample_count,
            download_bytes=excluded.download_bytes,
            upload_bytes=excluded.upload_bytes,
            download_counter_resets=excluded.download_counter_resets,
            upload_counter_resets=excluded.upload_counter_resets,
            online_seconds=excluded.online_seconds,
            peak_download_mbps=excluded.peak_download_mbps,
            peak_upload_mbps=excluded.peak_upload_mbps,
            avg_cpu_percent=excluded.avg_cpu_percent,
            peak_cpu_percent=excluded.peak_cpu_percent,
            avg_ram_percent=excluded.avg_ram_percent,
            peak_ram_percent=excluded.peak_ram_percent,
            updated_at=excluded.updated_at""",
        values,
    )
    return values


def ingest_event(
    connection: sqlite3.Connection,
    event: HistoryEvent,
    *,
    gap_limit_seconds: int = 600,
    commit: bool = True,
) -> dict[str, Any]:
    """Insert one idempotent sample and update only its client/day rollup."""
    apply_history_migration(connection)
    normalized = event.normalized()
    local_day = normalized.local_day
    before = connection.total_changes
    connection.execute(
        """INSERT OR IGNORE INTO history_samples_v1(
            event_id, organization_id, canonical_client_id, local_day,
            event_at, timezone_name, hostname, download_counter_bytes,
            upload_counter_bytes, current_download_mbps, current_upload_mbps,
            cpu_percent, ram_percent, payload_hash, inserted_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            normalized.event_id,
            normalized.organization_id,
            normalized.canonical_client_id,
            local_day,
            normalized.event_at,
            normalized.timezone_name,
            normalized.hostname,
            normalized.download_counter_bytes,
            normalized.upload_counter_bytes,
            normalized.current_download_mbps,
            normalized.current_upload_mbps,
            normalized.cpu_percent,
            normalized.ram_percent,
            normalized.payload_hash,
            _utc_now().isoformat(),
        ),
    )
    inserted = connection.total_changes > before
    if inserted:
        rollup = rebuild_rollup_for_key(
            connection,
            normalized.organization_id,
            normalized.canonical_client_id,
            local_day,
            gap_limit_seconds=gap_limit_seconds,
        )
    else:
        rollup = read_daily_rollup(
            connection,
            normalized.organization_id,
            normalized.canonical_client_id,
            local_day,
        )
    if commit:
        connection.commit()
    return {"inserted": inserted, "local_day": local_day, "rollup": rollup}


def read_daily_rollup(
    connection: sqlite3.Connection,
    organization_id: str,
    canonical_client_id: str,
    local_day: str,
) -> dict[str, Any] | None:
    """Read a rollup without creating, rebuilding or modifying data."""
    connection.row_factory = sqlite3.Row
    row = connection.execute(
        """SELECT * FROM history_daily_rollup_v1
           WHERE organization_id=? AND canonical_client_id=? AND local_day=?""",
        (organization_id, canonical_client_id, local_day),
    ).fetchone()
    return dict(row) if row else None


def merge_canonical_clients(
    connection: sqlite3.Connection,
    *,
    source_canonical_client_id: str,
    target_canonical_client_id: str,
    organization_id: str = "default",
    gap_limit_seconds: int = 600,
    commit: bool = True,
) -> dict[str, Any]:
    """Reassign samples and rebuild only affected days; raw samples remain retained."""
    source = str(source_canonical_client_id or "").strip()
    target = str(target_canonical_client_id or "").strip()
    if not source or not target:
        raise ValueError("source and target canonical client IDs are required")
    if source == target:
        return {"merged": False, "affected_days": []}
    apply_history_migration(connection)
    days = [
        row[0]
        for row in connection.execute(
            """SELECT DISTINCT local_day FROM history_samples_v1
               WHERE organization_id=? AND canonical_client_id IN (?,?)
               ORDER BY local_day""",
            (organization_id, source, target),
        ).fetchall()
    ]
    connection.execute(
        """UPDATE history_samples_v1 SET canonical_client_id=?
           WHERE organization_id=? AND canonical_client_id=?""",
        (target, organization_id, source),
    )
    connection.execute(
        """DELETE FROM history_daily_rollup_v1
           WHERE organization_id=? AND canonical_client_id=?""",
        (organization_id, source),
    )
    for day in days:
        rebuild_rollup_for_key(
            connection,
            organization_id,
            target,
            day,
            gap_limit_seconds=gap_limit_seconds,
        )
    merge_id = str(uuid.uuid4())
    connection.execute(
        """INSERT INTO history_alias_merge_audit_v1(
            merge_id, organization_id, source_canonical_client_id,
            target_canonical_client_id, affected_days_json, merged_at
        ) VALUES(?,?,?,?,?,?)""",
        (
            merge_id,
            organization_id,
            source,
            target,
            json.dumps(days),
            _utc_now().isoformat(),
        ),
    )
    if commit:
        connection.commit()
    return {"merged": True, "merge_id": merge_id, "affected_days": days}
