from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any, Callable, Mapping
import hashlib
import json
import os
import platform
import sqlite3
import sys
import tracemalloc
import uuid

from sagar_monitor.api import Request
from sagar_monitor.messaging import queue_message
from sagar_monitor.security import create_enrollment_token
from sagar_monitor.server.application import CombinedAPI
from sagar_monitor.server.backup import backup_database, restore_database, verify_backup
from sagar_monitor.server.bootstrap import bootstrap_database


STRONG_PASSWORD = "Qualification!Admin2026"


@dataclass(frozen=True)
class QualificationThresholds:
    max_error_rate: float = 0.0
    max_registration_p95_ms: float = 5000.0
    max_heartbeat_p95_ms: float = 2000.0
    max_admin_p95_ms: float = 500.0
    max_wal_bytes: int = 512 * 1024 * 1024
    max_peak_traced_memory_bytes: int = 512 * 1024 * 1024


@dataclass(frozen=True)
class QualificationConfig:
    agent_count: int
    concurrency: int = 16
    heartbeat_rounds: int = 2
    duplicate_replay_count: int = 25
    message_target_count: int = 10
    admin_request_count: int = 100
    timezone_name: str = "Asia/Kolkata"
    thresholds: QualificationThresholds = QualificationThresholds()

    def validate(self) -> None:
        if not 1 <= self.agent_count <= 10000:
            raise ValueError("agent_count must be between 1 and 10000")
        if not 1 <= self.concurrency <= 128:
            raise ValueError("concurrency must be between 1 and 128")
        if not 1 <= self.heartbeat_rounds <= 1000:
            raise ValueError("heartbeat_rounds must be between 1 and 1000")
        if self.duplicate_replay_count < 0:
            raise ValueError("duplicate_replay_count cannot be negative")
        if self.message_target_count < 0:
            raise ValueError("message_target_count cannot be negative")
        if self.admin_request_count < 0:
            raise ValueError("admin_request_count cannot be negative")


class OperationRecorder:
    def __init__(self, name: str) -> None:
        self.name = name
        self._latencies: list[float] = []
        self._failures: list[dict[str, Any]] = []
        self._lock = Lock()
        self._started_at: float | None = None
        self._finished_at: float | None = None

    def _append(self, latency_ms: float, failure: dict[str, Any] | None) -> None:
        now = perf_counter()
        with self._lock:
            if self._started_at is None:
                self._started_at = now - max(0.0, latency_ms / 1000.0)
            self._finished_at = now
            self._latencies.append(float(latency_ms))
            if failure:
                self._failures.append(failure)

    def record(
        self,
        latency_ms: float,
        status: int,
        expected: set[int],
        payload: Mapping[str, Any] | None,
    ) -> None:
        failure = None
        if int(status) not in expected:
            error = payload.get("error") if isinstance(payload, Mapping) else None
            failure = {
                "status": int(status),
                "error": error if isinstance(error, Mapping) else {},
            }
        self._append(latency_ms, failure)

    def exception(self, latency_ms: float, exc: BaseException) -> None:
        self._append(
            latency_ms,
            {
                "status": 0,
                "error": {"type": type(exc).__name__, "message": str(exc)},
            },
        )

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        if not values:
            return 0.0
        ordered = sorted(values)
        rank = int((percentile / 100.0) * len(ordered) + 0.999999) - 1
        rank = max(0, min(len(ordered) - 1, rank))
        return round(ordered[rank], 3)

    def summary(self) -> dict[str, Any]:
        count = len(self._latencies)
        failures = len(self._failures)
        if self._started_at is None or self._finished_at is None:
            elapsed = 0.0
        else:
            elapsed = max(0.000001, self._finished_at - self._started_at)
        return {
            "name": self.name,
            "count": count,
            "failures": failures,
            "error_rate": round(failures / count, 6) if count else 0.0,
            "throughput_per_second": round(count / elapsed, 3) if count else 0.0,
            "elapsed_seconds": round(elapsed, 3),
            "latency_ms": {
                "min": round(min(self._latencies), 3) if count else 0.0,
                "p50": self._percentile(self._latencies, 50),
                "p95": self._percentile(self._latencies, 95),
                "p99": self._percentile(self._latencies, 99),
                "max": round(max(self._latencies), 3) if count else 0.0,
            },
            "failure_examples": self._failures[:10],
        }


