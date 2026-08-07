#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def require_files() -> tuple[Path, ...]:
    required = (
        ROOT / "commercial" / "sagar_monitor" / "staging" / "plan.py",
        ROOT / "commercial" / "sagar_monitor" / "staging" / "preflight.py",
        ROOT / "commercial" / "sagar_monitor" / "staging" / "repository.py",
        ROOT / "commercial" / "sagar_monitor" / "staging" / "release.py",
        ROOT / "commercial" / "sagar_monitor" / "staging" / "mirror.py",
        ROOT / "commercial" / "sagar_monitor" / "staging" / "cli.py",
        ROOT / "commercial" / "tools" / "run_staging_lab.py",
        ROOT / "commercial" / "staging" / "windows" / "prepare-staging-host.ps1",
        ROOT / "commercial" / "staging" / "windows" / "install-ephemeral-runner.ps1",
        ROOT / "commercial" / "staging" / "windows" / "remove-staging-runner.ps1",
        ROOT / "commercial" / "staging" / "windows" / "bootstrap-private-staging.ps1",
        ROOT / "commercial" / "staging" / "windows" / "issue-private-runner-token.ps1",
        ROOT / "commercial" / "staging" / "ubuntu" / "prepare-staging-host.sh",
        ROOT / "commercial" / "staging" / "ubuntu" / "install-ephemeral-runner.sh",
        ROOT / "commercial" / "staging" / "ubuntu" / "remove-staging-runner.sh",
        ROOT / "commercial" / "staging" / "ubuntu" / "bootstrap-private-staging.sh",
        ROOT / "commercial" / "staging" / "ubuntu" / "issue-private-runner-token.sh",
        ROOT / "commercial" / "tests" / "test_staging_lab.py",
        ROOT / "commercial" / "tests" / "test_private_staging_mirror.py",
        ROOT / ".github" / "workflows" / "commercial-physical-certification.yml",
        ROOT / ".github" / "workflows" / "commercial-staging-rc.yml",
        ROOT / "docs" / "PRIVATE_STAGING_MIRROR_V1.md",
    )
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        fail("required staging-lab files are missing: " + ", ".join(missing))
    return required


def verify_plan_and_repository_gate() -> None:
    plan = (ROOT / "commercial/sagar_monitor/staging/plan.py").read_text(encoding="utf-8")
    for marker in (
        "windows_server",
        "ubuntu_server",
        "windows_client_1",
        "windows_client_2",
        "ubuntu_client_1",
        "ubuntu_client_2",
        "restore_host",
        "REQUIRED_REPOSITORY_VISIBILITY = \"PRIVATE\"",
        "PRODUCTION_PORT = 2278",
    ):
        if marker not in plan:
            fail(f"staging plan is missing marker: {marker}")

    repository = (ROOT / "commercial/sagar_monitor/staging/repository.py").read_text(encoding="utf-8")
    for marker in ("gh", "repo", "view", "visibility", "use a private repository"):
        if marker not in repository:
            fail(f"private repository gate is missing marker: {marker}")


def verify_private_mirror() -> None:
    mirror = (ROOT / "commercial/sagar_monitor/staging/mirror.py").read_text(encoding="utf-8")
    for marker in (
        "private staging target must be different from the public source repository",
        "source checkout must be clean",
        "certified source commit mismatch",
        "--private",
        "commercial-staging-certification",
        "private mirror SHA verification failed",
        "runner registration token file must be stored outside the source repository",
        "runner token issuance is blocked",
        "token_printed",
    ):
        if marker not in mirror:
            fail(f"private staging mirror is missing safety marker: {marker}")

    wrappers = (
        ROOT / "commercial/staging/windows/bootstrap-private-staging.ps1",
        ROOT / "commercial/staging/windows/issue-private-runner-token.ps1",
        ROOT / "commercial/staging/ubuntu/bootstrap-private-staging.sh",
        ROOT / "commercial/staging/ubuntu/issue-private-runner-token.sh",
    )
    for wrapper in wrappers:
        text = wrapper.read_text(encoding="utf-8")
        if "ghp_" in text or "github_pat_" in text:
            fail(f"{wrapper.relative_to(ROOT)} contains a forbidden token pattern")
    if "private-mirror-sync" not in wrappers[0].read_text(encoding="utf-8"):
        fail("Windows private mirror launcher is missing private-mirror-sync")
    if "private-mirror-sync" not in wrappers[2].read_text(encoding="utf-8"):
        fail("Ubuntu private mirror launcher is missing private-mirror-sync")
    if "issue-runner-token" not in wrappers[1].read_text(encoding="utf-8"):
        fail("Windows runner-token launcher is missing issue-runner-token")
    if "issue-runner-token" not in wrappers[3].read_text(encoding="utf-8"):
        fail("Ubuntu runner-token launcher is missing issue-runner-token")


