from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse
import json
import os
import sys
import time

from .inbox import LocalInbox, UserNotifier
from .runtime import AgentRuntime, RuntimeConfig
from .transport import HTTPAgentTransport


def _load_config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise RuntimeError(f"cannot read configuration: {exc}") from exc
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("configuration is not valid JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("configuration must be a JSON object")
    return value


def _state_directory(config: dict[str, Any]) -> Path:
    value = str(config.get("state_directory") or "").strip()
    if not value:
        raise RuntimeError("state_directory is required")
    return Path(os.path.expandvars(value)).expanduser().resolve()


def _token_file(config: dict[str, Any]) -> Path | None:
    value = str(config.get("enrollment_token_file") or "").strip()
    return Path(os.path.expandvars(value)).expanduser().resolve() if value else None


def _read_enrollment_token(config: dict[str, Any]) -> str:
    path = _token_file(config)
    if path is None or not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


def _remove_enrollment_token(config: dict[str, Any]) -> None:
    path = _token_file(config)
    if path is None or not path.exists():
        return
    try:
        size = path.stat().st_size
        with path.open("r+b") as handle:
            handle.write(b"\x00" * min(size, 1024 * 1024))
            handle.flush()
            os.fsync(handle.fileno())
        path.unlink(missing_ok=True)
    except OSError:
        # Registration has already succeeded and the long-lived credential is
        # stored. The operator can remove the token file manually if the
        # filesystem refuses deletion; never print its contents.
        pass


def build_runtime(config: dict[str, Any]) -> AgentRuntime:
    server_url = str(config.get("server_url") or "").strip()
    if not server_url:
        raise RuntimeError("server_url is required")
    state_directory = _state_directory(config)
    transport = HTTPAgentTransport(
        server_url,
        timeout_seconds=float(config.get("timeout_seconds") or 20),
        ca_bundle=str(config.get("ca_bundle") or ""),
        allow_loopback_http=bool(config.get("allow_loopback_http") or False),
    )
    runtime_config = RuntimeConfig(
        state_directory=state_directory,
        timezone_name=str(config.get("timezone_name") or "Asia/Kolkata"),
        heartbeat_interval_seconds=int(config.get("heartbeat_interval_seconds") or 60),
        max_heartbeats_per_cycle=int(config.get("max_heartbeats_per_cycle") or 20),
        max_receipts_per_cycle=int(config.get("max_receipts_per_cycle") or 50),
        queue_limit=int(config.get("queue_limit") or 10000),
        registration_metadata=config.get("registration_metadata")
        if isinstance(config.get("registration_metadata"), dict)
        else {},
    )
    return AgentRuntime(runtime_config, transport)


def _result_document(result) -> dict[str, Any]:
    return {
        "registered": result.registered,
        "credential_available": result.credential_available,
        "sample_enqueued": result.sample_enqueued,
        "heartbeats_sent": result.heartbeats_sent,
        "receipts_sent": result.receipts_sent,
        "messages_staged": result.messages_staged,
        "authentication_error": result.authentication_error,
        "queue_counts": result.queue_counts,
        "errors": list(result.errors),
    }


def _print_result(result) -> None:
    print(json.dumps(_result_document(result), ensure_ascii=False, sort_keys=True), flush=True)


def command_once(runtime: AgentRuntime, config: dict[str, Any]) -> int:
    result = runtime.run_cycle(enrollment_token=_read_enrollment_token(config))
    if result.registered:
        _remove_enrollment_token(config)
    _print_result(result)
    return 0 if result.credential_available and not result.authentication_error else 2


def command_service(runtime: AgentRuntime, config: dict[str, Any]) -> int:
    while True:
        result = runtime.run_cycle(enrollment_token=_read_enrollment_token(config))
        if result.registered:
            _remove_enrollment_token(config)
        _print_result(result)
        delay = runtime.config.heartbeat_interval_seconds
        if result.authentication_error:
            delay = max(300, delay)
        time.sleep(delay)


def command_notifier(config: dict[str, Any]) -> int:
    inbox = LocalInbox(_state_directory(config) / "messages")
    notifier = UserNotifier(inbox)
    notifier.run_forever(poll_seconds=float(config.get("notifier_poll_seconds") or 5))
    return 0


def command_status(runtime: AgentRuntime) -> int:
    credential = runtime.credentials.load_credential()
    if credential is None:
        print(json.dumps({"ok": False, "error": "agent is not registered"}), flush=True)
        return 2
    result = runtime.transport.status(credential.agent_install_id, credential.agent_token)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


def command_rotate(runtime: AgentRuntime, reason: str) -> int:
    credential = runtime.rotate_token(reason)
    print(
        json.dumps(
            {
                "ok": True,
                "agent_install_id": credential.agent_install_id,
                "token_version": credential.token_version,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Sagar Monitor commercial edge agent")
    result.add_argument("--config", required=True, help="Path to agent JSON configuration")
    subcommands = result.add_subparsers(dest="command", required=True)
    subcommands.add_parser("once", help="Collect and flush one cycle")
    subcommands.add_parser("service", help="Run the system-agent loop")
    subcommands.add_parser("notifier", help="Run the interactive message notifier")
    subcommands.add_parser("status", help="Read authenticated agent status")
    rotate = subcommands.add_parser("rotate-token", help="Rotate the stored agent credential")
    rotate.add_argument("--reason", default="operator requested rotation")
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        config = _load_config(Path(arguments.config).expanduser().resolve())
        if arguments.command == "notifier":
            return command_notifier(config)
        runtime = build_runtime(config)
        if arguments.command == "once":
            return command_once(runtime, config)
        if arguments.command == "service":
            return command_service(runtime, config)
        if arguments.command == "status":
            return command_status(runtime)
        if arguments.command == "rotate-token":
            return command_rotate(runtime, arguments.reason)
        raise RuntimeError("unsupported command")
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
