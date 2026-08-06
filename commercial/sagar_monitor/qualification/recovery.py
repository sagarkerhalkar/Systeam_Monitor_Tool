from __future__ import annotations

from pathlib import Path
from time import monotonic, sleep
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request as URLRequest, urlopen
import json
import os
import socket
import sqlite3
import subprocess
import sys
import uuid

from sagar_monitor.security import create_enrollment_token
from sagar_monitor.server.bootstrap import bootstrap_database


STRONG_PASSWORD = "Recovery!Admin2026"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _http_json(
    url: str,
    *,
    method: str = "GET",
    payload: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout: float = 5.0,
) -> tuple[int, dict[str, Any]]:
    body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    merged = {"Accept": "application/json"}
    if body is not None:
        merged["Content-Type"] = "application/json"
    merged.update(dict(headers or {}))
    request = URLRequest(url, data=body, headers=merged, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return int(response.status), json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            payload_value = json.loads(exc.read().decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            payload_value = {"ok": False, "error": {"message": str(exc)}}
        return int(exc.code), payload_value


def _wait_ready(base_url: str, process: subprocess.Popen[str], timeout: float = 20.0) -> None:
    deadline = monotonic() + timeout
    last_error = ""
    while monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"commercial server exited before readiness: {process.returncode}")
        try:
            status, payload = _http_json(base_url + "/api/v1/health/ready", timeout=1.0)
            if status == 200 and payload.get("ok"):
                return
            last_error = f"status={status} payload={payload}"
        except (OSError, URLError, TimeoutError) as exc:
            last_error = str(exc)
        sleep(0.1)
    raise RuntimeError(f"commercial server readiness timed out: {last_error}")


def _stop_process(process: subprocess.Popen[str]) -> int:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    return int(process.returncode or 0)


def run_forced_process_recovery(root: str | Path) -> dict[str, Any]:
    workspace = Path(root).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    database = workspace / "commercial.db"
    config_path = workspace / "server.json"
    log_path = workspace / "server.log"
    port = _free_port()
    organization_id = "qualification-recovery"

    for candidate in (database, Path(str(database) + "-wal"), Path(str(database) + "-shm")):
        candidate.unlink(missing_ok=True)

    bootstrap_database(
        database,
        organization_name="Qualification Recovery",
        organization_id=organization_id,
        admin_username="recovery.admin",
        admin_password=STRONG_PASSWORD,
    )
    connection = sqlite3.connect(database, timeout=10.0)
    try:
        enrollment = create_enrollment_token(
            connection,
            organization_id=organization_id,
            ttl_seconds=600,
            max_uses=1,
        )
    finally:
        connection.close()

    config_path.write_text(
        json.dumps(
            {
                "bind_host": "127.0.0.1",
                "port": port,
                "database_path": str(database),
                "certificate_file": str(workspace / "unused.crt"),
                "private_key_file": str(workspace / "unused.key"),
                "backup_directory": str(workspace / "backups"),
                "max_body_bytes": 2 * 1024 * 1024,
                "max_header_bytes": 32768,
                "socket_timeout_seconds": 10,
                "allow_loopback_http": True,
                "server_label": "Qualification Recovery",
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    commercial_root = Path(__file__).resolve().parents[2]
    environment = os.environ.copy()
    existing_pythonpath = environment.get("PYTHONPATH", "")
    environment["PYTHONPATH"] = str(commercial_root) + (os.pathsep + existing_pythonpath if existing_pythonpath else "")
    command = [
        sys.executable,
        "-m",
        "sagar_monitor.server.cli",
        "--config",
        str(config_path),
        "serve",
    ]
    base_url = f"http://127.0.0.1:{port}"

    def start(log_handle) -> subprocess.Popen[str]:
        process = subprocess.Popen(
            command,
            cwd=str(commercial_root.parent),
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            text=True,
        )
        _wait_ready(base_url, process)
        return process

    first_exit = 0
    second_exit = 0
    agent: dict[str, Any] = {}
    event_id = "recovery-heartbeat-000001"
    with log_path.open("w", encoding="utf-8") as log_handle:
        first = start(log_handle)
        try:
            agent_id = str(uuid.uuid4())
            status, agent = _http_json(
                base_url + "/api/v1/agents/register",
                method="POST",
                payload={
                    "agent_install_id": agent_id,
                    "platform": "windows",
                    "hostname": "recovery-client",
                },
                headers={"Authorization": f"Enrollment {enrollment}"},
            )
            if status != 201:
                raise RuntimeError(f"recovery registration failed: {status} {agent}")
            headers = {
                "Authorization": f"Agent {agent['agent_token']}",
                "X-Agent-ID": agent["agent_install_id"],
            }
            status, heartbeat = _http_json(
                base_url + "/api/v1/agents/heartbeat",
                method="POST",
                payload={
                    "event_id": event_id,
                    "timezone_name": "Asia/Kolkata",
                    "payload": {
                        "hostname": "recovery-client",
                        "identity": {"hostname": "recovery-client"},
                        "os": {"name": "Windows 11"},
                        "hardware": {
                            "cpu": {"usage_percent": 30},
                            "memory": {"used_percent": 50},
                        },
                        "network": {
                            "traffic": {
                                "today_download_bytes": 1000,
                                "today_upload_bytes": 200,
                                "current_download_mbps": 12.5,
                                "current_upload_mbps": 2.5,
                            }
                        },
                    },
                },
                headers=headers,
            )
            if status != 200 or not heartbeat.get("heartbeat", {}).get("inserted"):
                raise RuntimeError(f"recovery heartbeat failed: {status} {heartbeat}")
        finally:
            first_exit = _stop_process(first)

        second = start(log_handle)
        try:
            headers = {
                "Authorization": f"Agent {agent['agent_token']}",
                "X-Agent-ID": agent["agent_install_id"],
            }
            status, current = _http_json(
                base_url + "/api/v1/agents/status",
                headers=headers,
            )
            if status != 200:
                raise RuntimeError(f"authenticated status failed after restart: {status} {current}")
            if current.get("current", {}).get("hostname") != "recovery-client":
                raise RuntimeError("current client state did not survive forced process restart")
        finally:
            second_exit = _stop_process(second)

    connection = sqlite3.connect(database, timeout=10.0)
    try:
        counts = {
            "credentials": int(connection.execute("SELECT COUNT(*) FROM agent_credentials_v1").fetchone()[0]),
            "heartbeats": int(connection.execute("SELECT COUNT(*) FROM agent_heartbeat_events_v1").fetchone()[0]),
            "history_samples": int(connection.execute("SELECT COUNT(*) FROM history_samples_v1").fetchone()[0]),
            "current_clients": int(connection.execute("SELECT COUNT(*) FROM agent_current_v1").fetchone()[0]),
        }
        integrity = str(connection.execute("PRAGMA quick_check").fetchone()[0])
    finally:
        connection.close()

    passed = counts == {
        "credentials": 1,
        "heartbeats": 1,
        "history_samples": 1,
        "current_clients": 1,
    } and integrity.lower() == "ok"
    return {
        "schema": "sagar-monitor-forced-recovery-v1",
        "passed": passed,
        "first_process_exit": first_exit,
        "second_process_exit": second_exit,
        "counts": counts,
        "sqlite_quick_check": integrity,
        "event_id": event_id,
        "log_file": str(log_path),
    }
