from __future__ import annotations

import os
import uuid
from pathlib import Path

WINDOWS_AGENT_ID_PATH = Path(r"C:\ProgramData\SagarSystemMonitor\agent_install_id.txt")
UBUNTU_AGENT_ID_PATH = Path("/var/lib/commercial-monitor-pro/agent_install_id")


def normalize_agent_install_id(value: object) -> str:
    try:
        return str(uuid.UUID(str(value or "").strip()))
    except (ValueError, AttributeError, TypeError):
        return ""


def load_or_create_agent_install_id(path: str | os.PathLike[str]) -> str:
    """Return a permanent UUID stored with restrictive file permissions.

    A valid existing identifier is never replaced. An absent or invalid file is
    replaced atomically so agent restarts and hostname changes keep one identity.
    """
    target = Path(path)
    try:
        current = normalize_agent_install_id(target.read_text(encoding="utf-8"))
    except OSError:
        current = ""
    if current:
        return current

    target.parent.mkdir(parents=True, exist_ok=True)
    value = str(uuid.uuid4())
    temporary = target.with_name(f".{target.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(value + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temporary, 0o600)
        except OSError:
            pass
        os.replace(temporary, target)
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass

    stored = normalize_agent_install_id(target.read_text(encoding="utf-8"))
    if not stored:
        raise RuntimeError(f"agent installation ID could not be persisted at {target}")
    return stored
