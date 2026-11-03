"""Manifest loading and validation for DossierDock."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
import tomllib
from typing import Any


class ConfigError(ValueError):
    """Raised when a DossierDock manifest is missing or invalid."""


@dataclass(frozen=True, slots=True)
class AgentConfig:
    """A deployable participant in a multi-agent application."""

    name: str
    role: str
    depends_on: tuple[str, ...]
    healthcheck: str
    timeout_seconds: int


@dataclass(frozen=True, slots=True)
class AppConfig:
    name: str
    dockerfile: str
    context: str
    image: str
    healthcheck: str
    port: int
    target: str
    environment: str
    replicas: int
    public_api: bool
    auth_mode: str
    secrets_name: str
    readiness_path: str
    liveness_path: str
    metrics_path: str
    workers: int
    shutdown_seconds: int
    resource_cpu: str
    resource_memory: str
    service_kind: str
    model_provider: str
    model_ids: tuple[str, ...]
    telemetry: str
    traces_enabled: bool
    structured_logs: bool
    required_env: tuple[str, ...]
    agents: tuple[AgentConfig, ...]
    config_path: Path

    @property
    def project_root(self) -> Path:
        return self.config_path.parent

    @property
    def dockerfile_path(self) -> Path:
        return self.project_root / self.dockerfile

    @property
    def context_path(self) -> Path:
        return self.project_root / self.context

    def public_dict(self) -> dict[str, Any]:
        """Return serialisable non-secret configuration for command output."""
        data = asdict(self)
        data["config_path"] = str(self.config_path)
        return data


DEFAULT_CONFIG = """# DossierDock release-evidence manifest\n# Keep credentials in your CI secret store, never in this file.\n\n[app]\nname = \"my-ai-service\"\ndockerfile = \"Dockerfile\"\ncontext = \".\"\nimage = \"my-ai-service\"\nhealthcheck = \"/health\"\nport = 8000\n\n[deployment]\ntarget = \"local\"\nenvironment = \"development\"\n\n[ai]\n# Metadata only: never put API keys or connection strings here.\nservice_kind = \"ai-api\"\nmodel_provider = \"external\"\ntelemetry = \"open-telemetry\"\n"""


DEFAULT_CONFIG = DEFAULT_CONFIG.replace(
    'environment = "development"\n\n[ai]',
    'environment = "development"\nreplicas = 1\npublic_api = false\nauth_mode = "not-applicable"\nsecrets_name = "my-ai-service-secrets"\n\n[ai]',
)
DEFAULT_CONFIG = DEFAULT_CONFIG.replace(
    'telemetry = "open-telemetry"\n',
    'telemetry = "open-telemetry"\nmodel_ids = ["your-model-id"]\n',
)
DEFAULT_CONFIG += """

[runtime]
readiness_path = "/ready"
liveness_path = "/health"
metrics_path = "/metrics"
workers = 1
shutdown_seconds = 30
# Names only: DossierDock never stores secret values.
required_env = []

[resources]
cpu = "500m"
memory = "512Mi"

[observability]
traces_enabled = true
structured_logs = true

# Add one or more [[agents]] tables for a multi-agent service.
[[agents]]
name = "request-router"
role = "Routes incoming work to specialised agents"
depends_on = []
healthcheck = "/health"
timeout_seconds = 20
"""


def default_config_path() -> Path:
    return Path.cwd() / "dossierdock.toml"


def _table(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key)
    if not isinstance(value, dict):
        raise ConfigError(f"Missing [{key}] section.")
    return value


def _optional_table(document: dict[str, Any], key: str) -> dict[str, Any]:
    value = document.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] must be a table.")
    return value


def _text(table: dict[str, Any], key: str, default: str | None = None) -> str:
    value = table.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"'{key}' must be a non-empty string.")
    return value.strip()


def _route(table: dict[str, Any], key: str, default: str) -> str:
    value = _text(table, key, default)
    if not value.startswith("/"):
        raise ConfigError(f"'{key}' must start with '/'.")
    return value


def _port(table: dict[str, Any]) -> int:
    value = table.get("port", 8000)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ConfigError("'port' must be an integer between 1 and 65535.")
    return value


def _positive_int(table: dict[str, Any], key: str, default: int) -> int:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(f"'{key}' must be a positive integer.")
    return value


def _bool(table: dict[str, Any], key: str, default: bool) -> bool:
    value = table.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(f"'{key}' must be true or false.")
    return value


def _string_list(table: dict[str, Any], key: str, default: tuple[str, ...] = ()) -> tuple[str, ...]:
    value = table.get(key, list(default))
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ConfigError(f"'{key}' must be a list of non-empty strings.")
    items = tuple(item.strip() for item in value)
    if len(set(items)) != len(items):
        raise ConfigError(f"'{key}' must not contain duplicates.")
    return items


