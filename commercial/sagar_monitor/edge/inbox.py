from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time


DELIVERY_RE = re.compile(r"^[A-Za-z0-9-]{8,128}$")


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(dict(value), handle, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            temporary.chmod(0o660)
        os.replace(temporary, path)
        if os.name != "nt":
            path.chmod(0o660)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def _content_hash(message: Mapping[str, Any]) -> str:
    raw = json.dumps(
        {
            "message_id": message.get("message_id"),
            "title": message.get("title"),
            "body": message.get("body"),
            "severity": message.get("severity"),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class LocalInbox:
    """Filesystem handoff between the system agent and user-session notifier."""

    def __init__(self, directory: str | Path) -> None:
        self.directory = Path(directory).expanduser().resolve()
        self.pending = self.directory / "pending"
        self.displayed = self.directory / "displayed"
        self.pending.mkdir(parents=True, exist_ok=True)
        self.displayed.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            # The installer assigns these setgid directories to a dedicated
            # notifier group. Credentials and queue data remain outside them.
            self.directory.chmod(0o770)
            self.pending.chmod(0o770)
            self.displayed.chmod(0o770)

    @staticmethod
    def _delivery_id(message: Mapping[str, Any]) -> str:
        delivery_id = str(message.get("delivery_id") or "").strip()
        if not DELIVERY_RE.fullmatch(delivery_id):
            raise ValueError("invalid message delivery_id")
        return delivery_id

    def stage(self, message: Mapping[str, Any]) -> bool:
        delivery_id = self._delivery_id(message)
        document = dict(message)
        document["content_hash"] = _content_hash(message)
        document["staged_at"] = _iso_now()
        target = self.pending / f"{delivery_id}.json"
        if target.exists():
            try:
                current = json.loads(target.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                current = {}
            if isinstance(current, dict) and current.get("content_hash") != document["content_hash"]:
                raise ValueError("delivery_id was reused with different message content")
            # A renewed server lease may supply a new dispatch token. Replace
            # the pending document atomically without redisplaying it twice.
            _atomic_json(target, document)
            return False
        _atomic_json(target, document)
        return True

    def pending_messages(self, limit: int = 20) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for path in sorted(self.pending.glob("*.json"), key=lambda item: item.stat().st_mtime)[: max(1, limit)]:
            marker = self.displayed / path.name
            if marker.exists():
                continue
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            if isinstance(value, dict):
                result.append(value)
        return result

    def mark_displayed(self, delivery_id: str, detail: Mapping[str, Any] | None = None) -> None:
        if not DELIVERY_RE.fullmatch(str(delivery_id or "")):
            raise ValueError("invalid delivery_id")
        pending = self.pending / f"{delivery_id}.json"
        if not pending.exists():
            raise FileNotFoundError("pending message no longer exists")
        _atomic_json(
            self.displayed / f"{delivery_id}.json",
            {"displayed_at": _iso_now(), "detail": dict(detail or {})},
        )

    def displayed_messages(self, limit: int = 100) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        result: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for marker in sorted(self.displayed.glob("*.json"), key=lambda item: item.stat().st_mtime)[: max(1, limit)]:
            pending = self.pending / marker.name
            if not pending.exists():
                try:
                    marker.unlink()
                except OSError:
                    pass
                continue
            try:
                message = json.loads(pending.read_text(encoding="utf-8"))
                display = json.loads(marker.read_text(encoding="utf-8"))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                continue
            if isinstance(message, dict) and isinstance(display, dict):
                result.append((message, display))
        return result

    def complete(self, delivery_id: str) -> None:
        if not DELIVERY_RE.fullmatch(str(delivery_id or "")):
            raise ValueError("invalid delivery_id")
        for directory in (self.pending, self.displayed):
            try:
                (directory / f"{delivery_id}.json").unlink(missing_ok=True)
            except OSError:
                pass


class UserNotifier:
    """Display staged messages from an interactive user session."""

    def __init__(
        self,
        inbox: LocalInbox,
        *,
        command_runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ) -> None:
        self.inbox = inbox
        self.command_runner = command_runner

    def display_once(self, limit: int = 10) -> int:
        displayed = 0
        for message in self.inbox.pending_messages(limit=limit):
            delivery_id = str(message.get("delivery_id") or "")
            title = str(message.get("title") or "System message")[:200]
            body = str(message.get("body") or "")[:4000]
            severity = str(message.get("severity") or "info")[:30]
            command = self._command(title, body)
            try:
                result = self.command_runner(
                    command,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=135,
                    check=False,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if int(result.returncode) != 0:
                continue
            self.inbox.mark_displayed(
                delivery_id,
                {"notifier": "windows-msg" if os.name == "nt" else "notify-send", "severity": severity},
            )
            displayed += 1
        return displayed

    @staticmethod
    def _command(title: str, body: str) -> list[str]:
        if os.name == "nt":
            # The notifier task runs as SYSTEM at user logon. msg.exe targets
            # the interactive session and automatically closes at 120 seconds.
            safe = f"{title}\n\n{body}".replace("\x00", "")
            return ["msg.exe", "*", "/TIME:120", safe]
        return ["notify-send", "--expire-time=120000", "--app-name=Sagar Monitor", title, body]

    def run_forever(self, poll_seconds: float = 5.0) -> None:
        interval = min(300.0, max(1.0, float(poll_seconds)))
        while True:
            self.display_once()
            time.sleep(interval)
