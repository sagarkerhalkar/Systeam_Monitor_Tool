from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import hashlib
import json
import os
import platform
import time
import uuid

from .collectors import SystemCollector
from .counters import DailyCounterStore
from .inbox import LocalInbox
from .state import AgentCredential, CredentialStore, EdgeQueue, QueuedHeartbeat, QueuedReceipt
from .transport import AgentTransport, TransportError, UnauthorizedError


AGENT_VERSION = "1.0.0"


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


def _retry_delay(identifier: str, attempts: int, *, base: int = 5, maximum: int = 900) -> int:
    exponent = min(8, max(0, int(attempts)))
    raw = min(maximum, base * (2**exponent))
    digest = hashlib.sha256(f"{identifier}:{attempts}".encode("utf-8")).digest()
    jitter = int.from_bytes(digest[:2], "big") % max(1, raw // 4 + 1)
    return min(maximum, raw + jitter)


@dataclass(frozen=True)
class RuntimeConfig:
    state_directory: Path
    timezone_name: str = "Asia/Kolkata"
    heartbeat_interval_seconds: int = 60
    max_heartbeats_per_cycle: int = 20
    max_receipts_per_cycle: int = 50
    queue_limit: int = 10000
    registration_metadata: Mapping[str, Any] = field(default_factory=dict)

    def normalized(self) -> "RuntimeConfig":
        state = Path(self.state_directory).expanduser().resolve()
        timezone_name = str(self.timezone_name or "Asia/Kolkata").strip()
        try:
            ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"unknown timezone: {timezone_name}") from exc
        interval = int(self.heartbeat_interval_seconds)
        if interval < 10 or interval > 3600:
            raise ValueError("heartbeat_interval_seconds must be between 10 and 3600")
        heartbeat_limit = int(self.max_heartbeats_per_cycle)
        receipt_limit = int(self.max_receipts_per_cycle)
        if heartbeat_limit < 1 or heartbeat_limit > 1000:
            raise ValueError("max_heartbeats_per_cycle must be between 1 and 1000")
        if receipt_limit < 1 or receipt_limit > 1000:
            raise ValueError("max_receipts_per_cycle must be between 1 and 1000")
        return RuntimeConfig(
            state_directory=state,
            timezone_name=timezone_name,
            heartbeat_interval_seconds=interval,
            max_heartbeats_per_cycle=heartbeat_limit,
            max_receipts_per_cycle=receipt_limit,
            queue_limit=int(self.queue_limit),
            registration_metadata=dict(self.registration_metadata or {}),
        )


@dataclass(frozen=True)
class RuntimeResult:
    registered: bool
    credential_available: bool
    sample_enqueued: bool
    heartbeats_sent: int
    receipts_sent: int
    messages_staged: int
    authentication_error: bool
    queue_counts: dict[str, int]
    errors: tuple[str, ...]


