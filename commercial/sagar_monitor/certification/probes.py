from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from time import monotonic, perf_counter, sleep
from typing import Any
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import hashlib
import json
import os
import platform
import shutil
import socket
import sqlite3
import ssl
import subprocess
import sys


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, min(len(ordered) - 1, int((percentile / 100.0) * len(ordered) + 0.999999) - 1))
    return round(ordered[rank], 3)


def _memory_bytes() -> int | None:
    if os.name == "nt":
        try:
            import ctypes

            class MemoryStatus(ctypes.Structure):
                _fields_ = [
                    ("length", ctypes.c_ulong),
                    ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong),
                    ("available_physical", ctypes.c_ulonglong),
                    ("total_page_file", ctypes.c_ulonglong),
                    ("available_page_file", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong),
                    ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended_virtual", ctypes.c_ulonglong),
                ]

            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.total_physical)
        except (AttributeError, OSError, ValueError):
            return None
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return int(pages) * int(page_size)
    except (AttributeError, OSError, ValueError):
        return None


def machine_snapshot(path: str | Path = ".") -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    usage = shutil.disk_usage(target if target.exists() else target.parent)
    return {
        "captured_at": _utc_now(),
        "hostname": socket.gethostname(),
        "platform": platform.system().lower(),
        "platform_release": platform.release(),
        "platform_version": platform.version(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "python_version": platform.python_version(),
        "python_executable": str(Path(sys.executable).resolve()),
        "cpu_count": os.cpu_count(),
        "memory_bytes": _memory_bytes(),
        "disk": {
            "path": str(target),
            "total_bytes": int(usage.total),
            "used_bytes": int(usage.used),
            "free_bytes": int(usage.free),
        },
        "process_id": os.getpid(),
    }


def sqlite_probe(database_path: str | Path) -> dict[str, Any]:
    database = Path(database_path).expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError(f"database is missing: {database}")
    connection = sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=10.0)
    try:
        quick_check = str(connection.execute("PRAGMA quick_check").fetchone()[0])
        integrity_check = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
        page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
        page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
        journal_mode = str(connection.execute("PRAGMA journal_mode").fetchone()[0]).lower()
    finally:
        connection.close()
    result = {
        "database_path": str(database),
        "database_bytes": database.stat().st_size,
        "wal_bytes": Path(str(database) + "-wal").stat().st_size if Path(str(database) + "-wal").exists() else 0,
        "quick_check": quick_check,
        "integrity_check": integrity_check,
        "page_count": page_count,
        "page_size": page_size,
        "journal_mode": journal_mode,
    }
    result["ok"] = quick_check.lower() == "ok" and integrity_check.lower() == "ok"
    return result


def disk_capacity_probe(path: str | Path, *, minimum_free_bytes: int = 5 * 1024 * 1024 * 1024) -> dict[str, Any]:
    target = Path(path).expanduser().resolve()
    usage = shutil.disk_usage(target if target.exists() else target.parent)
    result = {
        "path": str(target),
        "total_bytes": int(usage.total),
        "used_bytes": int(usage.used),
        "free_bytes": int(usage.free),
        "minimum_free_bytes": int(minimum_free_bytes),
    }
    result["ok"] = int(usage.free) >= int(minimum_free_bytes)
    return result


def _ssl_context(ca_bundle: str | Path | None) -> ssl.SSLContext:
    if ca_bundle:
        return ssl.create_default_context(cafile=str(Path(ca_bundle).expanduser().resolve()))
    return ssl.create_default_context()