def _safe_name(value: str, field: str = "name") -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value):
        raise ConfigError(f"'{field}' may contain lowercase letters, digits, dots, underscores, and hyphens only.")
    return value


def _environment_names(table: dict[str, Any]) -> tuple[str, ...]:
    items = _string_list(table, "required_env")
    for item in items:
        if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", item):
            raise ConfigError("'required_env' entries must be uppercase environment-variable names.")
    return items


def _validate_agent_graph(agents: tuple[AgentConfig, ...]) -> None:
    names = {agent.name for agent in agents}
    for agent in agents:
        missing = sorted(set(agent.depends_on) - names)
        if missing:
            raise ConfigError(f"Agent '{agent.name}' depends on unknown agent(s): {', '.join(missing)}.")
        if agent.name in agent.depends_on:
            raise ConfigError(f"Agent '{agent.name}' cannot depend on itself.")

    visiting: set[str] = set()
    visited: set[str] = set()
    by_name = {agent.name: agent for agent in agents}

    def visit(name: str) -> None:
        if name in visiting:
            raise ConfigError("Agent dependencies must form an acyclic graph.")
        if name in visited:
            return
        visiting.add(name)
        for dependency in by_name[name].depends_on:
            visit(dependency)
        visiting.remove(name)
        visited.add(name)

    for agent in agents:
        visit(agent.name)


def _agents(document: dict[str, Any], default_healthcheck: str) -> tuple[AgentConfig, ...]:
    raw_agents = document.get("agents", [])
    if not isinstance(raw_agents, list) or any(not isinstance(item, dict) for item in raw_agents):
        raise ConfigError("'agents' must be an array of tables.")

    agents: list[AgentConfig] = []
    names: set[str] = set()
    for item in raw_agents:
        name = _safe_name(_text(item, "name"), "agents.name")
        if name in names:
            raise ConfigError(f"Duplicate agent name: '{name}'.")
        names.add(name)
        agents.append(
            AgentConfig(
                name=name,
                role=_text(item, "role"),
                depends_on=_string_list(item, "depends_on"),
                healthcheck=_route(item, "healthcheck", default_healthcheck),
                timeout_seconds=_positive_int(item, "timeout_seconds", 30),
            )
        )

    result = tuple(agents)
    _validate_agent_graph(result)
    return result


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load and validate a DossierDock TOML deployment contract."""
    config_path = Path(path) if path else default_config_path()
    config_path = config_path.expanduser().resolve()
    if not config_path.is_file():
        raise ConfigError(f"Manifest not found: {config_path}")

    try:
        with config_path.open("rb") as handle:
            document = tomllib.load(handle)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"Invalid TOML in {config_path.name}: {error}") from error

    app = _table(document, "app")
    deployment = _table(document, "deployment")
    runtime = _optional_table(document, "runtime")
    resources = _optional_table(document, "resources")
    observability = _optional_table(document, "observability")
    ai = _optional_table(document, "ai")
    name = _safe_name(_text(app, "name"))
    healthcheck = _route(app, "healthcheck", "/health")

    return AppConfig(
        name=name,
        dockerfile=_text(app, "dockerfile", "Dockerfile"),
        context=_text(app, "context", "."),
        image=_text(app, "image", name),
        healthcheck=healthcheck,
        port=_port(app),
        target=_text(deployment, "target", "local"),
        environment=_text(deployment, "environment", "development"),
        replicas=_positive_int(deployment, "replicas", 1),
        public_api=_bool(deployment, "public_api", False),
        auth_mode=_text(deployment, "auth_mode", "not-applicable"),
        secrets_name=_safe_name(_text(deployment, "secrets_name", f"{name}-secrets"), "secrets_name"),
        readiness_path=_route(runtime, "readiness_path", healthcheck),
        liveness_path=_route(runtime, "liveness_path", healthcheck),
        metrics_path=_route(runtime, "metrics_path", "/metrics"),
        workers=_positive_int(runtime, "workers", 1),
        shutdown_seconds=_positive_int(runtime, "shutdown_seconds", 30),
        resource_cpu=_text(resources, "cpu", "500m"),
        resource_memory=_text(resources, "memory", "512Mi"),
        service_kind=_text(ai, "service_kind", "ai-api"),
        model_provider=_text(ai, "model_provider", "unspecified"),
        model_ids=_string_list(ai, "model_ids"),
        telemetry=_text(ai, "telemetry", "unspecified"),
        traces_enabled=_bool(observability, "traces_enabled", True),
        structured_logs=_bool(observability, "structured_logs", True),
        required_env=_environment_names(runtime),
        agents=_agents(document, healthcheck),
        config_path=config_path,
    )
