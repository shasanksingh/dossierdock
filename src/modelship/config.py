"""Manifest loading and validation for ModelShip."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import re
import tomllib
from typing import Any


class ConfigError(ValueError):
    """Raised when a ModelShip manifest is missing or invalid."""


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
    service_kind: str
    model_provider: str
    telemetry: str
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


DEFAULT_CONFIG = """# ModelShip release-evidence manifest\n# Keep credentials in your CI secret store, never in this file.\n\n[app]\nname = \"my-ai-service\"\ndockerfile = \"Dockerfile\"\ncontext = \".\"\nimage = \"my-ai-service\"\nhealthcheck = \"/health\"\nport = 8000\n\n[deployment]\ntarget = \"local\"\nenvironment = \"development\"\n\n[ai]\n# Metadata only: never put API keys or connection strings here.\nservice_kind = \"ai-api\"\nmodel_provider = \"external\"\ntelemetry = \"open-telemetry\"\n"""


def default_config_path() -> Path:
    return Path.cwd() / "modelship.toml"


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


def _port(table: dict[str, Any]) -> int:
    value = table.get("port", 8000)
    if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 65535:
        raise ConfigError("'port' must be an integer between 1 and 65535.")
    return value


def _safe_name(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", value):
        raise ConfigError("'name' may contain lowercase letters, digits, dots, underscores, and hyphens only.")
    return value


def load_config(path: str | Path | None = None) -> AppConfig:
    """Load and validate a ModelShip TOML manifest."""
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
    ai = _optional_table(document, "ai")
    name = _safe_name(_text(app, "name"))
    healthcheck = _text(app, "healthcheck", "/health")
    if not healthcheck.startswith("/"):
        raise ConfigError("'healthcheck' must start with '/'.")

    return AppConfig(
        name=name,
        dockerfile=_text(app, "dockerfile", "Dockerfile"),
        context=_text(app, "context", "."),
        image=_text(app, "image", name),
        healthcheck=healthcheck,
        port=_port(app),
        target=_text(deployment, "target", "local"),
        environment=_text(deployment, "environment", "development"),
        service_kind=_text(ai, "service_kind", "ai-api"),
        model_provider=_text(ai, "model_provider", "unspecified"),
        telemetry=_text(ai, "telemetry", "unspecified"),
        config_path=config_path,
    )
