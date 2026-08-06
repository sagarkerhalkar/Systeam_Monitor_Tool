from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import json
import os


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def _path(value: object, *, base: Path) -> Path:
    text = os.path.expandvars(str(value or "").strip())
    if not text:
        raise ValueError("required path is missing")
    candidate = Path(text).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve()


@dataclass(frozen=True)
class ServerConfig:
    bind_host: str
    port: int
    database_path: Path
    certificate_file: Path
    private_key_file: Path
    backup_directory: Path
    max_body_bytes: int = 2 * 1024 * 1024
    max_header_bytes: int = 32 * 1024
    socket_timeout_seconds: float = 30.0
    allow_loopback_http: bool = False
    server_label: str = "Sagar Monitor Commercial Server"

    def validate(self, *, require_existing_tls: bool = True) -> "ServerConfig":
        host = str(self.bind_host or "").strip()
        if not host:
            raise ValueError("bind_host is required")
        if not 1 <= int(self.port) <= 65535:
            raise ValueError("port must be between 1 and 65535")
        if not 1024 <= int(self.max_body_bytes) <= 10 * 1024 * 1024:
            raise ValueError("max_body_bytes must be between 1 KiB and 10 MiB")
        if not 4096 <= int(self.max_header_bytes) <= 128 * 1024:
            raise ValueError("max_header_bytes must be between 4 KiB and 128 KiB")
        if not 1.0 <= float(self.socket_timeout_seconds) <= 300.0:
            raise ValueError("socket_timeout_seconds must be between 1 and 300")
        if self.allow_loopback_http and host.lower() not in _LOOPBACK_HOSTS:
            raise ValueError("plain HTTP is allowed only on an explicit loopback bind host")
        if require_existing_tls and not self.allow_loopback_http:
            if not self.certificate_file.is_file():
                raise ValueError(f"TLS certificate file is missing: {self.certificate_file}")
            if not self.private_key_file.is_file():
                raise ValueError(f"TLS private key file is missing: {self.private_key_file}")
        return self

    @property
    def scheme(self) -> str:
        return "http" if self.allow_loopback_http else "https"

    @property
    def local_url(self) -> str:
        host = self.bind_host
        if host in {"0.0.0.0", "::"}:
            host = "127.0.0.1"
        return f"{self.scheme}://{host}:{self.port}"


def load_server_config(path: str | Path) -> ServerConfig:
    config_path = Path(path).expanduser().resolve()
    try:
        value = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise RuntimeError(f"cannot read server configuration: {exc}") from exc
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("server configuration is not valid JSON") from exc
    if not isinstance(value, Mapping):
        raise RuntimeError("server configuration must be a JSON object")
    base = config_path.parent
    config = ServerConfig(
        bind_host=str(value.get("bind_host") or "0.0.0.0").strip(),
        port=int(value.get("port") or 8443),
        database_path=_path(value.get("database_path") or "data/commercial.db", base=base),
        certificate_file=_path(value.get("certificate_file") or "tls/server.crt", base=base),
        private_key_file=_path(value.get("private_key_file") or "tls/server.key", base=base),
        backup_directory=_path(value.get("backup_directory") or "backups", base=base),
        max_body_bytes=int(value.get("max_body_bytes") or 2 * 1024 * 1024),
        max_header_bytes=int(value.get("max_header_bytes") or 32 * 1024),
        socket_timeout_seconds=float(value.get("socket_timeout_seconds") or 30.0),
        allow_loopback_http=bool(value.get("allow_loopback_http") or False),
        server_label=str(value.get("server_label") or "Sagar Monitor Commercial Server").strip()[:120],
    )
    config.database_path.parent.mkdir(parents=True, exist_ok=True)
    config.backup_directory.mkdir(parents=True, exist_ok=True)
    return config.validate(require_existing_tls=False)
