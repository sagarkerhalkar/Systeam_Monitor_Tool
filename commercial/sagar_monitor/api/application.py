from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping
from urllib.parse import parse_qs, urlsplit
import json
import re
import sqlite3
import uuid

from sagar_monitor.messaging import delivery_report, queue_message
from sagar_monitor.messaging.delivery import apply_message_migration
from sagar_monitor.security import (
    append_audit_event,
    apply_security_migration,
    authenticate_user,
    authorize,
    consume_rate_limit,
    create_enrollment_token,
    create_session,
    create_user,
    revoke_session,
    validate_session,
    verify_csrf,
)


JSON_CONTENT_TYPE = "application/json; charset=utf-8"
REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
MESSAGE_ID_RE = re.compile(r"^[A-Za-z0-9-]{8,128}$")


@dataclass(frozen=True)
class Request:
    method: str
    target: str
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""
    remote_addr: str = ""

    @property
    def path(self) -> str:
        return urlsplit(self.target).path

    @property
    def query(self) -> dict[str, list[str]]:
        return parse_qs(urlsplit(self.target).query, keep_blank_values=True)

    def header(self, name: str) -> str:
        wanted = name.lower()
        for key, value in self.headers.items():
            if str(key).lower() == wanted:
                return str(value)
        return ""


