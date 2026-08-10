from __future__ import annotations

from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from statistics import median
from typing import Any
from urllib.parse import parse_qs, urlparse
import json
import os
import sqlite3
import threading
import uuid

SERVICE = "sagar-monitor-dora-collector"
PORT = int(os.getenv("PORT", "8082"))
DB_PATH = Path(os.getenv("DORA_DB", "/data/dora.db")).expanduser()
LOCK = threading.RLock()


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_ts(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("timestamp is required")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    result = datetime.fromisoformat(text)
    if result.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return result.astimezone(timezone.utc)


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=NORMAL")
    connection.execute("PRAGMA busy_timeout=5000")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS deployments (
            id TEXT PRIMARY KEY,
            service TEXT NOT NULL,
            commit_sha TEXT NOT NULL,
            environment TEXT NOT NULL,
            change_started_at TEXT NOT NULL,
            deployed_at TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('success','failed')),
            rollout_strategy TEXT NOT NULL,
            source TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS idx_deployments_env_time
            ON deployments(environment, deployed_at);

        CREATE TABLE IF NOT EXISTS incidents (
            id TEXT PRIMARY KEY,
            deployment_id TEXT,
            service TEXT NOT NULL,
            environment TEXT NOT NULL,
            severity TEXT NOT NULL,
            reason TEXT NOT NULL,
            started_at TEXT NOT NULL,
            recovered_at TEXT,
            rollback_triggered INTEGER NOT NULL DEFAULT 0,
            source TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY(deployment_id) REFERENCES deployments(id)
        );
        CREATE INDEX IF NOT EXISTS idx_incidents_env_time
            ON incidents(environment, started_at);
        """
    )
    connection.commit()
    return connection


def json_metadata(value: Any) -> str:
    data = value if isinstance(value, dict) else {}
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def record_deployment(connection: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    deployment_id = str(payload.get("id") or uuid.uuid4())[:160]
    service = str(payload.get("service") or "").strip()[:160]
    commit_sha = str(payload.get("commit_sha") or "").strip()[:160]
    environment = str(payload.get("environment") or "production").strip()[:80]
    status = str(payload.get("status") or "success").strip().lower()
    strategy = str(payload.get("rollout_strategy") or "canary").strip()[:80]
    source = str(payload.get("source") or "github-actions").strip()[:120]
    if not service or not commit_sha:
        raise ValueError("service and commit_sha are required")
    if status not in {"success", "failed"}:
        raise ValueError("status must be success or failed")
    started = parse_ts(payload.get("change_started_at"))
    deployed = parse_ts(payload.get("deployed_at") or iso(utc_now()))
    if deployed < started:
        raise ValueError("deployed_at cannot be earlier than change_started_at")
    connection.execute(
        """
        INSERT INTO deployments(
            id,service,commit_sha,environment,change_started_at,deployed_at,status,
            rollout_strategy,source,metadata_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            service=excluded.service,
            commit_sha=excluded.commit_sha,
            environment=excluded.environment,
            change_started_at=excluded.change_started_at,
            deployed_at=excluded.deployed_at,
            status=excluded.status,
            rollout_strategy=excluded.rollout_strategy,
            source=excluded.source,
            metadata_json=excluded.metadata_json
        """,
        (
            deployment_id,
            service,
            commit_sha,
            environment,
            iso(started),
            iso(deployed),
            status,
            strategy,
            source,
            json_metadata(payload.get("metadata")),
        ),
    )
    connection.commit()
    return {
        "ok": True,
        "id": deployment_id,
        "status": status,
        "lead_time_seconds": round((deployed - started).total_seconds(), 3),
    }


def record_incident(connection: sqlite3.Connection, payload: dict[str, Any]) -> dict[str, Any]:
    incident_id = str(payload.get("id") or uuid.uuid4())[:160]
    deployment_id = str(payload.get("deployment_id") or "").strip()[:160] or None
    service = str(payload.get("service") or "").strip()[:160]
    environment = str(payload.get("environment") or "production").strip()[:80]
    severity = str(payload.get("severity") or "high").strip().lower()[:40]
    reason = str(payload.get("reason") or "unspecified incident").strip()[:1000]
    source = str(payload.get("source") or "alertmanager").strip()[:120]
    if not service:
        raise ValueError("service is required")
    started = parse_ts(payload.get("started_at") or iso(utc_now()))
    recovered = parse_ts(payload["recovered_at"]) if payload.get("recovered_at") else None
    if recovered is not None and recovered < started:
        raise ValueError("recovered_at cannot be earlier than started_at")
    connection.execute(
        """
        INSERT INTO incidents(
            id,deployment_id,service,environment,severity,reason,started_at,recovered_at,
            rollback_triggered,source,metadata_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
            deployment_id=excluded.deployment_id,
            service=excluded.service,
            environment=excluded.environment,
            severity=excluded.severity,
            reason=excluded.reason,
            started_at=excluded.started_at,
            recovered_at=excluded.recovered_at,
            rollback_triggered=excluded.rollback_triggered,
            source=excluded.source,
            metadata_json=excluded.metadata_json
        """,
        (
            incident_id,
            deployment_id,
            service,
            environment,
            severity,
            reason,
            iso(started),
            None if recovered is None else iso(recovered),
            1 if bool(payload.get("rollback_triggered")) else 0,
            source,
            json_metadata(payload.get("metadata")),
        ),
    )
    connection.commit()
    return {"ok": True, "id": incident_id}


def recover_incident(connection: sqlite3.Connection, incident_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    row = connection.execute("SELECT started_at FROM incidents WHERE id=?", (incident_id,)).fetchone()
    if row is None:
        raise KeyError("incident not found")
    started = parse_ts(row["started_at"])
    recovered = parse_ts(payload.get("recovered_at") or iso(utc_now()))
    if recovered < started:
        raise ValueError("recovered_at cannot be earlier than started_at")
    connection.execute("UPDATE incidents SET recovered_at=? WHERE id=?", (iso(recovered), incident_id))
    connection.commit()
    return {"ok": True, "id": incident_id, "mttr_seconds": round((recovered - started).total_seconds(), 3)}


def dora_metrics(connection: sqlite3.Connection, environment: str, days: int) -> dict[str, Any]:
    end = utc_now()
    start = end - timedelta(days=max(1, min(days, 365)))
    deployments = connection.execute(
        "SELECT * FROM deployments WHERE environment=? AND deployed_at>=? ORDER BY deployed_at ASC",
        (environment, iso(start)),
    ).fetchall()
    incidents = connection.execute(
        "SELECT * FROM incidents WHERE environment=? AND started_at>=? ORDER BY started_at ASC",
        (environment, iso(start)),
    ).fetchall()

    successful = [row for row in deployments if row["status"] == "success"]
    failed = [row for row in deployments if row["status"] == "failed"]
    lead_times = [
        (parse_ts(row["deployed_at"]) - parse_ts(row["change_started_at"])).total_seconds()
        for row in successful
    ]
    recovery_times = [
        (parse_ts(row["recovered_at"]) - parse_ts(row["started_at"])).total_seconds()
        for row in incidents
        if row["recovered_at"]
    ]
    deployment_ids_with_incidents = {row["deployment_id"] for row in incidents if row["deployment_id"]}
    change_failures = len({row["id"] for row in deployments if row["status"] == "failed" or row["id"] in deployment_ids_with_incidents})
    total_changes = len(deployments)
    period_days = max((end - start).total_seconds() / 86400.0, 1.0)

    return {
        "ok": True,
        "service": SERVICE,
        "environment": environment,
        "window_days": days,
        "deployment_frequency_per_day": round(len(successful) / period_days, 4),
        "successful_deployments": len(successful),
        "failed_deployments": len(failed),
        "median_lead_time_seconds": None if not lead_times else round(float(median(lead_times)), 3),
        "change_failure_rate_pct": 0.0 if total_changes == 0 else round((change_failures / total_changes) * 100.0, 2),
        "mean_time_to_recovery_seconds": None if not recovery_times else round(sum(recovery_times) / len(recovery_times), 3),
        "incidents": len(incidents),
        "recovered_incidents": len(recovery_times),
        "rollback_incidents": sum(1 for row in incidents if int(row["rollback_triggered"]) == 1),
        "generated_at": iso(end),
    }


def recent_history(connection: sqlite3.Connection, limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(limit, 200))
    deployments = [dict(row) for row in connection.execute("SELECT * FROM deployments ORDER BY deployed_at DESC LIMIT ?", (limit,)).fetchall()]
    incidents = [dict(row) for row in connection.execute("SELECT * FROM incidents ORDER BY started_at DESC LIMIT ?", (limit,)).fetchall()]
    for row in deployments + incidents:
        if "metadata_json" in row:
            try:
                row["metadata"] = json.loads(row.pop("metadata_json"))
            except json.JSONDecodeError:
                row["metadata"] = {}
    return {"ok": True, "deployments": deployments, "incidents": incidents}


class Handler(BaseHTTPRequestHandler):
    server_version = "SagarMonitorDORA"
    sys_version = ""

    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > 512 * 1024:
            raise ValueError("request body must be between 1 byte and 512 KiB")
        value = json.loads(self.rfile.read(length).decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("request body must be a JSON object")
        return value

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            with LOCK, connect() as connection:
                if parsed.path == "/healthz":
                    self.send_json(HTTPStatus.OK, {"ok": True, "service": SERVICE})
                    return
                if parsed.path == "/v1/metrics":
                    query = parse_qs(parsed.query)
                    environment = str(query.get("environment", ["production"])[0])[:80]
                    days = int(query.get("days", ["30"])[0])
                    self.send_json(HTTPStatus.OK, dora_metrics(connection, environment, days))
                    return
                if parsed.path == "/v1/history":
                    query = parse_qs(parsed.query)
                    limit = int(query.get("limit", ["50"])[0])
                    self.send_json(HTTPStatus.OK, recent_history(connection, limit))
                    return
            self.send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
        except Exception as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self.read_json()
            with LOCK, connect() as connection:
                if parsed.path == "/v1/deployments":
                    self.send_json(HTTPStatus.CREATED, record_deployment(connection, payload))
                    return
                if parsed.path == "/v1/incidents":
                    self.send_json(HTTPStatus.CREATED, record_incident(connection, payload))
                    return
                if parsed.path.startswith("/v1/incidents/") and parsed.path.endswith("/recover"):
                    incident_id = parsed.path.split("/")[3]
                    self.send_json(HTTPStatus.OK, recover_incident(connection, incident_id, payload))
                    return
            self.send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
        except KeyError as exc:
            self.send_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": str(exc)})
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
        except Exception:
            self.send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"ok": False, "error": "internal_error"})


def main() -> None:
    with connect():
        pass
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(json.dumps({"service": SERVICE, "port": PORT, "database": str(DB_PATH)}), flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
