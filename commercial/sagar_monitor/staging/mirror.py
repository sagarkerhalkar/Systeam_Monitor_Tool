from __future__ import annotations

from pathlib import Path
from typing import Any
import json
import os
import re
import shutil
import subprocess


_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_COMMIT_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_DEFAULT_BRANCH = "commercial-v1"
_DEFAULT_ENVIRONMENT = "commercial-staging-certification"


def _validate_repository(value: str) -> str:
    repository = str(value or "").strip()
    if not _REPOSITORY_RE.fullmatch(repository):
        raise ValueError("repository must be in owner/name form")
    return repository


def _validate_commit(value: str) -> str:
    commit = str(value or "").strip().lower()
    if not _COMMIT_RE.fullmatch(commit):
        raise ValueError("expected source commit must be a full 40-character hexadecimal SHA")
    return commit


def _which(name: str) -> str:
    executable = shutil.which(name)
    if not executable:
        raise RuntimeError(f"required executable is unavailable: {name}")
    return executable


def _run(command: list[str], *, cwd: Path | None = None, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout or "command failed").strip()
        raise RuntimeError(f"command failed ({command[0]}): {message[-2000:]}")
    return completed


def _origin_repository(remote_url: str) -> str:
    value = str(remote_url or "").strip()
    patterns = (
        re.compile(r"^https://github\.com/([^/]+/[^/]+?)(?:\.git)?$", re.IGNORECASE),
        re.compile(r"^git@github\.com:([^/]+/[^/]+?)(?:\.git)?$", re.IGNORECASE),
        re.compile(r"^ssh://git@github\.com/([^/]+/[^/]+?)(?:\.git)?$", re.IGNORECASE),
    )
    for pattern in patterns:
        match = pattern.fullmatch(value)
        if match:
            return _validate_repository(match.group(1))
    raise RuntimeError("origin must be a github.com repository URL")


