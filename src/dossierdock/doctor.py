"""Preflight checks for container build inputs."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import re

from dossierdock.config import AppConfig, ConfigError, load_config


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    status: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DoctorReport:
    checks: tuple[Check, ...]
    config: AppConfig | None = None

    @property
    def healthy(self) -> bool:
        return all(check.status != "error" for check in self.checks)

    def as_dict(self) -> dict[str, object]:
        return {
            "healthy": self.healthy,
            "checks": [check.as_dict() for check in self.checks],
            "config": self.config.public_dict() if self.config else None,
        }


def _check_file(path: Path, name: str, required: bool) -> Check:
    if path.is_file():
        return Check(name, "ok", f"Found {path.name}.")
    level = "error" if required else "warning"
    tip = "Create it before building the image." if required else "Recommended to reduce build context size."
    return Check(name, level, f"{path.name} was not found. {tip}")


def _docker_contract_checks(config: AppConfig) -> list[Check]:
    """Check image hardening signals without executing Docker or the application."""
    if not config.dockerfile_path.is_file():
        return []
    dockerfile = config.dockerfile_path.read_text(encoding="utf-8", errors="ignore")
    checks: list[Check] = []
    if re.search(r"^\s*USER\s+", dockerfile, flags=re.MULTILINE):
        checks.append(Check("container_user", "ok", "Dockerfile declares a runtime user."))
    else:
        checks.append(Check("container_user", "warning", "Dockerfile has no USER instruction; review root execution."))
    if re.search(r"^\s*HEALTHCHECK\s+", dockerfile, flags=re.MULTILINE):
        checks.append(Check("container_healthcheck", "ok", "Dockerfile declares a container health check."))
    else:
        checks.append(
            Check(
                "container_healthcheck",
                "warning",
                "No Docker HEALTHCHECK found; DossierDock will retain the external HTTP health contract.",
            )
        )
    return checks


def _health_route_check(config: AppConfig) -> Check:
    """Look for the declared route in typical API source files without parsing frameworks."""
    source_suffixes = {".py", ".js", ".ts", ".tsx", ".go", ".java"}
    ignored = {".git", ".venv", "venv", "node_modules", "build", "dist", "__pycache__"}
    marker = config.healthcheck.lower()
    for candidate in config.project_root.rglob("*"):
        if any(part in ignored for part in candidate.parts) or candidate.suffix.lower() not in source_suffixes:
            continue
        if candidate.is_file() and marker in candidate.read_text(encoding="utf-8", errors="ignore").lower():
            return Check("health_route", "ok", f"Found '{config.healthcheck}' in {candidate.relative_to(config.project_root)}.")
    return Check(
        "health_route",
        "warning",
        f"Could not locate '{config.healthcheck}' in source files; verify the route during a smoke test.",
    )


def _secret_exposure_check(config: AppConfig) -> Check:
    """Flag local environment files that are not protected by .gitignore.

    The check never prints values. It only reports the filenames that need review.
    """
    sensitive_names = (".env", ".env.local", ".env.production", "credentials.json", "service-account.json")
    found = [name for name in sensitive_names if (config.project_root / name).is_file()]
    if not found:
        return Check("secret_exposure", "ok", "No common local credential files found in the project root.")

    ignore_file = config.project_root / ".gitignore"
    ignored_patterns = ignore_file.read_text(encoding="utf-8", errors="ignore") if ignore_file.is_file() else ""
    unprotected = [name for name in found if name not in ignored_patterns and not (name.startswith(".env") and ".env" in ignored_patterns)]
    if unprotected:
        return Check("secret_exposure", "error", f"Sensitive local files are not ignored: {', '.join(unprotected)}.")
    return Check("secret_exposure", "warning", f"Local credential files are ignored but should not be copied into images: {', '.join(found)}.")


def run_doctor(path: str | Path | None = None) -> DoctorReport:
    """Run only local, non-invasive preflight checks."""
    try:
        config = load_config(path)
    except ConfigError as error:
        return DoctorReport((Check("manifest", "error", str(error)),))

    checks: list[Check] = [Check("manifest", "ok", f"Loaded {config.config_path.name}.")]
    checks.append(_check_file(config.dockerfile_path, "dockerfile", required=True))

    if config.context_path.is_dir():
        checks.append(Check("context", "ok", f"Build context: {config.context_path}"))
    else:
        checks.append(Check("context", "error", f"Build context not found: {config.context_path}"))

    checks.append(_check_file(config.project_root / ".dockerignore", "dockerignore", required=False))
    checks.extend(_docker_contract_checks(config))
    checks.append(
        Check(
            "healthcheck",
            "ok",
            f"Application should answer on http://localhost:{config.port}{config.healthcheck}.",
        )
    )
    checks.append(_health_route_check(config))
    checks.append(_secret_exposure_check(config))
    checks.append(
        Check(
            "ai_contract",
            "ok",
            f"AI service contract: {config.service_kind}; provider metadata: {config.model_provider}; telemetry: {config.telemetry}.",
        )
    )

    if config.target == "local":
        checks.append(Check("target", "ok", "Local target selected; no remote credentials are required."))
    else:
        checks.append(
            Check(
                "target",
                "warning",
                f"Target '{config.target}' is declared but no remote adapter is installed in this release.",
            )
        )
    return DoctorReport(tuple(checks), config)
