from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request as URLRequest, urlopen
import json
import ssl
import uuid


class TransportError(RuntimeError):
    def __init__(self, message: str, *, status: int = 0, retryable: bool = True) -> None:
        super().__init__(message)
        self.status = int(status)
        self.retryable = bool(retryable)


class UnauthorizedError(TransportError):
    def __init__(self, message: str = "agent credential was rejected") -> None:
        super().__init__(message, status=401, retryable=False)


class AgentTransport(Protocol):
    def register(self, enrollment_token: str, payload: Mapping[str, Any]) -> dict[str, Any]: ...

    def heartbeat(
        self,
        agent_install_id: str,
        agent_token: str,
        event: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def acknowledge(
        self,
        agent_install_id: str,
        agent_token: str,
        delivery_id: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]: ...

    def status(self, agent_install_id: str, agent_token: str) -> dict[str, Any]: ...

    def rotate(self, agent_install_id: str, agent_token: str, reason: str) -> dict[str, Any]: ...


@dataclass(frozen=True)
class HTTPSettings:
    server_url: str
    timeout_seconds: float = 20.0
    ca_bundle: str = ""
    allow_loopback_http: bool = False
    user_agent: str = "SagarMonitorCommercialAgent/1.0"


class HTTPAgentTransport:
    """Small HTTPS JSON client using only the Python standard library."""

    def __init__(
        self,
        server_url: str,
        *,
        timeout_seconds: float = 20.0,
        ca_bundle: str = "",
        allow_loopback_http: bool = False,
        user_agent: str = "SagarMonitorCommercialAgent/1.0",
    ) -> None:
        clean = str(server_url or "").strip().rstrip("/")
        parsed = urlparse(clean)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname:
            raise ValueError("server_url must be an absolute HTTP(S) URL")
        if parsed.scheme != "https":
            loopback = parsed.hostname.lower() in {"localhost", "127.0.0.1", "::1"}
            if not (allow_loopback_http and loopback):
                raise ValueError("HTTPS is required except explicit loopback development mode")
        if timeout_seconds < 1 or timeout_seconds > 300:
            raise ValueError("timeout_seconds must be between 1 and 300")
        self.settings = HTTPSettings(
            server_url=clean,
            timeout_seconds=float(timeout_seconds),
            ca_bundle=str(ca_bundle or "").strip(),
            allow_loopback_http=bool(allow_loopback_http),
            user_agent=str(user_agent or "SagarMonitorCommercialAgent/1.0")[:200],
        )
        self.ssl_context = ssl.create_default_context(cafile=self.settings.ca_bundle or None)
        self.ssl_context.minimum_version = ssl.TLSVersion.TLSv1_2

    @staticmethod
    def _error_message(body: bytes, fallback: str) -> str:
        try:
            value = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
            return fallback
        if isinstance(value, dict):
            error = value.get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])[:1000]
        return fallback

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Mapping[str, Any] | None = None,
        authorization: str = "",
        agent_install_id: str = "",
    ) -> dict[str, Any]:
        body = b""
        headers = {
            "Accept": "application/json",
            "User-Agent": self.settings.user_agent,
            "X-Request-ID": str(uuid.uuid4()),
        }
        if payload is not None:
            body = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if authorization:
            headers["Authorization"] = authorization
        if agent_install_id:
            headers["X-Agent-ID"] = agent_install_id
        request = URLRequest(
            self.settings.server_url + path,
            data=body if payload is not None else None,
            headers=headers,
            method=method.upper(),
        )
        try:
            with urlopen(
                request,
                timeout=self.settings.timeout_seconds,
                context=self.ssl_context if self.settings.server_url.startswith("https://") else None,
            ) as response:
                raw = response.read(10 * 1024 * 1024 + 1)
                if len(raw) > 10 * 1024 * 1024:
                    raise TransportError("server response exceeded 10 MiB", retryable=False)
                status = int(getattr(response, "status", 200))
        except HTTPError as exc:
            raw = exc.read(1024 * 1024)
            message = self._error_message(raw, f"HTTP {exc.code}")
            if exc.code in {401, 403}:
                raise UnauthorizedError(message) from exc
            retryable = exc.code in {408, 409, 425, 429, 500, 502, 503, 504}
            raise TransportError(message, status=exc.code, retryable=retryable) from exc
        except (URLError, TimeoutError, OSError, ssl.SSLError) as exc:
            raise TransportError(f"network request failed: {exc}", retryable=True) from exc
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise TransportError("server returned invalid JSON", status=status, retryable=False) from exc
        if not isinstance(value, dict):
            raise TransportError("server returned a non-object JSON response", status=status, retryable=False)
        if status < 200 or status >= 300 or value.get("ok") is False:
            raise TransportError(self._error_message(raw, f"HTTP {status}"), status=status, retryable=status >= 500)
        return value

    def register(self, enrollment_token: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/agents/register",
            payload=payload,
            authorization=f"Enrollment {enrollment_token}",
        )

    def heartbeat(
        self,
        agent_install_id: str,
        agent_token: str,
        event: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/agents/heartbeat",
            payload=event,
            authorization=f"Agent {agent_token}",
            agent_install_id=agent_install_id,
        )

    def acknowledge(
        self,
        agent_install_id: str,
        agent_token: str,
        delivery_id: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        clean_delivery = str(delivery_id or "").strip()
        if not clean_delivery or "/" in clean_delivery or "\\" in clean_delivery:
            raise ValueError("invalid delivery_id")
        return self._request(
            "POST",
            f"/api/v1/agents/messages/{clean_delivery}/ack",
            payload=payload,
            authorization=f"Agent {agent_token}",
            agent_install_id=agent_install_id,
        )

    def status(self, agent_install_id: str, agent_token: str) -> dict[str, Any]:
        return self._request(
            "GET",
            "/api/v1/agents/status",
            authorization=f"Agent {agent_token}",
            agent_install_id=agent_install_id,
        )

    def rotate(self, agent_install_id: str, agent_token: str, reason: str) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/v1/agents/token/rotate",
            payload={"reason": str(reason or "scheduled rotation")[:500]},
            authorization=f"Agent {agent_token}",
            agent_install_id=agent_install_id,
        )