def _target_visibility(gh: str, repository: str) -> str | None:
    completed = subprocess.run(
        [gh, "repo", "view", repository, "--json", "visibility"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        text = (completed.stderr or completed.stdout or "").lower()
        if "could not resolve to a repository" in text or "repository not found" in text:
            return None
        raise RuntimeError("cannot inspect target repository: " + (completed.stderr or completed.stdout).strip()[-1000:])
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub CLI returned invalid target visibility JSON") from exc
    visibility = str(payload.get("visibility") or "").upper()
    if visibility not in {"PUBLIC", "PRIVATE", "INTERNAL"}:
        raise RuntimeError("GitHub CLI did not return a supported target visibility")
    return visibility


def private_mirror_plan(*, source_repository: str, target_repository: str, expected_source_commit: str) -> dict[str, Any]:
    source = _validate_repository(source_repository)
    target = _validate_repository(target_repository)
    commit = _validate_commit(expected_source_commit)
    if source.lower() == target.lower():
        raise ValueError("private staging target must be different from the public source repository")
    return {
        "format": "sagar-monitor-private-staging-mirror-plan-v1",
        "source_repository": source,
        "source_branch": _DEFAULT_BRANCH,
        "expected_source_commit": commit,
        "target_repository": target,
        "required_target_visibility": "PRIVATE",
        "target_branch": _DEFAULT_BRANCH,
        "required_environment": _DEFAULT_ENVIRONMENT,
        "production_deployment_authorized": False,
        "contains_secrets": False,
        "steps": [
            "verify authenticated GitHub CLI and clean non-shallow source checkout",
            "verify origin repository and exact commercial-v1 source commit",
            "create private target when absent or reject non-private target",
            "push exact certified source commit to target commercial-v1",
            "set target default branch to commercial-v1",
            "create the staging certification environment",
            "verify the remote target branch SHA exactly matches the certified source commit",
        ],
    }


def sync_private_mirror(
    repository_root: str | Path,
    *,
    source_repository: str,
    target_repository: str,
    expected_source_commit: str,
    gh_executable: str = "gh",
    git_executable: str = "git",
    create_if_missing: bool = True,
    dry_run: bool = False,
) -> dict[str, Any]:
    root = Path(repository_root).expanduser().resolve()
    if not (root / ".git").exists():
        raise RuntimeError("repository root must be a Git checkout")
    plan = private_mirror_plan(
        source_repository=source_repository,
        target_repository=target_repository,
        expected_source_commit=expected_source_commit,
    )
    source = plan["source_repository"]
    target = plan["target_repository"]
    expected = plan["expected_source_commit"]
    gh = _which(gh_executable)
    git = _which(git_executable)

    _run([gh, "auth", "status", "--hostname", "github.com"])
    status = _run([git, "status", "--porcelain=v1"], cwd=root).stdout.strip()
    if status:
        raise RuntimeError("source checkout must be clean before staging mirror synchronization")
    shallow = _run([git, "rev-parse", "--is-shallow-repository"], cwd=root).stdout.strip().lower()
    if shallow != "false":
        raise RuntimeError("source checkout must be a complete non-shallow clone before staging mirror synchronization")
    origin_url = _run([git, "remote", "get-url", "origin"], cwd=root).stdout.strip()
    detected_source = _origin_repository(origin_url)
    if detected_source.lower() != source.lower():
        raise RuntimeError(f"origin repository mismatch: expected {source}, found {detected_source}")

    _run([git, "fetch", "--no-tags", "origin", _DEFAULT_BRANCH], cwd=root, timeout=180)
    fetched = _run([git, "rev-parse", "FETCH_HEAD"], cwd=root).stdout.strip().lower()
    if fetched != expected:
        raise RuntimeError(f"certified source commit mismatch: expected {expected}, fetched {fetched}")

    visibility = _target_visibility(gh, target)
    target_created = False
    if visibility is None:
        if not create_if_missing:
            raise RuntimeError("private staging target repository does not exist")
        if dry_run:
            visibility = "WOULD_CREATE_PRIVATE"
        else:
            _run([gh, "repo", "create", target, "--private", "--disable-issues", "--disable-wiki"])
            target_created = True
            visibility = _target_visibility(gh, target)
    if visibility not in {"PRIVATE", "WOULD_CREATE_PRIVATE"}:
        raise RuntimeError(f"staging target must be PRIVATE; found {visibility}")

    if dry_run:
        return {
            "ok": True,
            "dry_run": True,
            "source_repository": source,
            "source_commit": expected,
            "target_repository": target,
            "target_visibility": visibility,
            "target_created": False,
            "target_branch": _DEFAULT_BRANCH,
            "environment": _DEFAULT_ENVIRONMENT,
            "production_deployment_authorized": False,
        }

    _run([gh, "auth", "setup-git", "--hostname", "github.com"])
    target_url = f"https://github.com/{target}.git"
    _run([git, "push", target_url, f"{expected}:refs/heads/{_DEFAULT_BRANCH}"], cwd=root, timeout=300)
    _run([gh, "repo", "edit", target, "--default-branch", _DEFAULT_BRANCH])
    _run([gh, "api", "--method", "PUT", f"repos/{target}/environments/{_DEFAULT_ENVIRONMENT}"])
    remote_sha = _run(
        [gh, "api", f"repos/{target}/git/ref/heads/{_DEFAULT_BRANCH}", "--jq", ".object.sha"]
    ).stdout.strip().lower()
    if remote_sha != expected:
        raise RuntimeError(f"private mirror SHA verification failed: expected {expected}, found {remote_sha}")
    final_visibility = _target_visibility(gh, target)
    if final_visibility != "PRIVATE":
        raise RuntimeError("private staging repository visibility changed during synchronization")

    return {
        "ok": True,
        "dry_run": False,
        "source_repository": source,
        "source_commit": expected,
        "target_repository": target,
        "target_visibility": final_visibility,
        "target_created": target_created,
        "target_branch": _DEFAULT_BRANCH,
        "verified_target_commit": remote_sha,
        "environment": _DEFAULT_ENVIRONMENT,
        "production_deployment_authorized": False,
    }


def issue_runner_registration_token(
    repository: str,
    output_path: str | Path,
    *,
    gh_executable: str = "gh",
    forbidden_root: str | Path | None = None,
) -> dict[str, Any]:
    target = _validate_repository(repository)
    destination = Path(output_path).expanduser().resolve()
    if forbidden_root is not None:
        root = Path(forbidden_root).expanduser().resolve()
        try:
            destination.relative_to(root)
        except ValueError:
            pass
        else:
            raise RuntimeError("runner registration token file must be stored outside the source repository")

    gh = _which(gh_executable)
    _run([gh, "auth", "status", "--hostname", "github.com"])
    visibility = _target_visibility(gh, target)
    if visibility != "PRIVATE":
        raise RuntimeError(f"runner token issuance is blocked because {target} is not PRIVATE")
    token = _run(
        [gh, "api", "--method", "POST", f"repos/{target}/actions/runners/registration-token", "--jq", ".token"]
    ).stdout.strip()
    if not token or any(character.isspace() for character in token):
        raise RuntimeError("GitHub CLI did not return a valid runner registration token")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(token, encoding="utf-8")
    try:
        os.chmod(temporary, 0o600)
    except OSError:
        pass
    os.replace(temporary, destination)
    try:
        os.chmod(destination, 0o600)
    except OSError:
        pass
    return {
        "ok": True,
        "repository": target,
        "visibility": visibility,
        "token_file": str(destination),
        "token_printed": False,
    }