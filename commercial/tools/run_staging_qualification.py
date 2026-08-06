#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import shutil
import traceback

from sagar_monitor.qualification import (
    QualificationConfig,
    QualificationThresholds,
    run_qualification_scenario,
    write_evidence,
)


def _agent_counts(value: str) -> list[int]:
    result: list[int] = []
    for item in value.split(","):
        try:
            count = int(item.strip())
        except ValueError as exc:
            raise argparse.ArgumentTypeError("agents must be comma-separated integers") from exc
        if not 1 <= count <= 10000:
            raise argparse.ArgumentTypeError("each agent count must be between 1 and 10000")
        if count not in result:
            result.append(count)
    if not result:
        raise argparse.ArgumentTypeError("at least one agent count is required")
    return result


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Run commercial staging and performance qualification")
    result.add_argument("--agents", type=_agent_counts, default=[100, 500, 1000])
    result.add_argument("--concurrency", type=int, default=16)
    result.add_argument("--heartbeat-rounds", type=int, default=2)
    result.add_argument("--duplicate-replay-count", type=int, default=25)
    result.add_argument("--message-target-count", type=int, default=10)
    result.add_argument("--admin-request-count", type=int, default=100)
    result.add_argument("--workspace", default="qualification-work")
    result.add_argument("--output-dir", default="qualification-evidence")
    result.add_argument("--keep-workspace", action="store_true")
    result.add_argument("--max-registration-p95-ms", type=float, default=5000.0)
    result.add_argument("--max-heartbeat-p95-ms", type=float, default=2000.0)
    result.add_argument("--max-admin-p95-ms", type=float, default=500.0)
    result.add_argument("--max-wal-mb", type=float, default=512.0)
    result.add_argument("--max-memory-mb", type=float, default=512.0)
    return result


def _failure_report(count: int, config: QualificationConfig, exc: BaseException) -> dict:
    return {
        "schema": "sagar-monitor-qualification-v1",
        "scenario": {
            "agent_count": count,
            "concurrency": config.concurrency,
            "heartbeat_rounds": config.heartbeat_rounds,
            "duplicate_replay_count": config.duplicate_replay_count,
            "message_target_count": config.message_target_count,
            "admin_request_count": config.admin_request_count,
        },
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "passed": False,
        "fatal_error": {
            "type": type(exc).__name__,
            "message": str(exc),
            "traceback": traceback.format_exc(limit=20),
        },
    }


def _summary_row(report: dict) -> dict:
    operations = report.get("operations") or {}
    totals = report.get("totals") or {}
    database = report.get("database") or {}

    def p95(name: str) -> float | None:
        try:
            return float(operations[name]["latency_ms"]["p95"])
        except (KeyError, TypeError, ValueError):
            return None

    return {
        "agent_count": int(report.get("scenario", {}).get("agent_count", 0)),
        "passed": bool(report.get("passed")),
        "duration_seconds": report.get("duration_seconds"),
        "total_operations": totals.get("operations", 0),
        "failures": totals.get("failures", 1 if report.get("fatal_error") else 0),
        "registration_p95_ms": p95("registration"),
        "heartbeat_p95_ms": p95("heartbeat"),
        "admin_p95_ms": p95("admin"),
        "database_bytes": database.get("database_bytes"),
        "wal_bytes": database.get("wal_bytes"),
        "evidence_sha256": report.get("evidence_sha256"),
        "fatal_error": report.get("fatal_error"),
    }


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    workspace = Path(arguments.workspace).expanduser().resolve()
    output = Path(arguments.output_dir).expanduser().resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)

    thresholds = QualificationThresholds(
        max_error_rate=0.0,
        max_registration_p95_ms=float(arguments.max_registration_p95_ms),
        max_heartbeat_p95_ms=float(arguments.max_heartbeat_p95_ms),
        max_admin_p95_ms=float(arguments.max_admin_p95_ms),
        max_wal_bytes=int(float(arguments.max_wal_mb) * 1024 * 1024),
        max_peak_traced_memory_bytes=int(float(arguments.max_memory_mb) * 1024 * 1024),
    )

    reports: list[dict] = []
    try:
        for count in arguments.agents:
            scenario_root = workspace / f"agents-{count}"
            shutil.rmtree(scenario_root, ignore_errors=True)
            scenario_root.mkdir(parents=True)
            config = QualificationConfig(
                agent_count=count,
                concurrency=int(arguments.concurrency),
                heartbeat_rounds=int(arguments.heartbeat_rounds),
                duplicate_replay_count=int(arguments.duplicate_replay_count),
                message_target_count=int(arguments.message_target_count),
                admin_request_count=int(arguments.admin_request_count),
                thresholds=thresholds,
            )
            try:
                report = run_qualification_scenario(scenario_root / "commercial.db", config)
            except BaseException as exc:  # evidence must survive every scenario failure
                report = _failure_report(count, config, exc)
            evidence_path = write_evidence(output / f"qualification-{count}-agents.json", report)
            stored = json.loads(evidence_path.read_text(encoding="utf-8"))
            reports.append(stored)
            row = _summary_row(stored)
            row["evidence"] = str(evidence_path)
            print(json.dumps(row, ensure_ascii=False, sort_keys=True), flush=True)

        summary = {
            "schema": "sagar-monitor-qualification-summary-v1",
            "passed": all(bool(report.get("passed")) for report in reports),
            "scenario_count": len(reports),
            "agent_counts": [int(report.get("scenario", {}).get("agent_count", 0)) for report in reports],
            "reports": [_summary_row(report) for report in reports],
        }
        write_evidence(output / "qualification-summary.json", summary)
        return 0 if summary["passed"] else 2
    finally:
        if not arguments.keep_workspace:
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
