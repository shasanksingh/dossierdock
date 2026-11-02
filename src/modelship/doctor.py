"""Preflight checks for container build inputs."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

from modelship.config import AppConfig, ConfigError, load_config


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
    checks.append(
        Check(
            "healthcheck",
            "ok",
            f"Application should answer on http://localhost:{config.port}{config.healthcheck}.",
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
