from __future__ import annotations

from pathlib import Path
from typing import Any
import argparse
import json
import platform
import sys

from .evidence import (
    finalize_evidence,
    initialize_evidence,
    record_machine_snapshot,
    record_step,
    verify_evidence,
)
from .plan import certification_plan_document
from .probes import (
    disk_capacity_probe,
    https_health_probe,
    machine_snapshot,
    run_https_soak,
    service_probe,
    sqlite_probe,
    tls_certificate_probe,
)


def _json_value(value: str) -> dict[str, Any]:
    text = str(value or "").strip()
    if not text:
        return {}
    candidate = Path(text).expanduser()
    try:
        if candidate.is_file():
            parsed = json.loads(candidate.read_text(encoding="utf-8-sig"))
        else:
            parsed = json.loads(text)
    except (OSError, json.JSONDecodeError) as exc:
        raise argparse.ArgumentTypeError("metrics must be a JSON object or JSON file") from exc
    if not isinstance(parsed, dict):
        raise argparse.ArgumentTypeError("metrics must be a JSON object")
    return parsed


def _platform(value: str | None = None) -> str:
    if value:
        result = str(value).lower().strip()
    else:
        system = platform.system().lower()
        result = "windows" if system == "windows" else "ubuntu" if system == "linux" else "cross-platform"
    if result not in {"windows", "ubuntu", "cross-platform"}:
        raise ValueError("platform must be windows, ubuntu or cross-platform")
    return result


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Sagar Monitor physical staging certification")
    commands = root.add_subparsers(dest="command", required=True)

    commands.add_parser("plan", help="Print the fixed physical certification plan")

    init = commands.add_parser("init", help="Create a new certification evidence ledger")
    init.add_argument("--evidence", required=True)
    init.add_argument("--release-candidate", required=True)
    init.add_argument("--site", required=True)
    init.add_argument("--operator", required=True)
    init.add_argument("--metadata", type=_json_value, default={})

    snapshot = commands.add_parser("snapshot", help="Record the current physical machine snapshot")
    snapshot.add_argument("--evidence", required=True)
    snapshot.add_argument("--operator", required=True)
    snapshot.add_argument("--platform", choices=("windows", "ubuntu", "cross-platform"))
    snapshot.add_argument("--path", default=".")

    record = commands.add_parser("record", help="Record a manual or guided certification step")
    record.add_argument("--evidence", required=True)
    record.add_argument("--step-id", required=True)
    record.add_argument("--status", choices=("PASS", "FAIL"), required=True)
    record.add_argument("--platform", choices=("windows", "ubuntu", "cross-platform"), required=True)
    record.add_argument("--operator", required=True)
    record.add_argument("--notes", default="")
    record.add_argument("--duration-seconds", type=float, default=0.0)
    record.add_argument("--metrics", type=_json_value, default={})
    record.add_argument("--attachment", action="append", default=[])

    probe = commands.add_parser("probe-server", help="Run physical server health and integrity probes")
    probe.add_argument("--evidence", required=True)
    probe.add_argument("--step-id", required=True)
    probe.add_argument("--platform", choices=("windows", "ubuntu", "cross-platform"), required=True)
    probe.add_argument("--operator", required=True)
    probe.add_argument("--server-url", required=True)
    probe.add_argument("--ca-bundle")
    probe.add_argument("--database")
    probe.add_argument("--service-name")
    probe.add_argument("--disk-path", default=".")
    probe.add_argument("--minimum-free-gb", type=float, default=5.0)
    probe.add_argument("--notes", default="Automated physical server probe")
    probe.add_argument("--attachment", action="append", default=[])

    soak = commands.add_parser("soak", help="Run a real HTTPS soak and record its evidence")
    soak.add_argument("--evidence", required=True)
    soak.add_argument("--step-id", choices=("soak_8_hours", "soak_24_hours", "controlled_pilot"), required=True)
    soak.add_argument("--platform", choices=("windows", "ubuntu", "cross-platform"), default="cross-platform")
    soak.add_argument("--operator", required=True)
    soak.add_argument("--server-url", required=True)
    soak.add_argument("--ca-bundle")
    soak.add_argument("--duration-hours", type=float, required=True)
    soak.add_argument("--interval-seconds", type=float, default=30.0)
    soak.add_argument("--notes", default="Automated HTTPS soak completed")
    soak.add_argument("--attachment", action="append", default=[])

    verify = commands.add_parser("verify", help="Verify hashes, attachments and required step status")
    verify.add_argument("--evidence", required=True)
    verify.add_argument("--require-complete", action="store_true")

    finalize = commands.add_parser("finalize", help="Certify a fully passing release ledger")
    finalize.add_argument("--evidence", required=True)
    finalize.add_argument("--approver", required=True)
    finalize.add_argument("--notes", default="")

    return root


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def _probe_server(arguments: argparse.Namespace) -> int:
    metrics: dict[str, Any] = {
        "machine": machine_snapshot(arguments.disk_path),
        "disk": disk_capacity_probe(
            arguments.disk_path,
            minimum_free_bytes=max(0, int(float(arguments.minimum_free_gb) * 1024 * 1024 * 1024)),
        ),
        "https": https_health_probe(arguments.server_url, ca_bundle=arguments.ca_bundle),
        "tls": tls_certificate_probe(arguments.server_url, ca_bundle=arguments.ca_bundle),
    }
    if arguments.database:
        metrics["database"] = sqlite_probe(arguments.database)
    if arguments.service_name:
        metrics["service"] = service_probe(
            platform_name=arguments.platform,
            service_name=arguments.service_name,
        )
    checks = [value for value in metrics.values() if isinstance(value, dict) and "ok" in value]
    status = "PASS" if checks and all(bool(value["ok"]) for value in checks) else "FAIL"
    event = record_step(
        arguments.evidence,
        step_id=arguments.step_id,
        status=status,
        platform_name=arguments.platform,
        operator=arguments.operator,
        notes=arguments.notes,
        metrics=metrics,
        attachments=arguments.attachment,
    )
    _print(event)
    return 0 if status == "PASS" else 2