def verify_runner_scripts() -> None:
    scripts = (
        ROOT / "commercial/staging/windows/install-ephemeral-runner.ps1",
        ROOT / "commercial/staging/ubuntu/install-ephemeral-runner.sh",
    )
    forbidden_secret_patterns = (
        re.compile(r"ghp_[A-Za-z0-9]"),
        re.compile(r"github_pat_[A-Za-z0-9]"),
        re.compile(r"-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    )
    for script in scripts:
        text = script.read_text(encoding="utf-8")
        for marker in (
            "repository-check",
            "--ephemeral",
            "verify-marker",
            "write-runner-receipt",
            "verify-runner-receipt",
        ):
            if marker not in text:
                fail(f"{script.relative_to(ROOT)} is missing staging safety marker: {marker}")
        lower = text.lower()
        if "invoke-webrequest" in lower or "curl " in lower or "wget " in lower:
            fail(f"{script.relative_to(ROOT)} must use a local SHA-256-verified runner archive")
        for pattern in forbidden_secret_patterns:
            if pattern.search(text):
                fail(f"{script.relative_to(ROOT)} contains a forbidden secret pattern")

    windows = scripts[0].read_text(encoding="utf-8")
    if "Remove-Item -LiteralPath $RegistrationTokenFile" not in windows:
        fail("Windows runner bootstrap must delete the registration token file")
    ubuntu = scripts[1].read_text(encoding="utf-8")
    if "cleanup_token" not in ubuntu or "shred -u" not in ubuntu:
        fail("Ubuntu runner bootstrap must remove the registration token file")


def verify_workflows() -> None:
    physical = (ROOT / ".github/workflows/commercial-physical-certification.yml").read_text(encoding="utf-8")
    for marker in (
        "workflow_dispatch",
        "github.event.repository.private",
        "refs/heads/commercial-v1",
        "needs: repository-safety",
        "environment: commercial-staging-certification",
        "verify-runner-receipt",
        "commercial-certification",
    ):
        if marker not in physical:
            fail(f"physical workflow is missing safety marker: {marker}")

    rc = (ROOT / ".github/workflows/commercial-staging-rc.yml").read_text(encoding="utf-8")
    for marker in (
        "refs/heads/commercial-v1",
        "run_staging_lab.py build-rc",
        "run_staging_lab.py verify-rc",
        "retention-days: 90",
        "sha256sum",
    ):
        if marker not in rc:
            fail(f"staging RC workflow is missing marker: {marker}")


def verify_packaging() -> None:
    package = (ROOT / "commercial/sagar_monitor/server/package.py").read_text(encoding="utf-8")
    for marker in (
        "commercial / \"tools\" / \"run_staging_lab.py\"",
        "commercial / \"staging\"",
    ):
        if marker not in package:
            fail(f"commercial package builder is missing staging marker: {marker}")

    release = (ROOT / "commercial/sagar_monitor/staging/release.py").read_text(encoding="utf-8")
    for marker in (
        "contains_secrets",
        "production_deployment_authorized",
        "nested commercial-server package SHA-256 mismatch",
        "release candidate contains undeclared files",
    ):
        if marker not in release:
            fail(f"staging release candidate is missing marker: {marker}")


def main() -> int:
    require_files()
    verify_plan_and_repository_gate()
    verify_private_mirror()
    verify_runner_scripts()
    verify_workflows()
    verify_packaging()
    print("Commercial staging-lab foundation verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())