def https_health_probe(
    server_url: str,
    *,
    ca_bundle: str | Path | None = None,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    base = str(server_url or "").rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme.lower() != "https":
        raise ValueError("physical certification requires an HTTPS server URL")
    context = _ssl_context(ca_bundle)
    endpoints: dict[str, Any] = {}
    all_ok = True
    for name, path in (("live", "/api/v1/health/live"), ("ready", "/api/v1/health/ready")):
        started = perf_counter()
        try:
            request = Request(base + path, method="GET", headers={"Accept": "application/json"})
            with urlopen(request, timeout=float(timeout_seconds), context=context) as response:
                raw = response.read(1024 * 1024)
                status = int(response.status)
            payload = json.loads(raw.decode("utf-8"))
            ok = status == 200 and isinstance(payload, dict) and bool(payload.get("ok"))
            endpoints[name] = {
                "ok": ok,
                "status": status,
                "latency_ms": round((perf_counter() - started) * 1000.0, 3),
                "payload": payload,
            }
        except Exception as exc:
            endpoints[name] = {
                "ok": False,
                "status": 0,
                "latency_ms": round((perf_counter() - started) * 1000.0, 3),
                "error": {"type": type(exc).__name__, "message": str(exc)},
            }
        all_ok = all_ok and bool(endpoints[name]["ok"])
    return {"ok": all_ok, "server_url": base, "endpoints": endpoints}


def tls_certificate_probe(
    server_url: str,
    *,
    ca_bundle: str | Path | None = None,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    parsed = urlsplit(str(server_url or ""))
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("an HTTPS URL with a hostname is required")
    port = int(parsed.port or 443)
    context = _ssl_context(ca_bundle)
    with socket.create_connection((parsed.hostname, port), timeout=float(timeout_seconds)) as connection:
        with context.wrap_socket(connection, server_hostname=parsed.hostname) as secure:
            certificate_binary = secure.getpeercert(binary_form=True)
            certificate = secure.getpeercert()
            cipher = secure.cipher()
            protocol = secure.version()
    not_after_text = str(certificate.get("notAfter") or "")
    expires_at: str | None = None
    days_remaining: float | None = None
    if not_after_text:
        expires = datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after_text), timezone.utc)
        expires_at = expires.isoformat().replace("+00:00", "Z")
        days_remaining = round((expires - datetime.now(timezone.utc)).total_seconds() / 86400.0, 3)
    protocol_ok = protocol in {"TLSv1.2", "TLSv1.3"}
    return {
        "ok": bool(certificate_binary) and protocol_ok and (days_remaining is None or days_remaining > 0),
        "hostname": parsed.hostname,
        "port": port,
        "protocol": protocol,
        "protocol_ok": protocol_ok,
        "cipher": cipher[0] if cipher else None,
        "certificate_sha256": hashlib.sha256(certificate_binary).hexdigest(),
        "subject": certificate.get("subject"),
        "issuer": certificate.get("issuer"),
        "serial_number": certificate.get("serialNumber"),
        "expires_at": expires_at,
        "days_remaining": days_remaining,
    }


def service_probe(*, platform_name: str, service_name: str) -> dict[str, Any]:
    platform_value = str(platform_name).lower().strip()
    service = str(service_name or "").strip()
    if not service:
        raise ValueError("service_name is required")
    if platform_value == "windows":
        command = ["schtasks.exe", "/Query", "/TN", service, "/FO", "LIST", "/V"]
    elif platform_value == "ubuntu":
        command = ["systemctl", "is-active", service]
    else:
        raise ValueError("service probe supports windows or ubuntu")
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    if platform_value == "windows":
        lowered = stdout.lower()
        ok = completed.returncode == 0 and ("ready" in lowered or "running" in lowered)
    else:
        ok = completed.returncode == 0 and stdout.lower() == "active"
    return {
        "ok": bool(ok),
        "platform": platform_value,
        "service_name": service,
        "return_code": int(completed.returncode),
        "stdout": stdout[-8000:],
        "stderr": stderr[-8000:],
    }


def run_https_soak(
    server_url: str,
    *,
    duration_seconds: float,
    interval_seconds: float = 30.0,
    ca_bundle: str | Path | None = None,
    timeout_seconds: float = 15.0,
) -> dict[str, Any]:
    duration = float(duration_seconds)
    interval = float(interval_seconds)
    if duration <= 0 or duration > 7 * 24 * 60 * 60:
        raise ValueError("duration_seconds must be greater than zero and no more than seven days")
    if interval < 0.05 or interval > 3600:
        raise ValueError("interval_seconds must be between 0.05 and 3600")
    started_at = _utc_now()
    deadline = monotonic() + duration
    checks = 0
    failures: list[dict[str, Any]] = []
    latencies: list[float] = []
    while True:
        probe_started = perf_counter()
        result = https_health_probe(
            server_url,
            ca_bundle=ca_bundle,
            timeout_seconds=timeout_seconds,
        )
        latency = (perf_counter() - probe_started) * 1000.0
        checks += 1
        latencies.append(latency)
        if not result["ok"]:
            failures.append({"check": checks, "captured_at": _utc_now(), "result": result})
        remaining = deadline - monotonic()
        if remaining <= 0:
            break
        sleep(min(interval, remaining))
    return {
        "ok": not failures,
        "server_url": str(server_url).rstrip("/"),
        "started_at": started_at,
        "finished_at": _utc_now(),
        "duration_seconds": round(duration, 3),
        "interval_seconds": round(interval, 3),
        "checks": checks,
        "failures": len(failures),
        "failure_examples": failures[:20],
        "latency_ms": {
            "min": round(min(latencies), 3) if latencies else 0.0,
            "mean": round(mean(latencies), 3) if latencies else 0.0,
            "p95": _percentile(latencies, 95),
            "p99": _percentile(latencies, 99),
            "max": round(max(latencies), 3) if latencies else 0.0,
        },
    }
