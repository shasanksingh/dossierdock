"""Provider-neutral deployment manifest generators."""

from __future__ import annotations

import json
import re

from dossierdock.config import AppConfig
from dossierdock.topology import agent_start_order


def _yaml(value: object) -> str:
    """Return a YAML-safe scalar using JSON's YAML-compatible string syntax."""
    return json.dumps(str(value))


def _kubernetes_name(name: str) -> str:
    value = re.sub(r"[^a-z0-9-]+", "-", name.lower()).strip("-")
    return value[:63].rstrip("-") or "ai-service"


def render_kubernetes(config: AppConfig) -> str:
    """Render a Deployment and Service without embedding any secret values."""
    name = _kubernetes_name(config.name)
    env_lines = [
        "        - name: DOSSIERDOCK_MODEL_PROVIDER",
        f"          value: {_yaml(config.model_provider)}",
        "        - name: DOSSIERDOCK_SERVICE_KIND",
        f"          value: {_yaml(config.service_kind)}",
        "        - name: DOSSIERDOCK_AGENT_START_ORDER",
        f"          value: {_yaml(','.join(agent_start_order(config.agents)))}",
    ]
    for variable in config.required_env:
        env_lines.extend(
            [
                f"        - name: {variable}",
                "          valueFrom:",
                "            secretKeyRef:",
                f"              name: {config.secrets_name}",
                f"              key: {variable}",
            ]
        )

    return "\n".join(
        [
            "apiVersion: apps/v1",
            "kind: Deployment",
            "metadata:",
            f"  name: {name}",
            "  labels:",
            f"    app.kubernetes.io/name: {name}",
            "    app.kubernetes.io/managed-by: dossierdock",
            f"    dossierdock.io/environment: {_yaml(config.environment)}",
            f"    dossierdock.io/model-provider: {_yaml(config.model_provider)}",
            "spec:",
            f"  replicas: {config.replicas}",
            "  selector:",
            "    matchLabels:",
            f"      app.kubernetes.io/name: {name}",
            "  template:",
            "    metadata:",
            "      labels:",
            f"        app.kubernetes.io/name: {name}",
            "    spec:",
            "      containers:",
            f"      - name: {name}",
            f"        image: {_yaml(config.image)}",
            "        imagePullPolicy: IfNotPresent",
            "        ports:",
            f"        - containerPort: {config.port}",
            "          name: http",
            "        readinessProbe:",
            "          httpGet:",
            f"            path: {_yaml(config.readiness_path)}",
            "            port: http",
            "          initialDelaySeconds: 3",
            "          periodSeconds: 10",
            "        livenessProbe:",
            "          httpGet:",
            f"            path: {_yaml(config.liveness_path)}",
            "            port: http",
            "          initialDelaySeconds: 10",
            "          periodSeconds: 20",
            "        resources:",
            "          requests:",
            f"            cpu: {_yaml(config.resource_cpu)}",
            f"            memory: {_yaml(config.resource_memory)}",
            "          limits:",
            f"            cpu: {_yaml(config.resource_cpu)}",
            f"            memory: {_yaml(config.resource_memory)}",
            "        env:",
            *env_lines,
            "---",
            "apiVersion: v1",
            "kind: Service",
            "metadata:",
            f"  name: {name}",
            "  labels:",
            "    app.kubernetes.io/managed-by: dossierdock",
            "spec:",
            "  selector:",
            f"    app.kubernetes.io/name: {name}",
            "  ports:",
            "  - name: http",
            f"    port: {config.port}",
            "    targetPort: http",
            "  type: ClusterIP",
            "",
        ]
    )


def render_compose(config: AppConfig) -> str:
    """Render a Compose starter that references, but never writes, secrets."""
    environment_lines = [
        f"      DOSSIERDOCK_MODEL_PROVIDER: {_yaml(config.model_provider)}",
        f"      DOSSIERDOCK_SERVICE_KIND: {_yaml(config.service_kind)}",
        f"      DOSSIERDOCK_AGENT_START_ORDER: {_yaml(','.join(agent_start_order(config.agents)))}",
    ]
    environment_lines.extend(f"      {variable}: ${{{variable}:?Set {variable}}}" for variable in config.required_env)

    return "\n".join(
        [
            "services:",
            f"  {config.name}:",
            f"    image: {_yaml(config.image)}",
            "    build:",
            f"      context: {_yaml(config.context)}",
            f"      dockerfile: {_yaml(config.dockerfile)}",
            "    ports:",
            f"      - {_yaml(f'{config.port}:{config.port}')}",
            "    environment:",
            *environment_lines,
            "    labels:",
            "      io.dossierdock.managed: \"true\"",
            f"      io.dossierdock.readiness-path: {_yaml(config.readiness_path)}",
            f"      io.dossierdock.liveness-path: {_yaml(config.liveness_path)}",
            "",
        ]
    )