def _request(
    method: str,
    target: str,
    payload: Mapping[str, Any] | None = None,
    *,
    headers: Mapping[str, str] | None = None,
    remote_addr: str = "127.0.0.1",
) -> Request:
    merged = {"Content-Type": "application/json"}
    merged.update(dict(headers or {}))
    body = b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return Request(method=method, target=target, headers=merged, body=body, remote_addr=remote_addr)


def _heartbeat_payload(index: int, round_number: int) -> dict[str, Any]:
    hostname = f"qualification-{index:05d}"
    return {
        "hostname": hostname,
        "identity": {"hostname": hostname},
        "os": {"name": "Windows 11" if index % 2 == 0 else "Ubuntu 24.04"},
        "hardware": {
            "cpu": {"usage_percent": 20 + index % 60},
            "memory": {"used_percent": 30 + index % 50},
        },
        "network": {
            "traffic": {
                "today_download_bytes": (round_number + 1) * 1_000_000 + index,
                "today_upload_bytes": (round_number + 1) * 200_000 + index,
                "current_download_mbps": 10.0 + (index % 100) / 10.0,
                "current_upload_mbps": 2.0 + (index % 40) / 10.0,
            }
        },
    }


def _remote_address(index: int) -> str:
    value = index + 1
    return f"10.{(value // 65025) % 250 + 1}.{(value // 255) % 255}.{value % 255}"


def _parallel(count: int, concurrency: int, worker: Callable[[int], Any]) -> list[Any]:
    if count <= 0:
        return []
    results: list[Any] = [None] * count
    with ThreadPoolExecutor(max_workers=min(concurrency, count)) as executor:
        futures = {executor.submit(worker, index): index for index in range(count)}
        for future in as_completed(futures):
            results[futures[future]] = future.result()
    return results


def _call(
    api: CombinedAPI,
    request: Request,
    recorder: OperationRecorder,
    expected: set[int],
):
    started = perf_counter()
    try:
        response = api.handle(request)
        recorder.record((perf_counter() - started) * 1000.0, response.status, expected, response.payload)
        return response
    except BaseException as exc:  # qualification must record every worker failure
        recorder.exception((perf_counter() - started) * 1000.0, exc)
        return None


def _database_counts(path: Path) -> dict[str, int]:
    tables = (
        "agent_credentials_v1",
        "agent_current_v1",
        "agent_heartbeat_events_v1",
        "history_samples_v1",
        "history_daily_rollup_v1",
        "client_messages_v1",
        "client_message_deliveries_v1",
        "client_message_receipts_v1",
    )
    connection = sqlite3.connect(path, timeout=10.0)
    try:
        return {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in tables
        }
    finally:
        connection.close()


