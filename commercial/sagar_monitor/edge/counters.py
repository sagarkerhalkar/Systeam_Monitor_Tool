from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
import sqlite3


def _utc(value: datetime | str | None = None) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


class DailyCounterStore:
    """Persist OS cumulative network counters as local-day deltas."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS edge_daily_network_v1 (
                    local_day TEXT PRIMARY KEY,
                    last_download_total INTEGER NOT NULL,
                    last_upload_total INTEGER NOT NULL,
                    accumulated_download INTEGER NOT NULL,
                    accumulated_upload INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=10.0)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA busy_timeout=10000")
            yield connection
            if connection.in_transaction:
                connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def update(
        self,
        *,
        local_day: str,
        download_total: int,
        upload_total: int,
        now: datetime | str | None = None,
    ) -> tuple[int, int]:
        day = str(local_day or "").strip()
        if len(day) != 10:
            raise ValueError("local_day must be YYYY-MM-DD")
        down = max(0, int(download_total or 0))
        up = max(0, int(upload_total or 0))
        anchor = _utc(now).isoformat()
        with self.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM edge_daily_network_v1 WHERE local_day=?",
                (day,),
            ).fetchone()
            if row is None:
                accumulated_down = 0
                accumulated_up = 0
                connection.execute(
                    """INSERT INTO edge_daily_network_v1(
                        local_day,last_download_total,last_upload_total,
                        accumulated_download,accumulated_upload,updated_at
                    ) VALUES(?,?,?,?,?,?)""",
                    (day, down, up, 0, 0, anchor),
                )
            else:
                previous_down = int(row["last_download_total"])
                previous_up = int(row["last_upload_total"])
                accumulated_down = int(row["accumulated_download"])
                accumulated_up = int(row["accumulated_upload"])
                accumulated_down += down - previous_down if down >= previous_down else down
                accumulated_up += up - previous_up if up >= previous_up else up
                connection.execute(
                    """UPDATE edge_daily_network_v1
                       SET last_download_total=?,last_upload_total=?,
                           accumulated_download=?,accumulated_upload=?,updated_at=?
                       WHERE local_day=?""",
                    (down, up, accumulated_down, accumulated_up, anchor, day),
                )
            connection.execute(
                """DELETE FROM edge_daily_network_v1
                   WHERE local_day NOT IN (
                       SELECT local_day FROM edge_daily_network_v1 ORDER BY local_day DESC LIMIT 14
                   )"""
            )
            return accumulated_down, accumulated_up
