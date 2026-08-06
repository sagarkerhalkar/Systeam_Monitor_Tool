from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
import json
import math
import os
import platform
import shutil
import socket
import subprocess
import time


def _finite(value: object, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return default
    return number if math.isfinite(number) else default


def _non_negative_int(value: object) -> int:
    try:
        return max(0, int(float(value or 0)))
    except (TypeError, ValueError, OverflowError):
        return 0


def _run_json(command: list[str], timeout: float = 12.0) -> Any:
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return None
    try:
        return json.loads(completed.stdout)
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


class SystemCollector:
    """Dependency-free Windows and Linux collector.

    It reports OS cumulative network counters. The runtime converts them to a
    persistent local-day counter before queuing a heartbeat.
    """

    def __init__(self, *, clock=time.monotonic) -> None:
        self.clock = clock
        self._previous_network: tuple[float, int, int] | None = None
        self._previous_linux_cpu: tuple[int, int] | None = None

    @staticmethod
    def platform_name() -> str:
        return "windows" if os.name == "nt" else "linux"

    def sample(self) -> dict[str, Any]:
        hostname = socket.gethostname().strip()[:255]
        cpu = self._cpu()
        memory = self._memory()
        download_total, upload_total, interfaces = self._network()
        now_tick = float(self.clock())
        down_mbps = 0.0
        up_mbps = 0.0
        if self._previous_network is not None:
            previous_tick, previous_down, previous_up = self._previous_network
            elapsed = max(0.001, now_tick - previous_tick)
            if download_total >= previous_down:
                down_mbps = (download_total - previous_down) * 8.0 / elapsed / 1_000_000.0
            if upload_total >= previous_up:
                up_mbps = (upload_total - previous_up) * 8.0 / elapsed / 1_000_000.0
        self._previous_network = (now_tick, download_total, upload_total)
        return {
            "hostname": hostname,
            "identity": {
                "hostname": hostname,
                "platform": self.platform_name(),
                "os_name": platform.system(),
                "os_version": platform.version(),
                "machine": platform.machine(),
            },
            "hardware": {
                "cpu": cpu,
                "memory": memory,
                "storage": {"volumes": self._volumes()},
            },
            "network": {
                "interfaces": interfaces,
                "traffic": {
                    "raw_download_total_bytes": download_total,
                    "raw_upload_total_bytes": upload_total,
                    "current_download_mbps": round(max(0.0, down_mbps), 6),
                    "current_upload_mbps": round(max(0.0, up_mbps), 6),
                },
            },
            "agent": {
                "collector": "stdlib-v1",
                "collected_at": datetime.now(timezone.utc).isoformat(),
            },
        }

    def _cpu(self) -> dict[str, Any]:
        usage = self._windows_cpu() if os.name == "nt" else self._linux_cpu()
        return {
            "usage_percent": round(min(100.0, max(0.0, usage)), 4),
            "logical_cores": int(os.cpu_count() or 1),
            "model": platform.processor() or "",
        }

    def _linux_cpu(self) -> float:
        try:
            fields = Path("/proc/stat").read_text(encoding="utf-8", errors="replace").splitlines()[0].split()[1:]
            values = [_non_negative_int(value) for value in fields]
            idle = values[3] + (values[4] if len(values) > 4 else 0)
            total = sum(values)
        except (OSError, IndexError, ValueError):
            return 0.0
        current = (total, idle)
        if self._previous_linux_cpu is None:
            self._previous_linux_cpu = current
            return 0.0
        previous_total, previous_idle = self._previous_linux_cpu
        self._previous_linux_cpu = current
        delta_total = max(0, total - previous_total)
        delta_idle = max(0, idle - previous_idle)
        if delta_total <= 0:
            return 0.0
        return (1.0 - min(1.0, delta_idle / delta_total)) * 100.0

    @staticmethod
    def _windows_cpu() -> float:
        script = (
            "$v=(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average;"
            "if($null -eq $v){$v=0}; $v | ConvertTo-Json -Compress"
        )
        value = _run_json(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script])
        return _finite(value)

    def _memory(self) -> dict[str, Any]:
        if os.name == "nt":
            return self._windows_memory()
        return self._linux_memory()

    @staticmethod
    def _linux_memory() -> dict[str, Any]:
        values: dict[str, int] = {}
        try:
            for line in Path("/proc/meminfo").read_text(encoding="utf-8", errors="replace").splitlines():
                name, raw = line.split(":", 1)
                values[name] = _non_negative_int(raw.strip().split()[0]) * 1024
        except (OSError, ValueError, IndexError):
            pass
        total = values.get("MemTotal", 0)
        available = values.get("MemAvailable", values.get("MemFree", 0))
        used = max(0, total - available)
        percent = used * 100.0 / total if total else 0.0
        return {
            "total_bytes": total,
            "available_bytes": available,
            "used_bytes": used,
            "used_percent": round(percent, 4),
        }

    @staticmethod
    def _windows_memory() -> dict[str, Any]:
        script = (
            "$m=Get-CimInstance Win32_OperatingSystem;"
            "@{total=[int64]$m.TotalVisibleMemorySize*1024;free=[int64]$m.FreePhysicalMemory*1024}"
            "| ConvertTo-Json -Compress"
        )
        value = _run_json(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script])
        value = value if isinstance(value, dict) else {}
        total = _non_negative_int(value.get("total"))
        available = _non_negative_int(value.get("free"))
        used = max(0, total - available)
        return {
            "total_bytes": total,
            "available_bytes": available,
            "used_bytes": used,
            "used_percent": round(used * 100.0 / total, 4) if total else 0.0,
        }

    def _network(self) -> tuple[int, int, list[dict[str, Any]]]:
        if os.name == "nt":
            return self._windows_network()
        return self._linux_network()

    @staticmethod
    def _linux_network() -> tuple[int, int, list[dict[str, Any]]]:
        received = 0
        sent = 0
        interfaces: list[dict[str, Any]] = []
        try:
            lines = Path("/proc/net/dev").read_text(encoding="utf-8", errors="replace").splitlines()[2:]
        except OSError:
            lines = []
        for line in lines:
            try:
                name, raw = line.split(":", 1)
                fields = raw.split()
                rx = _non_negative_int(fields[0])
                tx = _non_negative_int(fields[8])
            except (ValueError, IndexError):
                continue
            clean_name = name.strip()
            if clean_name == "lo":
                continue
            received += rx
            sent += tx
            interfaces.append({"name": clean_name, "received_bytes": rx, "sent_bytes": tx})
        return received, sent, interfaces

    @staticmethod
    def _windows_network() -> tuple[int, int, list[dict[str, Any]]]:
        script = (
            "$a=Get-NetAdapterStatistics -ErrorAction SilentlyContinue | "
            "Select-Object Name,ReceivedBytes,SentBytes; @($a) | ConvertTo-Json -Compress"
        )
        value = _run_json(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script])
        if isinstance(value, dict):
            rows = [value]
        elif isinstance(value, list):
            rows = [row for row in value if isinstance(row, dict)]
        else:
            rows = []
        interfaces: list[dict[str, Any]] = []
        received = 0
        sent = 0
        for row in rows:
            rx = _non_negative_int(row.get("ReceivedBytes"))
            tx = _non_negative_int(row.get("SentBytes"))
            received += rx
            sent += tx
            interfaces.append({"name": str(row.get("Name") or ""), "received_bytes": rx, "sent_bytes": tx})
        return received, sent, interfaces

    @staticmethod
    def _volumes() -> list[dict[str, Any]]:
        candidates: list[str]
        if os.name == "nt":
            candidates = [f"{letter}:\\" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{letter}:\\").exists()]
        else:
            candidates = ["/"]
            for base in (Path("/mnt"), Path("/media")):
                if base.exists():
                    candidates.extend(str(child) for child in base.iterdir() if child.is_dir())
        volumes: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate in candidates:
            try:
                usage = shutil.disk_usage(candidate)
            except OSError:
                continue
            key = os.path.realpath(candidate)
            if key in seen:
                continue
            seen.add(key)
            volumes.append(
                {
                    "mount": candidate,
                    "total_bytes": int(usage.total),
                    "used_bytes": int(usage.used),
                    "free_bytes": int(usage.free),
                    "used_percent": round(usage.used * 100.0 / usage.total, 4) if usage.total else 0.0,
                }
            )
        return volumes