def _checkpoint(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(path, timeout=10.0)
    try:
        mode = str(connection.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA wal_autocheckpoint=1000")
        busy, log_frames, checkpointed = connection.execute("PRAGMA wal_checkpoint(PASSIVE)").fetchone()
        return {
            "journal_mode": mode,
            "busy": int(busy),
            "log_frames": int(log_frames),
            "checkpointed_frames": int(checkpointed),
        }
    finally:
        connection.close()


def _fd_count() -> int | None:
    directory = Path("/proc/self/fd")
    if not directory.is_dir():
        return None
    try:
        return len(list(directory.iterdir()))
    except OSError:
        return None


def _hash(document: Mapping[str, Any]) -> str:
    raw = json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def write_evidence(path: str | Path, evidence: Mapping[str, Any]) -> Path:
    destination = Path(path).expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = dict(evidence)
    document.pop("evidence_sha256", None)
    document["evidence_sha256"] = _hash(document)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, destination)
    return destination


def run_qualification_scenario(
    database_path: str | Path,
    config: QualificationConfig,
) -> dict[str, Any]:
    config.validate()
    database = Path(database_path).expanduser().resolve()
    database.parent.mkdir(parents=True, exist_ok=True)
    for candidate in (database, Path(str(database) + "-wal"), Path(str(database) + "-shm")):
        candidate.unlink(missing_ok=True)

    organization_id = f"qualification-{config.agent_count}"
    bootstrap_database(
        database,
        organization_name=f"Qualification {config.agent_count}",
        organization_id=organization_id,
        admin_username="qualification.admin",
        admin_password=STRONG_PASSWORD,
    )
    checkpoint_before = _checkpoint(database)
    api = CombinedAPI(database, max_body_bytes=2 * 1024 * 1024)

    connection = sqlite3.connect(database, timeout=10.0)
    try:
        enrollment = create_enrollment_token(
            connection,
            organization_id=organization_id,
            ttl_seconds=3600,
            max_uses=config.agent_count,
        )
    finally:
        connection.close()

    recorders = {
        name: OperationRecorder(name)
        for name in (
            "registration",
            "heartbeat",
            "duplicate_replay",
            "admin",
            "message_claim",
            "message_ack",
            "restart",
        )
    }
    tracemalloc.start()
    fd_before = _fd_count()
    started_at = datetime.now(timezone.utc)
    namespace = uuid.UUID("fb362e8a-4529-4bb2-b22f-aebec712b178")

    def register(index: int):
        response = _call(
            api,
            _request(
                "POST",
                "/api/v1/agents/register",
                {
                    "agent_install_id": str(uuid.uuid5(namespace, f"{config.agent_count}:{index}")),
                    "platform": "windows" if index % 2 == 0 else "ubuntu",
                    "hostname": f"qualification-{index:05d}",
                    "metadata": {"scenario": config.agent_count, "index": index},
                },
                headers={"Authorization": f"Enrollment {enrollment}"},
                remote_addr=_remote_address(index),
            ),
            recorders["registration"],
            {201},
        )
        return dict(response.payload) if response is not None and response.status == 201 else None

    agents = _parallel(config.agent_count, config.concurrency, register)
    valid_agents = [agent for agent in agents if isinstance(agent, Mapping) and agent.get("agent_token")]

    def headers(agent: Mapping[str, Any]) -> dict[str, str]:
        return {
            "Authorization": f"Agent {agent['agent_token']}",
            "X-Agent-ID": str(agent["agent_install_id"]),
        }

    for round_number in range(config.heartbeat_rounds):
        def send_heartbeat(index: int, round_value: int = round_number):
            agent = agents[index]
            if not isinstance(agent, Mapping):
                return None
            return _call(
                api,
                _request(
                    "POST",
                    "/api/v1/agents/heartbeat",
                    {
                        "event_id": f"heartbeat-{round_value:04d}-{index:06d}",
                        "timezone_name": config.timezone_name,
                        "payload": _heartbeat_payload(index, round_value),
                    },
                    headers=headers(agent),
                    remote_addr=_remote_address(index),
                ),
                recorders["heartbeat"],
                {200},
            )

        _parallel(config.agent_count, config.concurrency, send_heartbeat)

    duplicate_count = min(config.agent_count, config.duplicate_replay_count)
    final_round = config.heartbeat_rounds - 1

    def replay(index: int):
        agent = agents[index]
        if not isinstance(agent, Mapping):
            return None
        return _call(
            api,
            _request(
                "POST",
                "/api/v1/agents/heartbeat",
                {
                    "event_id": f"heartbeat-{final_round:04d}-{index:06d}",
                    "timezone_name": config.timezone_name,
                    "payload": _heartbeat_payload(index, final_round + 1000),
                },
                headers=headers(agent),
            ),
            recorders["duplicate_replay"],
            {200},
        )

    duplicate_responses = _parallel(duplicate_count, config.concurrency, replay)
    duplicate_insertions = sum(
        1
        for response in duplicate_responses
        if response is not None and response.payload.get("heartbeat", {}).get("inserted")
    )

    login = _call(
        api,
        _request(
            "POST",
            "/api/v1/auth/login",
            {
                "organization_id": organization_id,
                "username": "qualification.admin",
                "password": STRONG_PASSWORD,
            },
            headers={"X-Client-Fingerprint": "qualification-browser"},
            remote_addr="127.0.0.10",
        ),
        recorders["admin"],
        {200},
    )
    login_payload = dict(login.payload) if login is not None and login.status == 200 else {}
    admin_headers = {
        "Authorization": f"Bearer {login_payload.get('session_token', '')}",
        "X-Client-Fingerprint": "qualification-browser",
    }

    def admin_read(index: int):
        return _call(
            api,
            Request(
                method="GET",
                target="/api/v1/auth/me",
                headers={**admin_headers, "X-Request-ID": f"qualification-admin-{index:08d}"},
                remote_addr="127.0.0.10",
            ),
            recorders["admin"],
            {200},
        )

    _parallel(config.admin_request_count, config.concurrency, admin_read)

    target_count = min(config.message_target_count, len(valid_agents))
    targets = valid_agents[:target_count]
    connection = sqlite3.connect(database, timeout=10.0)
    try:
        if targets:
            queue_message(
                connection,
                organization_id=organization_id,
                canonical_client_ids=[str(agent["canonical_client_id"]) for agent in targets],
                title="Qualification message",
                body="Display and acknowledge once",
                severity="info",
            )
    finally:
        connection.close()

    claims: list[tuple[Mapping[str, Any], Mapping[str, Any]] | None] = [None] * target_count

    def claim(index: int):
        agent = targets[index]
        response = _call(
            api,
            _request(
                "POST",
                "/api/v1/agents/heartbeat",
                {
                    "event_id": f"message-heartbeat-{index:06d}",
                    "timezone_name": config.timezone_name,
                    "payload": _heartbeat_payload(index, config.heartbeat_rounds + 1),
                },
                headers=headers(agent),
            ),
            recorders["message_claim"],
            {200},
        )
        if response is not None and response.status == 200:
            messages = response.payload.get("messages") or []
            if messages:
                claims[index] = (agent, dict(messages[0]))
        return response

    _parallel(target_count, config.concurrency, claim)
    claimed = [claim_value for claim_value in claims if claim_value is not None]

    def acknowledge(index: int):
        agent, message = claimed[index]
        return _call(
            api,
            _request(
                "POST",
                f"/api/v1/agents/messages/{message['delivery_id']}/ack",
                {
                    "dispatch_token": message["dispatch_token"],
                    "client_receipt_id": f"qualification-receipt-{index:06d}",
                    "detail": {"displayed": True, "source": "qualification"},
                },
                headers=headers(agent),
            ),
            recorders["message_ack"],
            {200},
        )

    _parallel(len(claimed), config.concurrency, acknowledge)

    api = CombinedAPI(database, max_body_bytes=2 * 1024 * 1024)
    if valid_agents:
        first = valid_agents[0]
        _call(
            api,
            _request(
                "POST",
                "/api/v1/agents/heartbeat",
                {
                    "event_id": "restart-heartbeat-000001",
                    "timezone_name": config.timezone_name,
                    "payload": _heartbeat_payload(0, config.heartbeat_rounds + 2),
                },
                headers=headers(first),
            ),
            recorders["restart"],
            {200},
        )

    checkpoint_after = _checkpoint(database)
    wal_path = Path(str(database) + "-wal")
    wal_bytes = wal_path.stat().st_size if wal_path.exists() else 0
    source_counts = _database_counts(database)

    backup_path = database.parent / "backup" / f"qualification-{config.agent_count}.db"
    backup = backup_database(database, backup_path)
    verified = verify_backup(backup_path)
    restored_path = database.parent / "restored" / f"qualification-{config.agent_count}.db"
    restore = restore_database(backup_path, restored_path, service_stopped=True)
    restored_counts = _database_counts(restored_path)

    _, peak_memory = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    fd_after = _fd_count()
    finished_at = datetime.now(timezone.utc)

    operations = {name: recorder.summary() for name, recorder in recorders.items()}
    total_operations = sum(int(value["count"]) for value in operations.values())
    total_failures = sum(int(value["failures"]) for value in operations.values())
    error_rate = round(total_failures / total_operations, 6) if total_operations else 0.0
    expected_heartbeats = len(valid_agents) * config.heartbeat_rounds + target_count + (1 if valid_agents else 0)

    invariants = {
        "all_agents_registered": len(valid_agents) == config.agent_count,
        "agent_credentials_exact": source_counts["agent_credentials_v1"] == config.agent_count,
        "current_clients_exact": source_counts["agent_current_v1"] == config.agent_count,
        "heartbeat_rows_exact": source_counts["agent_heartbeat_events_v1"] == expected_heartbeats,
        "history_samples_exact": source_counts["history_samples_v1"] == expected_heartbeats,
        "daily_rollups_exact": source_counts["history_daily_rollup_v1"] == config.agent_count,
        "duplicate_replay_idempotent": duplicate_insertions == 0,
        "all_target_messages_claimed": len(claimed) == target_count,
        "all_target_messages_acknowledged": source_counts["client_message_receipts_v1"] == target_count,
        "backup_verified": bool(verified.get("ok")),
        "restore_counts_match": source_counts == restored_counts,
        "wal_checkpoint_not_busy": int(checkpoint_after["busy"]) == 0,
    }

    limits = config.thresholds
    threshold_results = {
        "error_rate": error_rate <= limits.max_error_rate,
        "registration_p95": operations["registration"]["latency_ms"]["p95"] <= limits.max_registration_p95_ms,
        "heartbeat_p95": operations["heartbeat"]["latency_ms"]["p95"] <= limits.max_heartbeat_p95_ms,
        "admin_p95": operations["admin"]["latency_ms"]["p95"] <= limits.max_admin_p95_ms,
        "wal_size": wal_bytes <= limits.max_wal_bytes,
        "peak_memory": peak_memory <= limits.max_peak_traced_memory_bytes,
    }

    evidence: dict[str, Any] = {
        "schema": "sagar-monitor-qualification-v1",
        "scenario": asdict(config),
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "duration_seconds": round((finished_at - started_at).total_seconds(), 3),
        "environment": {
            "platform": platform.platform(),
            "python": sys.version,
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
        },
        "operations": operations,
        "totals": {
            "operations": total_operations,
            "failures": total_failures,
            "error_rate": error_rate,
            "registered_agents": len(valid_agents),
            "claimed_messages": len(claimed),
            "duplicate_insertions": duplicate_insertions,
        },
        "database": {
            "database_bytes": database.stat().st_size,
            "wal_bytes": wal_bytes,
            "checkpoint_before": checkpoint_before,
            "checkpoint_after": checkpoint_after,
            "source_counts": source_counts,
            "restored_counts": restored_counts,
        },
        "backup": {"backup": backup, "verified": verified, "restore": restore},
        "resources": {
            "peak_traced_memory_bytes": peak_memory,
            "file_descriptors_before": fd_before,
            "file_descriptors_after": fd_after,
        },
        "invariants": invariants,
        "threshold_results": threshold_results,
    }
    evidence["passed"] = all(invariants.values()) and all(threshold_results.values())
    evidence["evidence_sha256"] = _hash(evidence)
    return evidence
