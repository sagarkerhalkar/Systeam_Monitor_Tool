from __future__ import annotations

import argparse
import json
import sys

from .mirror import issue_runner_registration_token, private_mirror_plan, sync_private_mirror
from .plan import ROLE_BY_ID, REPOSITORY_FULL_NAME, staging_plan_document
from .preflight import (
    create_host_marker,
    create_runner_receipt,
    load_and_verify_marker,
    preflight_host,
    verify_runner_receipt,
    write_json,
)
from .release import build_release_candidate, verify_release_candidate
from .repository import require_private_repository


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Prepare and verify the commercial staging lab")
    sub = result.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="Print the fixed staging-lab plan")
    plan.add_argument("--output")

    preflight = sub.add_parser("preflight", help="Run clean or installed host preflight")
    preflight.add_argument("--role", required=True, choices=sorted(ROLE_BY_ID))
    preflight.add_argument("--work-root", required=True)
    preflight.add_argument("--phase", choices=("clean", "installed"), default="clean")
    preflight.add_argument("--output", required=True)
    preflight.add_argument("--marker")
    preflight.add_argument("--site")
    preflight.add_argument("--operator")

    marker = sub.add_parser("verify-marker", help="Verify a staging-host marker")
    marker.add_argument("--marker", required=True)
    marker.add_argument("--expected-role")

    repository = sub.add_parser("repository-check", help="Require a private GitHub repository")
    repository.add_argument("--repository", default=REPOSITORY_FULL_NAME)
    repository.add_argument("--gh-executable", default="gh")

    mirror_plan = sub.add_parser("private-mirror-plan", help="Print the private staging mirror plan")
    mirror_plan.add_argument("--source-repository", default=REPOSITORY_FULL_NAME)
    mirror_plan.add_argument("--target-repository", required=True)
    mirror_plan.add_argument("--expected-source-commit", required=True)

    mirror_sync = sub.add_parser("private-mirror-sync", help="Create or synchronize the private staging repository")
    mirror_sync.add_argument("--repository-root", default=".")
    mirror_sync.add_argument("--source-repository", default=REPOSITORY_FULL_NAME)
    mirror_sync.add_argument("--target-repository", required=True)
    mirror_sync.add_argument("--expected-source-commit", required=True)
    mirror_sync.add_argument("--gh-executable", default="gh")
    mirror_sync.add_argument("--git-executable", default="git")
    mirror_sync.add_argument("--require-existing-target", action="store_true")
    mirror_sync.add_argument("--dry-run", action="store_true")
    mirror_sync.add_argument("--output")

    runner_token = sub.add_parser("issue-runner-token", help="Write a short-lived runner registration token to a protected file")
    runner_token.add_argument("--repository", required=True)
    runner_token.add_argument("--output", required=True)
    runner_token.add_argument("--repository-root", default=".")
    runner_token.add_argument("--gh-executable", default="gh")

    write_receipt = sub.add_parser("write-runner-receipt", help="Write a hashed ephemeral runner receipt")
    write_receipt.add_argument("--receipt", required=True)
    write_receipt.add_argument("--marker", required=True)
    write_receipt.add_argument("--repository", default=REPOSITORY_FULL_NAME)
    write_receipt.add_argument("--platform", required=True, choices=("windows", "ubuntu"))
    write_receipt.add_argument("--runner-name", required=True)

    receipt = sub.add_parser("verify-runner-receipt", help="Verify ephemeral runner receipt")
    receipt.add_argument("--receipt", required=True)
    receipt.add_argument("--marker", required=True)
    receipt.add_argument("--repository", default=REPOSITORY_FULL_NAME)
    receipt.add_argument("--platform", required=True, choices=("windows", "ubuntu"))

    build = sub.add_parser("build-rc", help="Build a deterministic staging release candidate")
    build.add_argument("--repository-root", default=".")
    build.add_argument("--output", required=True)
    build.add_argument("--version", required=True)
    build.add_argument("--source-commit", required=True)

    verify = sub.add_parser("verify-rc", help="Verify a staging release candidate")
    verify.add_argument("--package", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    arguments = parser().parse_args(argv)
    try:
        if arguments.command == "plan":
            document = staging_plan_document()
            if arguments.output:
                write_json(arguments.output, document)
            _print(document)
            return 0

        if arguments.command == "preflight":
            result = preflight_host(role_id=arguments.role, work_root=arguments.work_root, phase=arguments.phase)
            write_json(arguments.output, result)
            if arguments.marker:
                if not arguments.site or not arguments.operator:
                    raise ValueError("--site and --operator are required with --marker")
                create_host_marker(
                    arguments.marker,
                    role_id=arguments.role,
                    site=arguments.site,
                    operator=arguments.operator,
                    preflight=result,
                )
            _print(result)
            return 0 if result["ok"] else 2

        if arguments.command == "verify-marker":
            marker = load_and_verify_marker(arguments.marker, expected_role=arguments.expected_role)
            _print({"ok": True, "marker": marker})
            return 0

        if arguments.command == "repository-check":
            _print(require_private_repository(arguments.repository, gh_executable=arguments.gh_executable))
            return 0

        if arguments.command == "private-mirror-plan":
            _print(
                private_mirror_plan(
                    source_repository=arguments.source_repository,
                    target_repository=arguments.target_repository,
                    expected_source_commit=arguments.expected_source_commit,
                )
            )
            return 0

        if arguments.command == "private-mirror-sync":
            result = sync_private_mirror(
                arguments.repository_root,
                source_repository=arguments.source_repository,
                target_repository=arguments.target_repository,
                expected_source_commit=arguments.expected_source_commit,
                gh_executable=arguments.gh_executable,
                git_executable=arguments.git_executable,
                create_if_missing=not arguments.require_existing_target,
                dry_run=arguments.dry_run,
            )
            if arguments.output:
                write_json(arguments.output, result)
            _print(result)
            return 0

        if arguments.command == "issue-runner-token":
            _print(
                issue_runner_registration_token(
                    arguments.repository,
                    arguments.output,
                    gh_executable=arguments.gh_executable,
                    forbidden_root=arguments.repository_root,
                )
            )
            return 0

        if arguments.command == "write-runner-receipt":
            destination = create_runner_receipt(
                arguments.receipt,
                marker_path=arguments.marker,
                repository=arguments.repository,
                platform_name=arguments.platform,
                runner_name=arguments.runner_name,
            )
            _print({"ok": True, "receipt": str(destination)})
            return 0

        if arguments.command == "verify-runner-receipt":
            result = verify_runner_receipt(
                arguments.receipt,
                marker_path=arguments.marker,
                repository=arguments.repository,
                platform_name=arguments.platform,
            )
            _print(result)
            return 0 if result["ok"] else 2

        if arguments.command == "build-rc":
            _print(
                build_release_candidate(
                    arguments.repository_root,
                    arguments.output,
                    version=arguments.version,
                    source_commit=arguments.source_commit,
                )
            )
            return 0

        if arguments.command == "verify-rc":
            _print(verify_release_candidate(arguments.package))
            return 0
    except Exception as exc:
        print(
            json.dumps({"ok": False, "error": {"type": type(exc).__name__, "message": str(exc)}}, sort_keys=True),
            file=sys.stderr,
        )
        return 2
    return 2