from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Callable
import sqlite3

from sagar_monitor.api.agent_application import AgentAPI
from sagar_monitor.api.application import CommercialAPI, Request, Response

from .bootstrap import migration_status


class CombinedAPI:
    """Route commercial user/admin and authenticated agent traffic on one endpoint."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
        max_body_bytes: int = 2 * 1024 * 1024,
    ) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.admin_api = CommercialAPI(
            self.database_path,
            clock=clock,
            max_body_bytes=min(max_body_bytes, 10 * 1024 * 1024),
        )
        self.agent_api = AgentAPI(
            self.database_path,
            clock=clock,
            max_body_bytes=min(max_body_bytes, 10 * 1024 * 1024),
        )

    def _readiness(self, request: Request) -> Response:
        request_id = request.header("X-Request-ID") or "server-readiness"
        status = migration_status(self.database_path)
        connection = sqlite3.connect(f"file:{self.database_path.as_posix()}?mode=ro", uri=True, timeout=5.0)
        try:
            quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
            admins = int(
                connection.execute(
                    "SELECT COUNT(*) FROM users_v1 WHERE active=1 AND role='admin'"
                ).fetchone()[0]
            )
        finally:
            connection.close()
        ready = (
            quick_check.lower() == "ok"
            and admins > 0
            and not status.get("pending")
            and not status.get("mismatched")
        )
        return Response(
            status=200 if ready else 503,
            payload={
                "ok": ready,
                "service": "sagar-monitor-commercial-server",
                "database": {"quick_check": quick_check, "active_admins": admins},
                "migrations": status,
            },
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
                "X-Request-ID": request_id,
            },
        )

    def handle(self, request: Request) -> Response:
        if request.method.upper() == "GET" and request.path == "/api/v1/health/live":
            return Response(
                status=200,
                payload={"ok": True, "service": "sagar-monitor-commercial-server"},
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        if request.method.upper() == "GET" and request.path == "/api/v1/health/ready":
            return self._readiness(request)
        if request.path.startswith("/api/v1/agents/"):
            return self.agent_api.handle(request)
        return self.admin_api.handle(request)
