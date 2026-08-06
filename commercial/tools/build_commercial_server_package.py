from __future__ import annotations

from pathlib import Path
import argparse
import json

from sagar_monitor.server.package import build_source_package, verify_source_package


def main() -> int:
    parser = argparse.ArgumentParser(description="Build or verify a commercial server source package")
    subcommands = parser.add_subparsers(dest="command", required=True)
    build = subcommands.add_parser("build")
    build.add_argument("--repository-root", default=str(Path(__file__).resolve().parents[2]))
    build.add_argument("--output", required=True)
    build.add_argument("--version", required=True)
    verify = subcommands.add_parser("verify")
    verify.add_argument("--package", required=True)
    arguments = parser.parse_args()
    if arguments.command == "build":
        result = build_source_package(
            arguments.repository_root,
            arguments.output,
            version=arguments.version,
        )
    else:
        result = verify_source_package(arguments.package)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
