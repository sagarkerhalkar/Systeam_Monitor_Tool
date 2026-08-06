from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
import hashlib
import json
import os
import re
import shutil

from .plan import CERTIFICATION_STEPS, STEP_BY_ID, certification_plan_document, require_step


SCHEMA = "sagar-monitor-physical-certification-evidence-v1"
_ALLOWED_STATUSES = {"PASS", "FAIL"}
_ALLOWED_PLATFORMS = {"windows", "ubuntu", "cross-platform"}
_MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024 * 1024


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _document_hash(document: Mapping[str, Any]) -> str:
    copy = dict(document)
    copy.pop("ledger_sha256", None)
    return _sha256_bytes(_canonical(copy))


def _event_hash(event: Mapping[str, Any]) -> str:
    copy = dict(event)
    copy.pop("event_sha256", None)
    return _sha256_bytes(_canonical(copy))


def _safe_name(name: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(name).name).strip(".-")
    return clean[:120] or "evidence.bin"


def _write(path: Path, document: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    document["ledger_sha256"] = _document_hash(document)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(document, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def load_evidence(path: str | Path) -> dict[str, Any]:
    source = Path(path).expanduser().resolve()
    try:
        value = json.loads(source.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        raise RuntimeError(f"cannot read certification evidence: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("certification evidence is not valid JSON") from exc
    if not isinstance(value, dict) or value.get("schema") != SCHEMA:
        raise RuntimeError("unsupported certification evidence schema")
    return value


def initialize_evidence(
    path: str | Path,
    *,
    release_candidate: str,
    site: str,
    operator: str,
    metadata: Mapping[str, Any] | None = None,
) -> Path:
    destination = Path(path).expanduser().resolve()
    if destination.exists():
        raise FileExistsError(f"certification evidence already exists: {destination}")
    release = str(release_candidate or "").strip()
    site_name = str(site or "").strip()
    operator_name = str(operator or "").strip()
    if not release or not site_name or not operator_name:
        raise ValueError("release_candidate, site and operator are required")
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "release_candidate": release[:160],
        "site": site_name[:160],
        "operator": operator_name[:160],
        "created_at": _utc_now(),
        "plan": certification_plan_document(),
        "metadata": dict(metadata or {}),
        "events": [],
        "finalization": None,
    }
    return _write(destination, document)


def _copy_attachments(evidence_path: Path, attachments: Iterable[str | Path]) -> list[dict[str, Any]]:
    directory = evidence_path.parent / f"{evidence_path.stem}-attachments"
    results: list[dict[str, Any]] = []
    for raw in attachments:
        source = Path(raw).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(f"attachment does not exist: {source}")
        size = source.stat().st_size
        if size > _MAX_ATTACHMENT_BYTES:
            raise ValueError(f"attachment exceeds 2 GiB: {source}")
        digest = _sha256_file(source)
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{digest[:16]}-{_safe_name(source.name)}"
        if destination.exists():
            if _sha256_file(destination) != digest:
                raise RuntimeError(f"attachment collision: {destination}")
        else:
            temporary = destination.with_suffix(destination.suffix + ".tmp")
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
        results.append(
            {
                "name": source.name,
                "relative_path": destination.relative_to(evidence_path.parent).as_posix(),
                "size_bytes": size,
                "sha256": digest,
            }
        )
    return results


def record_machine_snapshot(
    path: str | Path,
    *,
    platform_name: str,
    operator: str,
    snapshot: Mapping[str, Any],
) -> dict[str, Any]:
    return _append_event(
        path,
        step_id="__machine_snapshot__",
        status="PASS",
        platform_name=platform_name,
        operator=operator,
        notes="Physical staging machine snapshot",
        duration_seconds=0.0,
        metrics=dict(snapshot),
        attachments=(),
        enforce_step=False,
    )


def record_step(
    path: str | Path,
    *,
    step_id: str,
    status: str,
    platform_name: str,
    operator: str,
    notes: str = "",
    duration_seconds: float = 0.0,
    metrics: Mapping[str, Any] | None = None,
    attachments: Iterable[str | Path] = (),
) -> dict[str, Any]:
    return _append_event(
        path,
        step_id=step_id,
        status=status,
        platform_name=platform_name,
        operator=operator,
        notes=notes,
        duration_seconds=duration_seconds,
        metrics=dict(metrics or {}),
        attachments=attachments,
        enforce_step=True,
    )


def _append_event(
    path: str | Path,
    *,
    step_id: str,
    status: str,
    platform_name: str,
    operator: str,
    notes: str,
    duration_seconds: float,
    metrics: Mapping[str, Any],
    attachments: Iterable[str | Path],
    enforce_step: bool,
) -> dict[str, Any]:
    evidence_path = Path(path).expanduser().resolve()
    document = load_evidence(evidence_path)
    if document.get("finalization"):
        raise RuntimeError("finalized certification evidence cannot be modified")
    normalized_status = str(status).upper().strip()
    normalized_platform = str(platform_name).lower().strip()
    operator_name = str(operator or "").strip()
    if normalized_status not in _ALLOWED_STATUSES:
        raise ValueError("status must be PASS or FAIL")
    if normalized_platform not in _ALLOWED_PLATFORMS:
        raise ValueError("platform must be windows, ubuntu or cross-platform")
    if not operator_name:
        raise ValueError("operator is required")
    duration = max(0.0, float(duration_seconds))
    attachment_records = _copy_attachments(evidence_path, attachments)

    if enforce_step:
        step = require_step(step_id)
        if step.platform != "cross-platform" and normalized_platform != step.platform:
            raise ValueError(f"step {step_id} requires platform {step.platform}")
        if normalized_status == "PASS" and duration < step.minimum_duration_seconds:
            raise ValueError(
                f"step {step_id} requires at least {step.minimum_duration_seconds} seconds of evidence"
            )
        if normalized_status == "PASS" and step.attachment_required and not attachment_records:
            raise ValueError(f"step {step_id} requires at least one attachment")
    if normalized_status == "PASS" and not (str(notes).strip() or metrics or attachment_records):
        raise ValueError("a passing result requires notes, metrics or an attachment")

    events = document.setdefault("events", [])
    if not isinstance(events, list):
        raise RuntimeError("certification event ledger is invalid")
    previous_hash = str(events[-1].get("event_sha256") or "") if events else ""
    event: dict[str, Any] = {
        "sequence": len(events) + 1,
        "step_id": str(step_id),
        "status": normalized_status,
        "platform": normalized_platform,
        "operator": operator_name[:160],
        "recorded_at": _utc_now(),
        "notes": str(notes or "").strip()[:4000],
        "duration_seconds": round(duration, 3),
        "metrics": dict(metrics),
        "attachments": attachment_records,
        "previous_event_sha256": previous_hash,
    }
    event["event_sha256"] = _event_hash(event)
    events.append(event)
    _write(evidence_path, document)
    return event


def latest_step_results(document: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    latest: dict[str, Mapping[str, Any]] = {}
    events = document.get("events")
    if isinstance(events, list):
        for event in events:
            if isinstance(event, Mapping) and event.get("step_id") in STEP_BY_ID:
                latest[str(event["step_id"])] = event
    return latest


def verify_evidence(path: str | Path, *, require_complete: bool = False) -> dict[str, Any]:
    evidence_path = Path(path).expanduser().resolve()
    document = load_evidence(evidence_path)
    errors: list[str] = []
    warnings: list[str] = []
    stored_document_hash = str(document.get("ledger_sha256") or "")
    if stored_document_hash != _document_hash(document):
        errors.append("ledger_sha256 does not match the evidence document")

    events = document.get("events")
    if not isinstance(events, list):
        errors.append("events must be a list")
        events = []
    previous_hash = ""
    for expected_sequence, event in enumerate(events, start=1):
        if not isinstance(event, dict):
            errors.append(f"event {expected_sequence} is not an object")
            continue
        if event.get("sequence") != expected_sequence:
            errors.append(f"event {expected_sequence} sequence is invalid")
        if str(event.get("previous_event_sha256") or "") != previous_hash:
            errors.append(f"event {expected_sequence} previous hash is invalid")
        event_hash = str(event.get("event_sha256") or "")
        if event_hash != _event_hash(event):
            errors.append(f"event {expected_sequence} hash is invalid")
        previous_hash = event_hash
        attachments = event.get("attachments")
        if not isinstance(attachments, list):
            errors.append(f"event {expected_sequence} attachments are invalid")
            continue
        for attachment in attachments:
            if not isinstance(attachment, Mapping):
                errors.append(f"event {expected_sequence} contains an invalid attachment record")
                continue
            relative = str(attachment.get("relative_path") or "")
            candidate = (evidence_path.parent / relative).resolve()
            try:
                candidate.relative_to(evidence_path.parent)
            except ValueError:
                errors.append(f"event {expected_sequence} attachment path escapes the evidence directory")
                continue
            if not candidate.is_file():
                errors.append(f"event {expected_sequence} attachment is missing: {relative}")
                continue
            if candidate.stat().st_size != int(attachment.get("size_bytes") or -1):
                errors.append(f"event {expected_sequence} attachment size changed: {relative}")
            if _sha256_file(candidate) != str(attachment.get("sha256") or ""):
                errors.append(f"event {expected_sequence} attachment hash changed: {relative}")

    latest = latest_step_results(document)
    missing = [step.step_id for step in CERTIFICATION_STEPS if step.required and step.step_id not in latest]
    failed = [step_id for step_id, event in latest.items() if str(event.get("status")) != "PASS"]
    if require_complete:
        if missing:
            errors.append("missing required steps: " + ", ".join(missing))
        if failed:
            errors.append("non-passing required steps: " + ", ".join(sorted(failed)))
    else:
        if missing:
            warnings.append(f"{len(missing)} required certification steps are not yet recorded")
        if failed:
            warnings.append(f"{len(failed)} certification steps currently have a non-passing result")

    finalization = document.get("finalization")
    if finalization is not None and not isinstance(finalization, Mapping):
        errors.append("finalization is invalid")
    if isinstance(finalization, Mapping):
        if str(finalization.get("status")) != "CERTIFIED":
            errors.append("finalization status is invalid")
        if str(finalization.get("approver") or "").strip().casefold() == str(document.get("operator") or "").strip().casefold():
            errors.append("approver must be different from the original operator")
        if missing or failed:
            errors.append("finalized evidence does not have all required passing steps")

    return {
        "ok": not errors,
        "complete": not missing and not failed,
        "finalized": isinstance(finalization, Mapping),
        "release_candidate": document.get("release_candidate"),
        "site": document.get("site"),
        "event_count": len(events),
        "required_step_count": len(CERTIFICATION_STEPS),
        "passing_step_count": sum(1 for event in latest.values() if event.get("status") == "PASS"),
        "missing_steps": missing,
        "failed_steps": sorted(failed),
        "errors": errors,
        "warnings": warnings,
        "ledger_sha256": stored_document_hash,
    }


def finalize_evidence(path: str | Path, *, approver: str, notes: str = "") -> dict[str, Any]:
    evidence_path = Path(path).expanduser().resolve()
    document = load_evidence(evidence_path)
    if document.get("finalization"):
        raise RuntimeError("certification evidence is already finalized")
    approver_name = str(approver or "").strip()
    if not approver_name:
        raise ValueError("approver is required")
    if approver_name.casefold() == str(document.get("operator") or "").strip().casefold():
        raise ValueError("approver must be different from the original operator")
    verification = verify_evidence(evidence_path, require_complete=True)
    if not verification["ok"]:
        raise RuntimeError("certification cannot be finalized: " + "; ".join(verification["errors"]))
    document["finalization"] = {
        "status": "CERTIFIED",
        "approver": approver_name[:160],
        "approved_at": _utc_now(),
        "notes": str(notes or "").strip()[:4000],
        "pre_finalization_ledger_sha256": document.get("ledger_sha256"),
        "required_step_count": len(CERTIFICATION_STEPS),
    }
    _write(evidence_path, document)
    return verify_evidence(evidence_path, require_complete=True)
