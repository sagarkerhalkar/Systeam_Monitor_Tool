from __future__ import annotations

from typing import Any
import json
import shutil
import subprocess


def repository_visibility(repository: str, *, gh_executable: str = "gh") -> dict[str, Any]:
    repository_name = str(repository or "").strip()
    if not repository_name or "/" not in repository_name:
        raise ValueError("repository must be in owner/name form")
    executable = shutil.which(gh_executable)
    if not executable:
        raise RuntimeError("GitHub CLI is required and must be authenticated")
    completed = subprocess.run(
        [executable, "repo", "view", repository_name, "--json", "visibility"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        message = (completed.stderr or completed.stdout).strip()
        raise RuntimeError("cannot verify repository visibility with GitHub CLI: " + message[-1000:])
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub CLI returned invalid visibility JSON") from exc
    visibility = str(payload.get("visibility") or "").upper()
    if visibility not in {"PUBLIC", "PRIVATE", "INTERNAL"}:
        raise RuntimeError("GitHub CLI did not return a supported repository visibility")
    return {
        "ok": visibility == "PRIVATE",
        "repository": repository_name,
        "visibility": visibility,
        "required_visibility": "PRIVATE",
    }


def require_private_repository(repository: str, *, gh_executable: str = "gh") -> dict[str, Any]:
    result = repository_visibility(repository, gh_executable=gh_executable)
    if not result["ok"]:
        raise RuntimeError(
            f"self-hosted runner registration is blocked because {repository} is {result['visibility']}; "
            "use a private repository"
        )
    return result
