#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import argparse
import json
import shutil
import sys

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
        if count < 1 or count > 10000:
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
            if scenario_root.exists():
                shutil.rmtree(scenario_root)
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
            report = run_qualification_scenario(scenario_root / "commercial.db", config)
            evidence_path = write_evidence(output / f"qualification-{count}-agents.json", report)
            reports.append(report)
            print(
                json.dumps(
                    {
                        "agents": count,
                        "passed": report["passed"],
                        "duration_seconds": report["duration_seconds"],
                        "heartbeat_p95_ms": report["operations"]["heartbeat"]["latency_ms"]["p95"],
                        "errors": report["totals"]["failures"],
                        "evidence": str(evidence_path),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )

        summary = {
            "schema": "sagar-monitor-qualification-summary-v1",
            "passed": all(bool(report.get("passed")) for report in reports),
            "scenario_count": len(reports),
            "agent_counts": [int(report["scenario"]["agent_count"]) for report in reports],
            "reports": [
                {
                    "agent_count": int(report["scenario"]["agent_count"]),
                    "passed": bool(report["passed"]),
                    "duration_seconds": report["duration_seconds"],
                    "total_operations": report["totals"]["operations"],
                    "failures": report["totals"]["failures"],
                    "registration_p95_ms": report["operations"]["registration"]["latency_ms"]["p95"],
                    "heartbeat_p95_ms": report["operations"]["heartbeat"]["latency_ms"]["p95"],
                    "admin_p95_ms": report["operations"]["admin"]["latency_ms"]["p95"],
                    "database_bytes": report["database"]["database_bytes"],
                    "wal_bytes": report["database"]["wal_bytes"],
                    "evidence_sha256": report["evidence_sha256"],
                }
                for report in reports
            ],
        }
        write_evidence(output / "qualification-summary.json", summary)
        return 0 if summary["passed"] else 2
    finally:
        if not arguments.keep_workspace:
            shutil.rmtree(workspace, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