@dataclass(frozen=True)
class Response:
    status: int
    payload: Mapping[str, Any]
    headers: Mapping[str, str] = field(default_factory=dict)

    def body_bytes(self) -> bytes:
        return json.dumps(
            dict(self.payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status = int(status)
        self.code = code
        self.message = message


class CommercialAPI:
    """Framework-independent API surface for staged commercial integration."""

    def __init__(
        self,
        database_path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
        max_body_bytes: int = 1024 * 1024,
        login_limit: int = 5,
        login_window_seconds: int = 300,
    ) -> None:
        self.database_path = Path(database_path).expanduser().resolve()
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        if max_body_bytes < 1024 or max_body_bytes > 10 * 1024 * 1024:
            raise ValueError("max_body_bytes must be between 1 KiB and 10 MiB")
        if login_limit < 1 or login_window_seconds < 1:
            raise ValueError("positive login rate limit settings are required")
        self.max_body_bytes = max_body_bytes
        self.login_limit = login_limit
        self.login_window_seconds = login_window_seconds
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            apply_security_migration(connection)
            apply_message_migration(connection)

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
        value = self.clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _request_id(self, request: Request) -> str:
        supplied = request.header("X-Request-ID").strip()
        return supplied if REQUEST_ID_RE.fullmatch(supplied) else str(uuid.uuid4())

    def _response(self, status: int, payload: Mapping[str, Any], request_id: str) -> Response:
        headers = {
            "Content-Type": JSON_CONTENT_TYPE,
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
            "X-Request-ID": request_id,
        }
        return Response(status=status, payload=payload, headers=headers)

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

    def _bearer(self, request: Request) -> str:
        value = request.header("Authorization").strip()
        if not value.lower().startswith("bearer "):
            return ""
        return value[7:].strip()

    def _session(
        self,
        connection: sqlite3.Connection,
        request: Request,
        *,
        csrf: bool = False,
        roles: set[str] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        token = self._bearer(request)
        session = validate_session(
            connection,
            token,
            client_fingerprint=request.header("X-Client-Fingerprint"),
            now=self._now(),
            touch=False,
        )
        if not session:
            raise APIError(HTTPStatus.UNAUTHORIZED, "unauthorized", "valid session is required")
        if csrf and not verify_csrf(connection, token, request.header("X-CSRF-Token")):
            raise APIError(HTTPStatus.FORBIDDEN, "csrf", "valid CSRF token is required")
        if roles and not authorize(session, roles, organization_id=session["organization_id"]):
            raise APIError(HTTPStatus.FORBIDDEN, "forbidden", "role is not allowed")
        return token, session

    @staticmethod
    def _bounded_int(query: Mapping[str, list[str]], name: str, default: int, minimum: int, maximum: int) -> int:
        raw = (query.get(name) or [str(default)])[0]
        try:
            value = int(raw)
        except ValueError:
            raise APIError(HTTPStatus.BAD_REQUEST, "invalid_pagination", f"{name} must be an integer")
        if value < minimum or value > maximum:
            raise APIError(
                HTTPStatus.BAD_REQUEST,
                "invalid_pagination",
                f"{name} must be between {minimum} and {maximum}",
            )
        return value

    def handle(self, request: Request) -> Response:
        request_id = self._request_id(request)
        method = str(request.method or "GET").upper()
        try:
            if len(request.body) > self.max_body_bytes:
                raise APIError(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body_too_large", "request body is too large")
            with self._connection() as connection:
                if method == "GET" and request.path == "/api/v1/health":
                    return self._response(
                        HTTPStatus.OK,
                        {"ok": True, "service": "sagar-monitor-commercial-api", "version": "v1"},
                        request_id,
                    )
                if method == "POST" and request.path == "/api/v1/auth/login":
                    return self._login(connection, request, request_id)
                if method == "GET" and request.path == "/api/v1/auth/me":
                    return self._me(connection, request, request_id)
                if method == "POST" and request.path == "/api/v1/auth/logout":
                    return self._logout(connection, request, request_id)
                if method == "POST" and request.path == "/api/v1/users":
                    return self._create_user(connection, request, request_id)
                if method == "GET" and request.path == "/api/v1/users":
                    return self._list_users(connection, request, request_id)
                if method == "POST" and request.path == "/api/v1/enrollment-tokens":
                    return self._create_enrollment(connection, request, request_id)
                if method == "POST" and request.path == "/api/v1/messages":
                    return self._queue_message(connection, request, request_id)
                if method == "GET" and request.path == "/api/v1/messages":
                    return self._list_messages(connection, request, request_id)
                match = re.fullmatch(r"/api/v1/messages/([A-Za-z0-9-]{8,128})", request.path)
                if method == "GET" and match:
                    return self._message_report(connection, request, request_id, match.group(1))
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
                {"ok": False, "error": {"code": "conflict", "message": "resource already exists or is invalid"}},
                request_id,
            )
        except Exception:
            return self._response(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"ok": False, "error": {"code": "internal_error", "message": "internal server error"}},
                request_id,
            )

    def _login(self, connection: sqlite3.Connection, request: Request, request_id: str) -> Response:
        data = self._json(request)
        organization_id = str(data.get("organization_id") or "").strip()
        username = str(data.get("username") or "").strip()
        password = str(data.get("password") or "")
        if not organization_id or not username or not password:
            raise APIError(HTTPStatus.BAD_REQUEST, "login_fields", "organization_id, username and password are required")
        limit = consume_rate_limit(
            connection,
            f"login:{organization_id}:{username.lower()}:{request.remote_addr}",
            limit=self.login_limit,
            window_seconds=self.login_window_seconds,
            now=self._now(),
        )
        if not limit["allowed"]:
            raise APIError(HTTPStatus.TOO_MANY_REQUESTS, "rate_limited", "too many login attempts")
        user = authenticate_user(
            connection,
            organization_id=organization_id,
            username=username,
            password=password,
        )
        if not user:
            append_audit_event(
                connection,
                organization_id=organization_id,
                event_type="auth.login.failed",
                subject_id=username.lower(),
                detail={"remote_addr": request.remote_addr},
                now=self._now(),
            )
            raise APIError(HTTPStatus.UNAUTHORIZED, "invalid_credentials", "invalid credentials")
        tokens = create_session(
            connection,
            user_id=user["user_id"],
            client_fingerprint=request.header("X-Client-Fingerprint"),
            now=self._now(),
        )
        append_audit_event(
            connection,
            organization_id=organization_id,
            event_type="auth.login.success",
            actor_user_id=user["user_id"],
            subject_id=user["user_id"],
            detail={"remote_addr": request.remote_addr},
            now=self._now(),
        )
        return self._response(
            HTTPStatus.OK,
            {
                "ok": True,
                "session_token": tokens.session_token,
                "csrf_token": tokens.csrf_token,
                "expires_at": tokens.expires_at,
                "user": user,
            },
            request_id,
        )

    def _me(self, connection: sqlite3.Connection, request: Request, request_id: str) -> Response:
        _, session = self._session(connection, request)
        return self._response(
            HTTPStatus.OK,
            {
                "ok": True,
                "user": {
                    "user_id": session["user_id"],
                    "organization_id": session["organization_id"],
                    "username": session["username"],
                    "role": session["role"],
                },
            },
            request_id,
        )

    def _logout(self, connection: sqlite3.Connection, request: Request, request_id: str) -> Response:
        token, session = self._session(connection, request, csrf=True)
        revoke_session(connection, token, now=self._now())
        append_audit_event(
            connection,
            organization_id=session["organization_id"],
            event_type="auth.logout",
            actor_user_id=session["user_id"],
            subject_id=session["user_id"],
            now=self._now(),
        )
        return self._response(HTTPStatus.OK, {"ok": True}, request_id)

    def _create_user(self, connection: sqlite3.Connection, request: Request, request_id: str) -> Response:
        _, session = self._session(connection, request, csrf=True, roles={"admin"})
        data = self._json(request)
        try:
            user_id = create_user(
                connection,
                organization_id=session["organization_id"],
                username=str(data.get("username") or ""),
                password=str(data.get("password") or ""),
                role=str(data.get("role") or "viewer"),
                now=self._now(),
            )
        except ValueError as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, "invalid_user", str(exc))
        append_audit_event(
            connection,
            organization_id=session["organization_id"],
            event_type="user.created",
            actor_user_id=session["user_id"],
            subject_id=user_id,
            detail={"username": str(data.get("username") or ""), "role": str(data.get("role") or "viewer")},
            now=self._now(),
        )
        return self._response(HTTPStatus.CREATED, {"ok": True, "user_id": user_id}, request_id)

    def _list_users(self, connection: sqlite3.Connection, request: Request, request_id: str) -> Response:
        _, session = self._session(connection, request, roles={"admin", "operator"})
        limit = self._bounded_int(request.query, "limit", 50, 1, 200)
        offset = self._bounded_int(request.query, "offset", 0, 0, 1_000_000)
        query = str((request.query.get("q") or [""])[0]).strip().lower()[:100]
        params: list[Any] = [session["organization_id"]]
        where = "organization_id=?"
        if query:
            where += " AND username LIKE ? ESCAPE '\\'"
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            params.append(f"%{escaped}%")
        total = int(connection.execute(f"SELECT COUNT(*) FROM users_v1 WHERE {where}", params).fetchone()[0])
        rows = connection.execute(
            f"""SELECT user_id,username,role,active,created_at,password_changed_at
                FROM users_v1 WHERE {where}
                ORDER BY username,user_id LIMIT ? OFFSET ?""",
            params + [limit, offset],
        ).fetchall()
        return self._response(
            HTTPStatus.OK,
            {"ok": True, "items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset},
            request_id,
        )

    def _create_enrollment(self, connection: sqlite3.Connection, request: Request, request_id: str) -> Response:
        _, session = self._session(connection, request, csrf=True, roles={"admin"})
        data = self._json(request)
        try:
            token = create_enrollment_token(
                connection,
                organization_id=session["organization_id"],
                ttl_seconds=int(data.get("ttl_seconds") or 3600),
                max_uses=int(data.get("max_uses") or 1),
                label=str(data.get("label") or ""),
                now=self._now(),
            )
        except (ValueError, TypeError) as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, "invalid_enrollment", str(exc))
        append_audit_event(
            connection,
            organization_id=session["organization_id"],
            event_type="enrollment.created",
            actor_user_id=session["user_id"],
            detail={"label": str(data.get("label") or ""), "max_uses": int(data.get("max_uses") or 1)},
            now=self._now(),
        )
        return self._response(HTTPStatus.CREATED, {"ok": True, "enrollment_token": token}, request_id)

    def _queue_message(self, connection: sqlite3.Connection, request: Request, request_id: str) -> Response:
        _, session = self._session(connection, request, csrf=True, roles={"admin", "operator"})
        data = self._json(request)
        clients = data.get("canonical_client_ids")
        if not isinstance(clients, list) or len(clients) > 1000:
            raise APIError(HTTPStatus.BAD_REQUEST, "invalid_targets", "canonical_client_ids must be a list of at most 1000 items")
        try:
            result = queue_message(
                connection,
                organization_id=session["organization_id"],
                canonical_client_ids=clients,
                title=str(data.get("title") or ""),
                body=str(data.get("body") or ""),
                severity=str(data.get("severity") or "info"),
                created_by_user_id=session["user_id"],
                ttl_seconds=int(data.get("ttl_seconds") or 24 * 60 * 60),
                max_attempts=int(data.get("max_attempts") or 5),
                metadata=data.get("metadata") if isinstance(data.get("metadata"), dict) else {},
                now=self._now(),
            )
        except (ValueError, TypeError) as exc:
            raise APIError(HTTPStatus.BAD_REQUEST, "invalid_message", str(exc))
        append_audit_event(
            connection,
            organization_id=session["organization_id"],
            event_type="message.queued",
            actor_user_id=session["user_id"],
            subject_id=result["message_id"],
            detail={"target_count": result["target_count"]},
            now=self._now(),
        )
        return self._response(HTTPStatus.CREATED, {"ok": True, **result}, request_id)

    def _list_messages(self, connection: sqlite3.Connection, request: Request, request_id: str) -> Response:
        _, session = self._session(connection, request, roles={"admin", "operator", "viewer"})
        limit = self._bounded_int(request.query, "limit", 50, 1, 200)
        offset = self._bounded_int(request.query, "offset", 0, 0, 1_000_000)
        total = int(
            connection.execute(
                "SELECT COUNT(*) FROM client_messages_v1 WHERE organization_id=?",
                (session["organization_id"],),
            ).fetchone()[0]
        )
        rows = connection.execute(
            """SELECT message_id,title,severity,created_at,not_before,expires_at
               FROM client_messages_v1 WHERE organization_id=?
               ORDER BY created_at DESC,message_id DESC LIMIT ? OFFSET ?""",
            (session["organization_id"], limit, offset),
        ).fetchall()
        return self._response(
            HTTPStatus.OK,
            {"ok": True, "items": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset},
            request_id,
        )

    def _message_report(
        self,
        connection: sqlite3.Connection,
        request: Request,
        request_id: str,
        message_id: str,
    ) -> Response:
        _, session = self._session(connection, request, roles={"admin", "operator", "viewer"})
        if not MESSAGE_ID_RE.fullmatch(message_id):
            raise APIError(HTTPStatus.BAD_REQUEST, "invalid_message_id", "invalid message ID")
        try:
            report = delivery_report(
                connection,
                organization_id=session["organization_id"],
                message_id=message_id,
            )
        except KeyError:
            raise APIError(HTTPStatus.NOT_FOUND, "message_not_found", "message not found")
        return self._response(HTTPStatus.OK, {"ok": True, "message": report}, request_id)


def make_wsgi_app(application: CommercialAPI):
    """Return a PEP 3333 adapter. Use behind a production HTTPS reverse proxy/server."""

    def wsgi(environ, start_response):
        try:
            content_length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            content_length = 0
        if content_length > application.max_body_bytes:
            body = b""
        else:
            body = environ["wsgi.input"].read(max(0, content_length)) if content_length else b""
        headers = {
            key[5:].replace("_", "-"): value
            for key, value in environ.items()
            if key.startswith("HTTP_")
        }
        if environ.get("CONTENT_TYPE"):
            headers["Content-Type"] = environ["CONTENT_TYPE"]
        target = environ.get("PATH_INFO", "")
        if environ.get("QUERY_STRING"):
            target += "?" + environ["QUERY_STRING"]
        request = Request(
            method=environ.get("REQUEST_METHOD", "GET"),
            target=target,
            headers=headers,
            body=(b"x" * (application.max_body_bytes + 1)) if content_length > application.max_body_bytes else body,
            remote_addr=environ.get("REMOTE_ADDR", ""),
        )
        response = application.handle(request)
        payload = response.body_bytes()
        status = HTTPStatus(response.status)
        response_headers = list(response.headers.items()) + [("Content-Length", str(len(payload)))]
        start_response(f"{status.value} {status.phrase}", response_headers)
        return [payload]

    return wsgi
