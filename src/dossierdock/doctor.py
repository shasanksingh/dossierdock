"""Preflight checks for container build inputs."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import os
from pathlib import Path
import re

from dossierdock.config import AppConfig, ConfigError, load_config
from dossierdock.topology import agent_start_order


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


def _base_image_check(config: AppConfig) -> Check:
    """Warn about mutable or untagged container base images."""
    if not config.dockerfile_path.is_file():
        return Check("base_image", "warning", "Dockerfile is unavailable; base-image pinning could not be reviewed.")
    dockerfile = config.dockerfile_path.read_text(encoding="utf-8", errors="ignore")
    matches = re.findall(r"^\s*FROM\s+(?:--platform=\S+\s+)?([^\s]+)", dockerfile, flags=re.MULTILINE | re.IGNORECASE)
    if not matches:
        return Check("base_image", "warning", "No Docker base image was detected.")
    mutable: list[str] = []
    for image in matches:
        if image == "scratch" or "@sha256:" in image:
            continue
        last_component = image.rsplit("/", 1)[-1]
        if ":" not in last_component or image.endswith(":latest") or "${" in image:
            mutable.append(image)
    if mutable:
        return Check("base_image", "warning", f"Review mutable base image reference(s): {', '.join(mutable)}.")
    return Check("base_image", "ok", "Docker base image references are pinned by tag or digest.")


def _route_check(config: AppConfig, route: str, name: str) -> Check:
    """Look for a declared route in typical API source files without parsing frameworks."""
    source_suffixes = {".py", ".js", ".ts", ".tsx", ".go", ".java"}
    ignored = {".git", ".venv", "venv", "node_modules", "build", "dist", "__pycache__"}
    marker = route.lower()
    for candidate in config.project_root.rglob("*"):
        if any(part in ignored for part in candidate.parts) or candidate.suffix.lower() not in source_suffixes:
            continue
        if candidate.is_file() and marker in candidate.read_text(encoding="utf-8", errors="ignore").lower():
            return Check(name, "ok", f"Found '{route}' in {candidate.relative_to(config.project_root)}.")
    return Check(
        name,
        "warning",
        f"Could not locate '{route}' in source files; verify the route during a smoke test.",
    )


def _runtime_checks(config: AppConfig) -> list[Check]:
    checks = [
        Check(
            "runtime_contract",
            "ok",
            f"{config.workers} worker(s), graceful shutdown {config.shutdown_seconds}s, replicas {config.replicas}.",
        ),
        Check(
            "observability",
            "ok" if config.traces_enabled and config.structured_logs else "warning",
            "Traces and structured logs are declared."
            if config.traces_enabled and config.structured_logs
            else "Enable traces and structured logs before production deployment.",
        ),
    ]
    seen: set[str] = set()
    for name, route in (
        ("health_route", config.healthcheck),
        ("readiness_route", config.readiness_path),
        ("liveness_route", config.liveness_path),
        ("metrics_route", config.metrics_path),
    ):
        if route in seen:
            continue
        seen.add(route)
        checks.append(_route_check(config, route, name))
    return checks


def _agent_topology_check(config: AppConfig) -> Check:
    if not config.agents:
        return Check("agent_topology", "ok", "No explicit agents declared; the service will be treated as a single runtime.")
    order = ", ".join(agent_start_order(config.agents))
    return Check("agent_topology", "ok", f"Validated {len(config.agents)} agent(s); dependency-safe startup order: {order}.")


def _environment_contract_check(config: AppConfig) -> Check:
    if not config.required_env:
        return Check("environment_contract", "ok", "No required secret environment references declared.")
    missing = [name for name in config.required_env if not os.environ.get(name)]
    if missing:
        return Check(
            "environment_contract",
            "warning",
            f"Required environment references are not present locally: {', '.join(missing)}. Configure them in CI or a secret manager.",
        )
    return Check("environment_contract", "ok", "All declared environment references are present locally.")


def _access_policy_check(config: AppConfig) -> Check:
    if not config.public_api:
        return Check("access_policy", "ok", "Service is not declared as a public API.")
    insecure = {"", "none", "disabled", "not-applicable"}
    if config.auth_mode.lower() in insecure:
        return Check("access_policy", "error", "Public API requires a declared authentication mode.")
    return Check("access_policy", "ok", f"Public API access policy declares '{config.auth_mode}'.")


def _dependency_lock_check(config: AppConfig) -> Check:
    names = ("uv.lock", "poetry.lock", "requirements.txt", "package-lock.json", "pnpm-lock.yaml", "yarn.lock")
    found = [name for name in names if (config.project_root / name).is_file()]
    if found:
        return Check("dependency_lock", "ok", f"Dependency lock or manifest found: {', '.join(found)}.")
    return Check("dependency_lock", "warning", "No common dependency lock or manifest was found; make runtime dependencies reproducible.")


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
    checks.append(_base_image_check(config))
    checks.append(
        Check(
            "healthcheck",
            "ok",
            f"Application should answer on http://localhost:{config.port}{config.healthcheck}.",
        )
    )
    checks.extend(_runtime_checks(config))
    checks.append(_secret_exposure_check(config))
    checks.append(_environment_contract_check(config))
    checks.append(_access_policy_check(config))
    checks.append(_dependency_lock_check(config))
    checks.append(_agent_topology_check(config))
    checks.append(
        Check(
            "ai_contract",
            "ok",
            f"AI service contract: {config.service_kind}; provider metadata: {config.model_provider}; "
            f"models: {', '.join(config.model_ids) if config.model_ids else 'unspecified'}; telemetry: {config.telemetry}.",
        )
    )

    if config.target == "local":
        checks.append(Check("target", "ok", "Local target selected; no remote credentials are required."))
    elif config.target == "kubernetes":
        checks.append(Check("target", "ok", "Kubernetes target selected; generate a reviewable manifest with 'dossierdock manifest kubernetes'."))
    elif config.target == "docker-compose":
        checks.append(Check("target", "ok", "Compose target selected; generate a starter file with 'dossierdock manifest compose'."))
    else:
        checks.append(
            Check(
                "target",
                "warning",
                f"Target '{config.target}' is declared but no remote adapter is installed in this release.",
            )
        )
    return DoctorReport(tuple(checks), config)