class AgentRuntime:
    """One commercial runtime used by both Windows and Ubuntu agents."""

    def __init__(
        self,
        config: RuntimeConfig,
        transport: AgentTransport,
        *,
        collector: SystemCollector | None = None,
        clock: Callable[[], datetime] | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.config = config.normalized()
        self.transport = transport
        self.collector = collector or SystemCollector()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self.sleeper = sleeper
        self.credentials = CredentialStore(self.config.state_directory)
        self.queue_path = self.config.state_directory / "edge-queue.sqlite3"
        self.queue = EdgeQueue(self.queue_path, max_heartbeats=self.config.queue_limit)
        self.counters = DailyCounterStore(self.queue_path)
        self.inbox = LocalInbox(self.config.state_directory / "messages")
        self.credentials.ensure_agent_install_id()

    def _now(self) -> datetime:
        return _utc(self.clock())

    def _local_day(self, now: datetime) -> str:
        return now.astimezone(ZoneInfo(self.config.timezone_name)).date().isoformat()

    def register(self, enrollment_token: str) -> tuple[AgentCredential, bool]:
        current = self.credentials.load_credential()
        if current is not None:
            return current, False
        token = str(enrollment_token or "").strip()
        if not token:
            raise RuntimeError("agent is not registered and no enrollment token was supplied")
        install_id = self.credentials.ensure_agent_install_id()
        hostname = platform.node().strip()[:255]
        response = self.transport.register(
            token,
            {
                "agent_install_id": install_id,
                "platform": "windows" if os.name == "nt" else "linux",
                "hostname": hostname,
                "metadata": {
                    "agent_version": AGENT_VERSION,
                    "python_version": platform.python_version(),
                    "machine": platform.machine(),
                    **dict(self.config.registration_metadata),
                },
            },
        )
        credential = self.credentials.save_registration(response)
        self.queue.audit(
            "agent_registered",
            {
                "agent_install_id": credential.agent_install_id,
                "organization_id": credential.organization_id,
                "canonical_client_id": credential.canonical_client_id,
                "token_version": credential.token_version,
            },
            now=self._now(),
        )
        return credential, True

    def enqueue_sample(self, now: datetime | str | None = None) -> str:
        anchor = _utc(now or self._now())
        payload = self.collector.sample()
        network = payload.setdefault("network", {})
        if not isinstance(network, dict):
            network = {}
            payload["network"] = network
        traffic = network.setdefault("traffic", {})
        if not isinstance(traffic, dict):
            traffic = {}
            network["traffic"] = traffic
        raw_down = max(0, int(traffic.get("raw_download_total_bytes") or 0))
        raw_up = max(0, int(traffic.get("raw_upload_total_bytes") or 0))
        day_down, day_up = self.counters.update(
            local_day=self._local_day(anchor),
            download_total=raw_down,
            upload_total=raw_up,
            now=anchor,
        )
        traffic["today_download_bytes"] = day_down
        traffic["today_upload_bytes"] = day_up
        identity = payload.setdefault("identity", {})
        if isinstance(identity, dict):
            identity["agent_install_id"] = self.credentials.ensure_agent_install_id()
        agent = payload.setdefault("agent", {})
        if isinstance(agent, dict):
            agent.update(
                {
                    "version": AGENT_VERSION,
                    "queued_at": anchor.isoformat(),
                    "queue": self.queue.counts(),
                }
            )
        event_id = "hb:" + str(uuid.uuid4())
        self.queue.enqueue_heartbeat(
            event_id=event_id,
            payload=payload,
            timezone_name=self.config.timezone_name,
            now=anchor,
        )
        return event_id

    def _cached_delivery(self, delivery_id: str) -> tuple[bool, bool]:
        with self.queue.connection() as connection:
            row = connection.execute(
                "SELECT acknowledged_at FROM edge_message_cache_v1 WHERE delivery_id=?",
                (delivery_id,),
            ).fetchone()
            if not row:
                return False, False
            return True, bool(row["acknowledged_at"])

    def _refresh_cached_delivery(self, message: Mapping[str, Any], now: datetime) -> None:
        delivery_id = str(message.get("delivery_id") or "")
        exists, acknowledged = self._cached_delivery(delivery_id)
        if not exists:
            self.inbox.stage(message)
            return
        if acknowledged:
            # Server redelivery is authoritative evidence that the previous
            # response did not settle. Reopen the local receipt and retry with
            # the new dispatch lease without showing the popup again.
            with self.queue.connection() as connection:
                connection.execute(
                    "UPDATE edge_message_cache_v1 SET acknowledged_at=NULL WHERE delivery_id=?",
                    (delivery_id,),
                )
        self.queue.cache_message(message, now=now)

    def _promote_displayed(self, now: datetime) -> int:
        promoted = 0
        for message, display in self.inbox.displayed_messages(limit=self.config.max_receipts_per_cycle):
            detail = display.get("detail") if isinstance(display.get("detail"), dict) else {}
            merged = dict(message)
            merged["display_detail"] = detail
            self.queue.cache_message(merged, now=now)
            self.inbox.complete(str(message.get("delivery_id") or ""))
            promoted += 1
        return promoted

    def _flush_receipts(self, credential: AgentCredential, now: datetime) -> tuple[int, bool, list[str]]:
        sent = 0
        authentication_error = False
        errors: list[str] = []
        self._promote_displayed(now)
        for _ in range(self.config.max_receipts_per_cycle):
            receipt: QueuedReceipt | None = self.queue.next_receipt(now=now)
            if receipt is None:
                break
            try:
                self.transport.acknowledge(
                    credential.agent_install_id,
                    credential.agent_token,
                    receipt.delivery_id,
                    {
                        "dispatch_token": receipt.dispatch_token,
                        "client_receipt_id": receipt.client_receipt_id,
                        "detail": receipt.detail,
                    },
                )
                self.queue.complete_receipt(receipt.delivery_id, now=now)
                sent += 1
            except UnauthorizedError as exc:
                authentication_error = True
                errors.append(str(exc))
                self.queue.audit("agent_authentication_rejected", {"operation": "acknowledge"}, now=now)
                break
            except TransportError as exc:
                delay = _retry_delay(receipt.delivery_id, receipt.attempts)
                if not exc.retryable:
                    delay = max(delay, 3600)
                self.queue.fail_receipt(
                    receipt.delivery_id,
                    str(exc),
                    retry_after_seconds=delay,
                    now=now,
                )
                errors.append(str(exc))
                break
        return sent, authentication_error, errors

    def _flush_heartbeats(self, credential: AgentCredential, now: datetime) -> tuple[int, int, bool, list[str]]:
        sent = 0
        staged = 0
        authentication_error = False
        errors: list[str] = []
        for _ in range(self.config.max_heartbeats_per_cycle):
            event: QueuedHeartbeat | None = self.queue.next_heartbeat(now=now)
            if event is None:
                break
            try:
                response = self.transport.heartbeat(
                    credential.agent_install_id,
                    credential.agent_token,
                    {
                        "event_id": event.event_id,
                        "timezone_name": event.timezone_name,
                        "payload": event.payload,
                    },
                )
                self.queue.complete_heartbeat(event.event_id)
                sent += 1
                messages = response.get("messages") if isinstance(response.get("messages"), list) else []
                for message in messages:
                    if not isinstance(message, dict):
                        continue
                    before, _ = self._cached_delivery(str(message.get("delivery_id") or ""))
                    self._refresh_cached_delivery(message, now)
                    if not before:
                        staged += 1
            except UnauthorizedError as exc:
                authentication_error = True
                errors.append(str(exc))
                self.queue.audit("agent_authentication_rejected", {"operation": "heartbeat"}, now=now)
                break
            except TransportError as exc:
                delay = _retry_delay(event.event_id, event.attempts)
                if not exc.retryable:
                    delay = max(delay, 3600)
                self.queue.fail_heartbeat(
                    event.event_id,
                    str(exc),
                    retry_after_seconds=delay,
                    now=now,
                )
                errors.append(str(exc))
                break
        return sent, staged, authentication_error, errors

    def run_cycle(self, *, enrollment_token: str = "", collect_sample: bool = True) -> RuntimeResult:
        registered = False
        sample_enqueued = False
        errors: list[str] = []
        try:
            credential, registered = self.register(enrollment_token)
        except (TransportError, RuntimeError, ValueError) as exc:
            return RuntimeResult(
                registered=False,
                credential_available=False,
                sample_enqueued=False,
                heartbeats_sent=0,
                receipts_sent=0,
                messages_staged=0,
                authentication_error=isinstance(exc, UnauthorizedError),
                queue_counts=self.queue.counts(),
                errors=(str(exc),),
            )
        now = self._now()
        receipts_sent, receipt_auth_error, receipt_errors = self._flush_receipts(credential, now)
        errors.extend(receipt_errors)
        if collect_sample:
            try:
                self.enqueue_sample(now)
                sample_enqueued = True
            except Exception as exc:
                errors.append(f"metric collection failed: {exc}")
                self.queue.audit("metric_collection_failed", {"error": str(exc)[:1000]}, now=now)
        heartbeats_sent, messages_staged, heartbeat_auth_error, heartbeat_errors = self._flush_heartbeats(
            credential,
            now,
        )
        errors.extend(heartbeat_errors)
        return RuntimeResult(
            registered=registered,
            credential_available=True,
            sample_enqueued=sample_enqueued,
            heartbeats_sent=heartbeats_sent,
            receipts_sent=receipts_sent,
            messages_staged=messages_staged,
            authentication_error=receipt_auth_error or heartbeat_auth_error,
            queue_counts=self.queue.counts(),
            errors=tuple(errors),
        )

    def rotate_token(self, reason: str = "scheduled agent token rotation") -> AgentCredential:
        credential = self.credentials.load_credential()
        if credential is None:
            raise RuntimeError("agent is not registered")
        response = self.transport.rotate(
            credential.agent_install_id,
            credential.agent_token,
            reason,
        )
        return self.credentials.save_rotated_token(
            str(response.get("agent_token") or ""),
            int(response.get("token_version") or 0),
        )

    def run_forever(self, *, enrollment_token_provider: Callable[[], str] | None = None) -> None:
        provider = enrollment_token_provider or (lambda: "")
        while True:
            result = self.run_cycle(enrollment_token=provider(), collect_sample=True)
            if result.authentication_error:
                self.sleeper(max(300, self.config.heartbeat_interval_seconds))
            else:
                self.sleeper(self.config.heartbeat_interval_seconds)
