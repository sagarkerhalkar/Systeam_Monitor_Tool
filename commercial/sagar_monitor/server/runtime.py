from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
import logging
import socket
import ssl

from sagar_monitor.api.application import Request, Response

from .application import CombinedAPI
from .bootstrap import run_all_migrations
from .config import ServerConfig


LOGGER = logging.getLogger("sagar_monitor.commercial_server")


class CommercialHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 128

    def __init__(self, config: ServerConfig, api: CombinedAPI):
        self.config = config
        self.api = api
        super().__init__((config.bind_host, config.port), CommercialRequestHandler)


class CommercialRequestHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "SagarMonitor"
    sys_version = ""

    @property
    def commercial_server(self) -> CommercialHTTPServer:
        return self.server  # type: ignore[return-value]

    def version_string(self) -> str:
        return "SagarMonitor"

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(self.commercial_server.config.socket_timeout_seconds)

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info(
            "http_request",
            extra={
                "remote_addr": self.client_address[0] if self.client_address else "",
                "method": self.command,
                "path": self.path.split("?", 1)[0],
                "request_summary": format % args,
            },
        )

    def _json_error(self, status: int, code: str, message: str) -> None:
        self._send(
            Response(
                status=status,
                payload={"ok": False, "error": {"code": code, "message": message}},
                headers={
                    "Content-Type": "application/json; charset=utf-8",
                    "Cache-Control": "no-store",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        )

    def _header_size(self) -> int:
        return sum(len(str(key)) + len(str(value)) + 4 for key, value in self.headers.items())

    def _read_body(self) -> bytes | None:
        config = self.commercial_server.config
        if self.headers.get("Transfer-Encoding"):
            self._json_error(
                HTTPStatus.BAD_REQUEST,
                "transfer_encoding",
                "Transfer-Encoding is not accepted; send a fixed Content-Length",
            )
            return None
        if self.headers.get("Expect"):
            self._json_error(HTTPStatus.EXPECTATION_FAILED, "expectation", "Expect header is not supported")
            return None
        if self._header_size() > config.max_header_bytes:
            self._json_error(HTTPStatus.REQUEST_HEADER_FIELDS_TOO_LARGE, "headers_too_large", "request headers are too large")
            return None
        raw_length = self.headers.get("Content-Length", "0").strip()
        try:
            length = int(raw_length or "0")
        except ValueError:
            self._json_error(HTTPStatus.BAD_REQUEST, "content_length", "Content-Length must be an integer")
            return None
        if length < 0:
            self._json_error(HTTPStatus.BAD_REQUEST, "content_length", "Content-Length cannot be negative")
            return None
        if length > config.max_body_bytes:
            self._json_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "body_too_large", "request body is too large")
            return None
        if length == 0:
            return b""
        try:
            body = self.rfile.read(length)
        except (OSError, socket.timeout):
            self._json_error(HTTPStatus.REQUEST_TIMEOUT, "request_timeout", "request body timed out")
            return None
        if len(body) != length:
            self._json_error(HTTPStatus.BAD_REQUEST, "incomplete_body", "request body is incomplete")
            return None
        return body

    def _handle(self) -> None:
        body = self._read_body()
        if body is None:
            return
        headers = {str(key): str(value) for key, value in self.headers.items()}
        request = Request(
            method="GET" if self.command.upper() == "HEAD" else self.command,
            target=self.path,
            headers=headers,
            body=body,
            remote_addr=self.client_address[0] if self.client_address else "",
        )
        try:
            response = self.commercial_server.api.handle(request)
        except Exception:
            LOGGER.exception("unhandled commercial API exception")
            response = Response(
                status=HTTPStatus.INTERNAL_SERVER_ERROR,
                payload={"ok": False, "error": {"code": "internal_error", "message": "internal server error"}},
                headers={"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"},
            )
        self._send(response)

    def _send(self, response: Response) -> None:
        body = response.body_bytes()
        self.send_response(int(response.status))
        sent = set()
        for key, value in response.headers.items():
            lower = str(key).lower()
            if lower in {"content-length", "connection", "server", "date"}:
                continue
            self.send_header(str(key), str(value))
            sent.add(lower)
        if "content-type" not in sent:
            self.send_header("Content-Type", "application/json; charset=utf-8")
        if not self.commercial_server.config.allow_loopback_http:
            self.send_header("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command.upper() != "HEAD":
            try:
                self.wfile.write(body)
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
        self.close_connection = True

    do_GET = _handle
    do_POST = _handle
    do_PUT = _handle
    do_PATCH = _handle
    do_DELETE = _handle
    do_HEAD = _handle
    do_OPTIONS = _handle


def _prepare_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    import sqlite3

    connection = sqlite3.connect(path, timeout=10.0)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA busy_timeout=5000")
        run_all_migrations(connection)
        admins = int(
            connection.execute("SELECT COUNT(*) FROM users_v1 WHERE active=1 AND role='admin'").fetchone()[0]
        )
        if admins < 1:
            raise RuntimeError("commercial server has no active administrator; run first-run bootstrap")
    finally:
        connection.close()


def serve(config: ServerConfig) -> None:
    config.validate(require_existing_tls=not config.allow_loopback_http)
    _prepare_database(config.database_path)
    api = CombinedAPI(config.database_path, max_body_bytes=config.max_body_bytes)
    server = CommercialHTTPServer(config, api)
    if not config.allow_loopback_http:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version = ssl.TLSVersion.TLSv1_2
        context.options |= ssl.OP_NO_COMPRESSION
        context.load_cert_chain(
            certfile=str(config.certificate_file),
            keyfile=str(config.private_key_file),
        )
        server.socket = context.wrap_socket(server.socket, server_side=True)
    LOGGER.info(
        "commercial server starting",
        extra={"bind_host": config.bind_host, "port": config.port, "scheme": config.scheme},
    )
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()
