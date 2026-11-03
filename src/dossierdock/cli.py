"""Command-line interface for DossierDock."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence

from dossierdock import __version__
from dossierdock.config import DEFAULT_CONFIG
from dossierdock.doctor import run_doctor
from dossierdock.evidence import build_dossier
from dossierdock.manifests import render_compose, render_kubernetes
from dossierdock.topology import agent_graph, agent_start_order, format_agent_graph
from dossierdock.workflow import GITHUB_ACTIONS_WORKFLOW


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
    print("\nDossierDock is ready." if report.healthy else "\nDossierDock found issues to resolve.")


def _command_init(args: argparse.Namespace) -> int:
    root = Path(args.path).expanduser().resolve()
    destination = root / "dossierdock.toml"
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
        "runtime": {
            "readiness": config.readiness_path,
            "liveness": config.liveness_path,
            "metrics": config.metrics_path,
            "workers": config.workers,
            "shutdown_seconds": config.shutdown_seconds,
        },
        "agent_start_order": list(agent_start_order(config.agents)),
        "ready": report.healthy,
    }
    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        print(f"Application: {plan['application']} ({plan['environment']})")
        print(f"Target:      {plan['target']}")
        print(f"Build:       docker build -f {config.dockerfile} -t {config.image} {config.context}")
        print(f"Health:      {plan['healthcheck']}")
        print(f"Readiness:   {config.readiness_path} | Liveness: {config.liveness_path} | Metrics: {config.metrics_path}")
        print(f"Agents:      {', '.join(plan['agent_start_order']) if plan['agent_start_order'] else 'single runtime'}")
        print(f"Ready:       {'yes' if report.healthy else 'no — run dossierdock doctor'}")
    return 0 if report.healthy else 1


def _command_graph(args: argparse.Namespace) -> int:
    report = run_doctor(args.config)
    if not report.config:
        _print_report(report, args.json)
        return 1
    if args.json:
        print(json.dumps(agent_graph(report.config.agents), indent=2))
    else:
        print(format_agent_graph(report.config.agents))
    return 0


def _command_manifest(args: argparse.Namespace, renderer, label: str) -> int:
    report = run_doctor(args.config)
    if not report.config:
        _print_report(report, as_json=False)
        return 1
    destination = Path(args.output).expanduser().resolve()
    try:
        _write(destination, renderer(report.config), args.force)
    except FileExistsError as error:
        print(error, file=sys.stderr)
        return 2
    print(f"Created {label} manifest: {destination}")
    return 0


def _command_manifest_kubernetes(args: argparse.Namespace) -> int:
    return _command_manifest(args, render_kubernetes, "Kubernetes")


def _command_manifest_compose(args: argparse.Namespace) -> int:
    return _command_manifest(args, render_compose, "Compose")


def _command_dossier(args: argparse.Namespace) -> int:
    report = run_doctor(args.config)
    dossier = build_dossier(report)
    serialized = json.dumps(dossier, indent=2) + "\n"
    if args.output == "-":
        print(serialized, end="")
    else:
        destination = Path(args.output).expanduser().resolve()
        try:
            _write(destination, serialized, args.force)
        except FileExistsError as error:
            print(error, file=sys.stderr)
            return 2
        print(f"Created release dossier: {destination}")
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
        prog="dossierdock",
        description="Release-readiness evidence and CI workflow generation for containerized AI services.",
    )
    parser.add_argument("--version", action="version", version=f"dossierdock {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create a starter dossierdock.toml manifest.")
    init_parser.add_argument("--path", default=".", help="Directory that will receive dossierdock.toml.")
    init_parser.add_argument("--force", action="store_true", help="Replace an existing manifest.")
    init_parser.set_defaults(handler=_command_init)

    for name, handler, help_text in (
        ("doctor", _command_doctor, "Check local container-delivery inputs."),
        ("plan", _command_plan, "Show the generated build and health-check plan."),
        ("graph", _command_graph, "Show a dependency-safe multi-agent startup runbook."),
    ):
        command = subparsers.add_parser(name, help=help_text)
        command.add_argument("--config", help="Path to dossierdock.toml (defaults to the current directory).")
        command.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
        command.set_defaults(handler=handler)

    dossier = subparsers.add_parser("dossier", help="Create a portable AI service release-evidence dossier.")
    dossier.add_argument("--config", help="Path to dossierdock.toml (defaults to the current directory).")
    dossier.add_argument(
        "--output",
        default=".dossierdock/release-dossier.json",
        help="Dossier destination, or '-' to print JSON to stdout.",
    )
    dossier.add_argument("--force", action="store_true", help="Replace an existing dossier.")
    dossier.set_defaults(handler=_command_dossier)

    manifest = subparsers.add_parser("manifest", help="Generate reviewable deployment manifests without secrets.")
    manifest_subparsers = manifest.add_subparsers(dest="manifest_command", required=True)
    kubernetes = manifest_subparsers.add_parser("kubernetes", help="Write a Kubernetes Deployment and Service manifest.")
    kubernetes.add_argument("--config", help="Path to dossierdock.toml (defaults to the current directory).")
    kubernetes.add_argument("--output", default="k8s/dossierdock.yaml", help="Kubernetes manifest destination.")
    kubernetes.add_argument("--force", action="store_true", help="Replace an existing manifest.")
    kubernetes.set_defaults(handler=_command_manifest_kubernetes)

    compose = manifest_subparsers.add_parser("compose", help="Write a Docker Compose starter manifest.")
    compose.add_argument("--config", help="Path to dossierdock.toml (defaults to the current directory).")
    compose.add_argument("--output", default="compose.dossierdock.yml", help="Compose manifest destination.")
    compose.add_argument("--force", action="store_true", help="Replace an existing manifest.")
    compose.set_defaults(handler=_command_manifest_compose)

    workflow = subparsers.add_parser("workflow", help="Generate CI workflow files.")
    workflow_subparsers = workflow.add_subparsers(dest="workflow_command", required=True)
    github = workflow_subparsers.add_parser("github", help="Write a GitHub Actions CI workflow.")
    github.add_argument("--output", default=".github/workflows/dossierdock.yml", help="Workflow destination.")
    github.add_argument("--force", action="store_true", help="Replace an existing workflow.")
    github.set_defaults(handler=_command_workflow_github)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    return arguments.handler(arguments)
