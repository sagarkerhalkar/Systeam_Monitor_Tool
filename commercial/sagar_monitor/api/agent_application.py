from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping
import json
import re
import sqlite3
import uuid

from sagar_monitor.agents import (
    apply_agent_migration,
    authenticate_agent,
    ingest_heartbeat,
    register_agent,
    rotate_agent_token,
)
from sagar_monitor.history.incremental import apply_history_migration
from sagar_monitor.messaging import (
    acknowledge_delivery,
    apply_message_migration,
    claim_pending_deliveries,
)
from sagar_monitor.security import apply_security_migration, consume_rate_limit

from .application import APIError, JSON_CONTENT_TYPE, Request, Response


DELIVERY_PATH = re.compile(r"^/api/v1/agents/messages/([A-Za-z0-9-]{8,128})/ack$")


class AgentAPI:
    """Authenticated commercial agent registration, heartbeat and message API."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
        max_body_bytes: int = 2 * 1024 * 1024,
        registration_limit: int = 10,
        registration_window_seconds: int = 300,
    ) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        if max_body_bytes < 1024 or max_body_bytes > 10 * 1024 * 1024:
            raise ValueError("max_body_bytes must be between 1 KiB and 10 MiB")
        if registration_limit < 1 or registration_window_seconds < 1:
            raise ValueError("positive registration rate limit settings are required")
        self.max_body_bytes = max_body_bytes
        self.registration_limit = registration_limit
        self.registration_window_seconds = registration_window_seconds
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            apply_security_migration(connection)
            apply_message_migration(connection)
            apply_history_migration(connection)
            apply_agent_migration(connection)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database_path, timeout=5.0)
        try:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA busy_timeout=5000")
            yield connection
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()

    def _now(self) -> datetime:
        result = self.clock()
        if result.tzinfo is None:
            result = result.replace(tzinfo=timezone.utc)
        return result.astimezone(timezone.utc)

    @staticmethod
    def _request_id(request: Request) -> str:
        supplied = request.header("X-Request-ID").strip()
        if re.fullmatch(r"[A-Za-z0-9._:-]{8,128}", supplied):
            return supplied
        return str(uuid.uuid4())

    @staticmethod
    def _response(status: int, payload: Mapping[str, Any], request_id: str) -> Response:
        return Response(
            status=int(status),
            payload=payload,
            headers={
                "Content-Type": JSON_CONTENT_TYPE,
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "X-Frame-Options": "DENY",
                "Referrer-Policy": "no-referrer",
                "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
                "X-Request-ID": request_id,
            },
        )

    def _json(self, request: Request) -> dict[str, Any]:
        if len(request.body) > self.max_body_bytes:
            raise APIError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body_too_large", "request body is too large")
        content_type = request.header("Content-Type").split(";", 1)[0].strip().lower()
        if request.body and content_type != "application/json":
            raise APIError(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "content_type", "application/json is required")
        if not request.body:
            return {}
        try:
            value = json.loads(request.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise APIError(HTTPStatus.BAD_REQUEST, "invalid_json", "request body is not valid JSON")
        if not isinstance(value, dict):
            raise APIError(HTTPStatus.BAD_REQUEST, "invalid_json", "JSON object is required")
        return value

    @staticmethod
    def _authorization(request: Request, scheme: str) -> str:
        value = request.header("Authorization").strip()
        prefix = scheme.lower() + " "
        if not value.lower().startswith(prefix):
            return ""
        return value[len(prefix):].strip()

    def _agent(self, connection: sqlite3.Connection, request: Request):
        agent_id = request.header("X-Agent-ID").strip()
        token = self._authorization(request, "Agent")
        identity = authenticate_agent(
            connection,
            agent_install_id=agent_id,
            agent_token=token,
        )
        if not identity:
            raise APIError(HTTPStatus.UNAUTHORIZED, "agent_unauthorized", "valid active agent credential is required")
        return token, identity

    def handle(self, request: Request) -> Response:
        request_id = self._request_id(request)
        method = str(request.method or "GET").upper()
        try:
            if len(request.body) > self.max_body_bytes:
                raise APIError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body_too_large", "request body is too large")
            with self._connection() as connection:
                if method == "POST" and request.path == "/api/v1/agents/register":
                    return self._register(connection, request, request_id)
                if method == "POST" and request.path == "/api/v1/agents/heartbeat":
                    return self._heartbeat(connection, request, request_id)
                if method == "POST" and request.path == "/api/v1/agents/token/rotate":
                    return self._rotate(connection, request, request_id)
                match = DELIVERY_PATH.fullmatch(request.path)
                if method == "POST" and match:
                    return self._acknowledge(connection, request, request_id, match.group(1))
                if method == "GET" and request.path == "/api/v1/agents/status":
                    return self._status(connection, request, request_id)
                raise APIError(HTTPStatus.NOT_FOUND, "not_found", "route not found")
        except APIError as exc:
            return self._response(
                exc.status,
                {"ok": False, "error": {"code": exc.code, "message": exc.message}},
                request_id,
            )
        except sqlite3.IntegrityError:
            return self._response(
                HTTPStatus.CONFLICT,
                {"ok": False, "error": {"code": "conflict", "message": "agent or event already exists"}},
                request_id,
            )
        except PermissionError as exc:
            return self._response(
                HTTPStatus.UNAUTHORIZED,
                {"ok": False, "error": {"code": "agent_unauthorized", "message": str(exc)}},
                request_id,
            )
        except ValueError as exc:
            return self._response(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": {"code": "invalid_request", "message": str(exc)}},
                request_id,
            )
        except Exception:
            return self._response(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": {"code": "internal_error", "message": "internal server error"}},
                request_id,
            )

    def _register(self, connection: sqlite3.Connection, request: Request, request_id: str) -> Response:
        enrollment_token = self._authorization(request, "Enrollment")
        if not enrollment_token:
            raise APIError(HTTPStatus.UNAUTHORIZED, "enrollment_required", "valid enrollment token is required")
        limit = consume_rate_limit(
            connection,
            f"agent-register:{request.remote_addr}",
            limit=self.registration_limit,
            window_seconds=self.registration_window_seconds,
            now=self._now(),
        )
        if not limit["allowed"]:
            raise APIError(HTTPStatus.TOO_MANY_REQUESTS, "rate_limited", "too many registration attempts")
        data = self._json(request)
        result = register_agent(
            connection,
            enrollment_token=enrollment_token,
            agent_install_id=str(data.get("agent_install_id") or ""),
            platform=str(data.get("platform") or ""),
            hostname=str(data.get("hostname") or ""),
            metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
            now=self._now(),
        )
        return self._response(HTTPStatus.CREATED, {"ok": True, **result}, request_id)

    def _heartbeat(self, connection: sqlite3.Connection, request: Request, request_id: str) -> Response:
        _, agent = self._agent(connection, request)
        data = self._json(request)
        payload = data.get("payload")
        if not isinstance(payload, dict):
            raise APIError(HTTPStatus.BAD_REQUEST, "invalid_payload", "payload must be a JSON object")
        result = ingest_heartbeat(
            connection,
            agent=agent,
            client_event_id=str(data.get("event_id") or ""),
            payload=payload,
            timezone_name=str(data.get("timezone_name") or "Asia/Kolkata"),
            received_at=self._now(),
        )
        claims = claim_pending_deliveries(
            connection,
            organization_id=agent.organization_id,
            canonical_client_id=agent.canonical_client_id,
            limit=20,
            now=self._now(),
        )
        messages = [
            {
                "delivery_id": claim.delivery_id,
                "message_id": claim.message_id,
                "dispatch_token": claim.dispatch_token,
                "title": claim.title,
                "body": claim.body,
                "severity": claim.severity,
                "attempt_count": claim.attempt_count,
                "expires_at": claim.expires_at,
                "metadata": claim.metadata,
            }
            for claim in claims
        ]
        return self._response(
            HTTPStatus.OK,
            {"ok": True, "heartbeat": result, "messages": messages},
            request_id,
        )

    def _acknowledge(
        self,
        connection: sqlite3.Connection,
        request: Request,
        request_id: str,
        delivery_id: str,
    ) -> Response:
        _, agent = self._agent(connection, request)
        data = self._json(request)
        result = acknowledge_delivery(
            connection,
            organization_id=agent.organization_id,
            canonical_client_id=agent.canonical_client_id,
            delivery_id=delivery_id,
            dispatch_token=str(data.get("dispatch_token") or ""),
            client_receipt_id=str(data.get("client_receipt_id") or ""),
            detail=data.get("detail") if isinstance(data.get("detail"), dict) else {},
            now=self._now(),
        )
        return self._response(HTTPStatus.OK, {"ok": True, **result}, request_id)

    def _rotate(self, connection: sqlite3.Connection, request: Request, request_id: str) -> Response:
        current_token, agent = self._agent(connection, request)
        data = self._json(request)
        result = rotate_agent_token(
            connection,
            agent_install_id=agent.agent_install_id,
            current_token=current_token,
            reason=str(data.get("reason") or "agent requested rotation"),
            now=self._now(),
        )
        return self._response(HTTPStatus.OK, {"ok": True, **result}, request_id)

    def _status(self, connection: sqlite3.Connection, request: Request, request_id: str) -> Response:
        _, agent = self._agent(connection, request)
        current = connection.execute(
            """SELECT hostname,platform,updated_at,last_event_key,summary_json
               FROM agent_current_v1
               WHERE organization_id=? AND canonical_client_id=?""",
            (agent.organization_id, agent.canonical_client_id),
        ).fetchone()
        return self._response(
            HTTPStatus.OK,
            {
                "ok": True,
                "agent": {
                    "agent_install_id": agent.agent_install_id,
                    "organization_id": agent.organization_id,
                    "canonical_client_id": agent.canonical_client_id,
                    "platform": agent.platform,
                    "hostname": agent.current_hostname,
                    "token_version": agent.token_version,
                },
                "current": dict(current) if current else None,
            },
            request_id,
        )
