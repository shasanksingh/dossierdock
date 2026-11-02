"""Command-line interface for ModelShip."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from modelship import __version__
from modelship.config import DEFAULT_CONFIG
from modelship.doctor import run_doctor
from modelship.workflow import GITHUB_ACTIONS_WORKFLOW


def _write(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite {path}. Use --force to replace it.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _print_report(report, as_json: bool) -> None:
    if as_json:
        print(json.dumps(report.as_dict(), indent=2))
        return
    for check in report.checks:
        print(f"[{check.status.upper():7}] {check.name}: {check.message}")
    print("\nModelShip is ready." if report.healthy else "\nModelShip found issues to resolve.")


def _command_init(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser().resolve()
    destination = root / "modelship.toml"
    try:
        _write(destination, DEFAULT_CONFIG, args.force)
    except FileExistsError as error:
        print(error, file=sys.stderr)
        return 2
    print(f"Created {destination}")
    return 0


def _command_doctor(args: argparse.Namespace) -> int:
    report = run_doctor(args.config)
    _print_report(report, args.json)
    return 0 if report.healthy else 1


def _command_plan(args: argparse.Namespace) -> int:
    report = run_doctor(args.config)
    if not report.config:
        _print_report(report, args.json)
        return 1
    config = report.config
    plan = {
        "application": config.name,
        "environment": config.environment,
        "target": config.target,
        "build": {
            "context": str(config.context_path),
            "dockerfile": str(config.dockerfile_path),
            "image": config.image,
        },
        "healthcheck": f"http://localhost:{config.port}{config.healthcheck}",
        "ready": report.healthy,
    }
    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        print(f"Application: {plan['application']} ({plan['environment']})")
        print(f"Target:      {plan['target']}")
        print(f"Build:       docker build -f {config.dockerfile} -t {config.image} {config.context}")
        print(f"Health:      {plan['healthcheck']}")
        print(f"Ready:       {'yes' if report.healthy else 'no — run modelship doctor'}")
    return 0 if report.healthy else 1


def _command_workflow_github(args: argparse.Namespace) -> int:
    destination = Path(args.output).expanduser().resolve()
    try:
        _write(destination, GITHUB_ACTIONS_WORKFLOW, args.force)
    except FileExistsError as error:
        print(error, file=sys.stderr)
        return 2
    print(f"Created GitHub Actions workflow: {destination}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="modelship",
        description="Deployment checks and CI workflow generation for containerized AI services.",
    )
    parser.add_argument("--version", action="version", version=f"modelship {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a starter modelship.toml manifest.")
    init_parser.add_argument("--path", default=".", help="Directory that will receive modelship.toml.")
    init_parser.add_argument("--force", action="store_true", help="Replace an existing manifest.")
    init_parser.set_defaults(handler=_command_init)

    for name, handler, help_text in (
        ("doctor", _command_doctor, "Check local container-delivery inputs."),
        ("plan", _command_plan, "Show the generated build and health-check plan."),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--config", help="Path to modelship.toml (defaults to the current directory).")
        command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
        command.set_defaults(handler=handler)

    workflow = subparsers.add_parser("workflow", help="Generate CI workflow files.")
    workflow_subparsers = workflow.add_subparsers(dest="workflow_command", required=True)
    github = workflow_subparsers.add_parser("github", help="Write a GitHub Actions CI workflow.")
    github.add_argument("--output", default=".github/workflows/modelship.yml", help="Workflow destination.")
    github.add_argument("--force", action="store_true", help="Replace an existing workflow.")
    github.set_defaults(handler=_command_workflow_github)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    return arguments.handler(arguments)