def _soak(arguments: argparse.Namespace) -> int:
    duration_seconds = float(arguments.duration_hours) * 60 * 60
    result = run_https_soak(
        arguments.server_url,
        duration_seconds=duration_seconds,
        interval_seconds=arguments.interval_seconds,
        ca_bundle=arguments.ca_bundle,
    )
    evidence_path = Path(arguments.evidence).expanduser().resolve()
    generated = evidence_path.parent / f"{evidence_path.stem}-{arguments.step_id}-probe.json"
    generated.write_text(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    attachments = [str(generated), *arguments.attachment]
    event = record_step(
        arguments.evidence,
        step_id=arguments.step_id,
        status="PASS" if result["ok"] else "FAIL",
        platform_name=arguments.platform,
        operator=arguments.operator,
        notes=arguments.notes,
        duration_seconds=duration_seconds,
        metrics=result,
        attachments=attachments,
    )
    generated.unlink(missing_ok=True)
    _print(event)
    return 0 if result["ok"] else 2


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "plan":
            _print(certification_plan_document())
            return 0
        if arguments.command == "init":
            path = initialize_evidence(
                arguments.evidence,
                release_candidate=arguments.release_candidate,
                site=arguments.site,
                operator=arguments.operator,
                metadata=arguments.metadata,
            )
            _print({"ok": True, "evidence": str(path)})
            return 0
        if arguments.command == "snapshot":
            event = record_machine_snapshot(
                arguments.evidence,
                platform_name=_platform(arguments.platform),
                operator=arguments.operator,
                snapshot=machine_snapshot(arguments.path),
            )
            _print(event)
            return 0
        if arguments.command == "record":
            event = record_step(
                arguments.evidence,
                step_id=arguments.step_id,
                status=arguments.status,
                platform_name=arguments.platform,
                operator=arguments.operator,
                notes=arguments.notes,
                duration_seconds=arguments.duration_seconds,
                metrics=arguments.metrics,
                attachments=arguments.attachment,
            )
            _print(event)
            return 0 if arguments.status == "PASS" else 2
        if arguments.command == "probe-server":
            return _probe_server(arguments)
        if arguments.command == "soak":
            return _soak(arguments)
        if arguments.command == "verify":
            result = verify_evidence(arguments.evidence, require_complete=arguments.require_complete)
            _print(result)
            return 0 if result["ok"] else 2
        if arguments.command == "finalize":
            result = finalize_evidence(
                arguments.evidence,
                approver=arguments.approver,
                notes=arguments.notes,
            )
            _print(result)
            return 0 if result["ok"] else 2
        raise RuntimeError(f"unsupported command: {arguments.command}")
    except Exception as exc:
        _print({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
